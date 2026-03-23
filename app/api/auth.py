from fastapi import APIRouter, HTTPException, Depends, Response, status, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
import datetime
import json
import urllib.parse
import httpx
from typing import Optional
from sqlalchemy.orm import Session
from app.api.subscriptions import Subscription

from app.api.deps import get_current_user

from app.services.auth_database import (
    add_user,
    verify_user,
    store_token_in_db,
    get_valid_youtube_token,
    get_conn,
    get_active_subscription,
    get_user_by_email,
    delete_youtube_token,
    store_twitter_token_in_db,
    get_valid_twitter_token,
)

from app.utils.security import hash_password, create_access_token
from app.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

# -----------------------------
# GOOGLE OAUTH CONFIG
# -----------------------------

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]

# -----------------------------
# TWITTER OAUTH CONFIG
# -----------------------------

TWITTER_SCOPES = [
    "tweet.read",
    "tweet.write",
    "users.read",
    "offline.access",
    "media.write",
    "dm.read",
    "dm.write",
    "like.write",
    "follows.write",
]

# Twitter OAuth 2.0 endpoints
TWITTER_AUTH_URL = "https://twitter.com/i/oauth2/authorize"
TWITTER_TOKEN_URL = "https://api.twitter.com/2/oauth2/token"

# Dynamic redirect URI based on environment
def get_redirect_uri(provider: str = "youtube"):
    """Return the appropriate redirect URI based on the current environment"""
    if settings.ENV == "production":
        return f"{settings.API_BASE_URL}/auth/{provider}/callback"
    else:
        return f"http://localhost:8000/auth/{provider}/callback"

FRONTEND_BASE_URL = settings.FRONTEND_BASE_URL

# -----------------------------
# Schemas
# -----------------------------

class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    email: str


class RegisterRequest(BaseModel):
    email: str
    password: str


class RegisterResponse(BaseModel):
    email: str


class MeResponse(BaseModel):
    email: str

class PasswordResetRequest(BaseModel):
    email: str


class PasswordResetConfirm(BaseModel):
    token: str
    password: str

class TwitterAuthStatus(BaseModel):
    authenticated: bool
    account_id: int
    auth_url: Optional[str] = None
    error: Optional[str] = None

# -----------------------------
# Auth routes
# -----------------------------

@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest):
    success = add_user(
        email=payload.email,
        password_hash=hash_password(payload.password),
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    return RegisterResponse(email=payload.email)


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, response: Response):
    is_valid = verify_user(
        username=payload.email,
        password=payload.password,
    )


    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    access_token = create_access_token(data={"sub": payload.email})

    # Always use SameSite=None and Secure for cross-origin cookie support
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite="none",
        secure=True,
        max_age=60 * 60 * 24,
    )

    return LoginResponse(email=payload.email)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    response.delete_cookie(
        key="access_token",
        samesite="none",
        secure=True,
    )


from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class SubscriptionInfo(BaseModel):
    plan_id: Optional[int] = None
    plan_name: Optional[str] = None
    status: Optional[str] = None
    end_date: Optional[datetime] = None


@router.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    """
    ✅ Reads ONLY from:
    - JWT (already validated)
    - AUTH DB (subscriptions)
    """

    # --- HARD AUTH GUARD (defensive, but safe) ---
    if not current_user or "id" not in current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    subscription_data = {
        "is_active": False
    }

    # --- AUTH DB SUBSCRIPTION CHECK ---
    try:
        with get_conn() as conn:
            subscription = get_active_subscription(conn, current_user["id"])

            if subscription and subscription.get("is_active"):
                subscription_data = {
                    "plan_id": subscription.get("plan_id"),
                    "plan_name": subscription.get("plan_name"),
                    "status": subscription.get("status"),
                    "end_date": subscription.get("end_date"),
                    "is_active": True,
                }

    except Exception as e:
        # Never break auth because of billing
        print("[AUTH][ME] Subscription lookup failed:", e)

    return {
        "id": current_user["id"],
        "email": current_user["email"],
        "username": current_user["email"],
        "is_admin": current_user.get("is_admin", False),
        "subscription": subscription_data,
    }




# =====================================================
# YOUTUBE OAUTH
# =====================================================

def get_google_flow():
    """
    Create Google OAuth flow using either environment variable or local file
    """
    if not settings.GOOGLE_CLIENT_SECRETS_JSON:
        raise HTTPException(
            status_code=500,
            detail="Google OAuth not configured. Missing client secrets."
        )
    
    redirect_uri = get_redirect_uri("youtube")
    print(f"[AUTH] Using YouTube redirect URI: {redirect_uri}")
    
    return Flow.from_client_config(
        settings.GOOGLE_CLIENT_SECRETS_JSON,
        scopes=GOOGLE_SCOPES,
        redirect_uri=redirect_uri,
    )

@router.get("/youtube/start/{account_id}")
def youtube_auth_start(
    account_id: int,
    request: Request,
    next: str = "/",
):
    """
    Starts YouTube OAuth flow
    """
    
    if next.startswith(('http://', 'https://')):
        from urllib.parse import urlparse
        parsed = urlparse(next)
        next = parsed.path
        if parsed.query:
            next += f"?{parsed.query}"
    
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)

    state_payload = {
        "account_id": account_id,
        "redirect": next,
        "code_verifier": code_verifier,
    }

    state = urllib.parse.quote(json.dumps(state_payload))

    flow = get_google_flow()

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
        code_challenge=code_challenge,
        code_challenge_method="S256",
    )

    return RedirectResponse(auth_url, status_code=302)


@router.get("/youtube/callback")
def youtube_auth_callback(
    code: str,
    state: str,
):
    """
    Google redirects here after consent.
    Stores tokens and redirects back to frontend.
    """

    # ---- Decode and validate state safely ----
    try:
        state_data = json.loads(urllib.parse.unquote(state))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    account_id = state_data["account_id"]
    redirect_path = state_data.get("redirect", "/")
    code_verifier = state_data.get("code_verifier")

    # If redirect_path is a full URL, extract just the path
    if redirect_path.startswith(('http://', 'https://')):
        from urllib.parse import urlparse
        parsed = urlparse(redirect_path)
        redirect_path = parsed.path
        # Add back query params if needed
        if parsed.query:
            redirect_path += f"?{parsed.query}"

    base_url = FRONTEND_BASE_URL.rstrip('/')

    # Ensure redirect_path starts with a slash
    if not redirect_path.startswith('/'):
        redirect_path = '/' + redirect_path

    # ---- GUARD: prevent replay / double-callback ----
    existing_token = get_valid_youtube_token(account_id)
    if existing_token:
        return RedirectResponse(
            f"{base_url}{redirect_path}?youtube=connected",
            status_code=302,
        )

    # ---- Recreate flow EXACTLY as start() ----
    flow = get_google_flow()

    # ---- Exchange code ONCE (pass verifier if PKCE was used) ----
    fetch_kwargs = {"code": code}
    if code_verifier:
        fetch_kwargs["code_verifier"] = code_verifier
    flow.fetch_token(**fetch_kwargs)
    creds: Credentials = flow.credentials

    # ---- Persist token ----
    store_token_in_db(account_id, creds)

    return RedirectResponse(
        f"{base_url}{redirect_path}?youtube=connected",
        status_code=302,
    )


@router.get("/youtube/status/{account_id}")
def youtube_auth_status(
    account_id: int,
    current_user: dict = Depends(get_current_user),
):
    """
    Check if a YouTube account is authenticated.
    Returns auth_url if not authenticated or token is invalid.
    """
    try:
        token = get_valid_youtube_token(account_id)
        
        if token:
            return {
                "authenticated": True,
                "account_id": account_id
            }
        else:
            return {
                "authenticated": False,
                "auth_url": f"{settings.API_BASE_URL}/auth/youtube/start/{account_id}",
            }
    except Exception as e:
        # Token refresh failed - need reauthentication
        print(f"[AUTH] Token validation failed for account {account_id}: {e}")
        return {
            "authenticated": False,
            "auth_url": f"{settings.API_BASE_URL}/auth/youtube/start/{account_id}",
            "error": "Token expired or invalid"
        }


# =====================================================
# TWITTER/X OAUTH
# =====================================================

def generate_code_verifier() -> str:
    """Generate a code verifier for PKCE."""
    import secrets
    import base64
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
    return code_verifier

def generate_code_challenge(verifier: str) -> str:
    """Generate a code challenge from verifier."""
    import hashlib
    import base64
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode('utf-8').rstrip('=')
    return challenge

@router.get("/twitter/start/{account_id}")
def twitter_auth_start(
    account_id: int,
    next: str = "/",
):
    """
    Starts Twitter OAuth 2.0 flow with PKCE.
    """
    # Validate Twitter credentials are configured
    if not settings.TWITTER_CLIENT_ID or not settings.TWITTER_CLIENT_SECRET:
        raise HTTPException(
            status_code=500,
            detail="Twitter OAuth not configured. Missing client credentials."
        )
    
    # Clean redirect path
    if next.startswith(('http://', 'https://')):
        from urllib.parse import urlparse
        parsed = urlparse(next)
        next = parsed.path
        if parsed.query:
            next += f"?{parsed.query}"
    
    # Generate PKCE verifier and challenge
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)
    
    # Store verifier in session or state for callback
    state_payload = {
        "account_id": account_id,
        "redirect": next,
        "code_verifier": code_verifier  # Store verifier to use in callback
    }
    
    state = urllib.parse.quote(json.dumps(state_payload))
    
    # Build authorization URL
    redirect_uri = get_redirect_uri("twitter")
    
    params = {
        "response_type": "code",
        "client_id": settings.TWITTER_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "scope": " ".join(TWITTER_SCOPES),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent"
    }
    
    auth_url = f"{TWITTER_AUTH_URL}?{urllib.parse.urlencode(params)}"
    
    return RedirectResponse(auth_url, status_code=302)


@router.get("/twitter/callback")
async def twitter_auth_callback(
    code: str,
    state: str,
    error: Optional[str] = None,
):
    """
    Twitter redirects here after consent.
    Exchanges code for tokens and stores them.
    """
    # Handle OAuth errors
    if error:
        raise HTTPException(
            status_code=400,
            detail=f"Twitter OAuth error: {error}"
        )
    
    # ---- Decode and validate state safely ----
    try:
        state_data = json.loads(urllib.parse.unquote(state))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    
    account_id = state_data["account_id"]
    redirect_path = state_data.get("redirect", "/")
    code_verifier = state_data.get("code_verifier")
    
    if not code_verifier:
        raise HTTPException(status_code=400, detail="Missing code verifier")
    
    # Clean redirect path
    if redirect_path.startswith(('http://', 'https://')):
        from urllib.parse import urlparse
        parsed = urlparse(redirect_path)
        redirect_path = parsed.path
        if parsed.query:
            redirect_path += f"?{parsed.query}"
    
    base_url = FRONTEND_BASE_URL.rstrip('/')
    if not redirect_path.startswith('/'):
        redirect_path = '/' + redirect_path
    
    # ---- Exchange code for tokens ----
    redirect_uri = get_redirect_uri("twitter")
    
    auth = httpx.BasicAuth(
        username=settings.TWITTER_CLIENT_ID,
        password=settings.TWITTER_CLIENT_SECRET
    )
    
    data = {
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                TWITTER_TOKEN_URL,
                auth=auth,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            if response.status_code != 200:
                error_detail = response.text
                print(f"[TWITTER] Token exchange failed: {error_detail}")
                return RedirectResponse(
                    f"{base_url}{redirect_path}?twitter=error&message=token_exchange_failed",
                    status_code=302,
                )
            
            tokens = response.json()
            
            # Calculate expiry
            expires_in = tokens.get("expires_in", 7200)
            expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=expires_in)
            
            # Store tokens in database
            store_twitter_token_in_db(
                account_id=account_id,
                access_token=tokens["access_token"],
                refresh_token=tokens.get("refresh_token"),
                expires_at=expires_at,
                scope=tokens.get("scope", " ".join(TWITTER_SCOPES))
            )
            
            return RedirectResponse(
                f"{base_url}{redirect_path}?twitter=connected",
                status_code=302,
            )
            
    except Exception as e:
        print(f"[TWITTER] Callback error: {e}")
        return RedirectResponse(
            f"{base_url}{redirect_path}?twitter=error&message=callback_failed",
            status_code=302,
        )


@router.get("/twitter/status/{account_id}", response_model=TwitterAuthStatus)
def twitter_auth_status(
    account_id: int,
    current_user: dict = Depends(get_current_user),
):
    """
    Check if a Twitter account is authenticated.
    Returns auth_url if not authenticated or token is invalid.
    """
    try:
        token = get_valid_twitter_token(account_id)
        
        if token:
            return {
                "authenticated": True,
                "account_id": account_id
            }
        else:
            return {
                "authenticated": False,
                "account_id": account_id,
                "auth_url": f"{settings.API_BASE_URL}/auth/twitter/start/{account_id}",
            }
    except Exception as e:
        # Token refresh failed - need reauthentication
        print(f"[AUTH] Twitter token validation failed for account {account_id}: {e}")
        return {
            "authenticated": False,
            "account_id": account_id,
            "auth_url": f"{settings.API_BASE_URL}/auth/twitter/start/{account_id}",
            "error": "Token expired or invalid"
        }


@router.post("/twitter/refresh/{account_id}")
def refresh_twitter_token(
    account_id: int,
    current_user: dict = Depends(get_current_user),
):
    """
    Manually trigger a Twitter token refresh.
    Useful for testing or force-refresh scenarios.
    """
    from app.services.twitter_token_service import refresh_twitter_token
    
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT refresh_token
                    FROM twitter_tokens
                    WHERE account_id = %s
                """, (account_id,))
                token_data = cur.fetchone()
                
                if not token_data or not token_data["refresh_token"]:
                    raise HTTPException(
                        status_code=400,
                        detail="No refresh token available for this account"
                    )
                
                success = refresh_twitter_token(account_id, token_data["refresh_token"])
                
                if success:
                    return {"message": "Token refreshed successfully"}
                else:
                    raise HTTPException(
                        status_code=500,
                        detail="Failed to refresh token"
                    )
                    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error refreshing token: {str(e)}"
        )


# =====================================================
# PASSWORD RESET
# =====================================================

from app.services.auth_database import create_password_reset_token, reset_password_with_token
from fastapi.responses import JSONResponse


@router.post("/password-reset/request")
def request_password_reset(payload: PasswordResetRequest):
    """
    Request a password reset email.
    Always returns success to prevent email enumeration.
    """
    try:
        create_password_reset_token(payload.email)
    except Exception as e:
        # Log the error but don't expose it (security)
        print(f"[AUTH] Password reset request error: {e}")

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "If an account exists for this email, a reset link has been sent."
        }
    )


@router.post("/password-reset/confirm")
def confirm_password_reset(payload: PasswordResetConfirm):
    """
    Confirm password reset with token and new password.
    """
    if not payload.token or not payload.password:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "Token and password are required."
            }
        )

    if len(payload.password) < 6:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "Password must be at least 6 characters."
            }
        )

    try:
        success = reset_password_with_token(
            token=payload.token,
            new_password=payload.password,
        )

        if not success:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "message": "Invalid or expired reset token."
                }
            )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Password reset successful."
            }
        )

    except Exception as e:
        print(f"[AUTH] Password reset confirm error: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "An error occurred. Please try again."
            }
        )