from fastapi import APIRouter, HTTPException, Depends, Response, status, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
import datetime
import json
import urllib.parse
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

REDIRECT_URI = f"{settings.API_BASE_URL}/auth/youtube/callback"
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
        client_config = json.loads(settings.GOOGLE_CLIENT_SECRETS_FILE.read_text())

        return Flow.from_client_config(
            client_config,
            scopes=GOOGLE_SCOPES,
            redirect_uri=REDIRECT_URI,
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

    state_payload = {
        "account_id": account_id,
        "redirect": next,
    }

    state = urllib.parse.quote(json.dumps(state_payload))

    
    
    flow = get_google_flow()

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )

    # IMPORTANT: force 302
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

    # ---- GUARD: prevent replay / double-callback ----
    existing_token = get_valid_youtube_token(account_id)
    if existing_token:
        return RedirectResponse(
            f"{FRONTEND_BASE_URL}{redirect_path}?youtube=connected",
            status_code=302,
        )

    # ---- Recreate flow EXACTLY as start() ----
    flow = get_google_flow()

    # ---- Exchange code ONCE ----
    flow.fetch_token(code=code)
    creds: Credentials = flow.credentials

    # ---- Persist token ----
    store_token_in_db(account_id, creds)

    return RedirectResponse(
        f"{FRONTEND_BASE_URL}{redirect_path}?youtube=connected",
        status_code=302,
    )


@router.get("/youtube/status/{account_id}")
def youtube_auth_status(
    account_id: int,
    current_user: dict = Depends(get_current_user),
):
    token = get_valid_youtube_token(account_id)

    if not token:
        return {
            "authenticated": False,
            "auth_url": f"{settings.API_BASE_URL}/auth/youtube/start/{account_id}",
        }

    return {
        "authenticated": True
    }


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
