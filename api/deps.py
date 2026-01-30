from fastapi import HTTPException, status, Cookie, Depends
from jose import jwt, JWTError

from app.config import settings
from app.utils.security import ALGORITHM
from app.services.auth_database import get_conn, is_admin_user


# --------------------------------------------------
# INTERNAL HELPERS
# --------------------------------------------------

def _get_user_by_email(email: str):
    """
    INTERNAL helper.
    Fetches user from AUTH (Postgres) database.

    Returns:
        dict {id, email, is_active, is_admin} or None
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, email, is_active, is_admin
                FROM users
                WHERE email = %s
                """,
                (email,),
            )
            return cur.fetchone()


# --------------------------------------------------
# AUTH DEPENDENCIES
# --------------------------------------------------

def get_current_user(access_token: str | None = Cookie(default=None)):
    """
    Canonical auth dependency.

    SOURCE OF TRUTH:
    - JWT (cookie)
    - AUTH database (Postgres)

    ENFORCES:
    - Valid JWT
    - User exists
    - User is active

    NEVER touches:
    - SQLite / app database
    """

    # -------------------------------------------------
    # 1️⃣ Require cookie
    # -------------------------------------------------
    if access_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    # -------------------------------------------------
    # 2️⃣ Decode & validate JWT
    # -------------------------------------------------
    try:
        payload = jwt.decode(
            access_token,
            settings.SECRET_KEY,
            algorithms=[ALGORITHM],
        )

        email: str | None = payload.get("sub")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    # -------------------------------------------------
    # 3️⃣ Resolve user from AUTH DB
    # -------------------------------------------------
    user = _get_user_by_email(email)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    # -------------------------------------------------
    # 4️⃣ Return canonical auth context
    # -------------------------------------------------
    return {
        "id": user["id"],
        "email": user["email"],
        "is_admin": user["is_admin"],
    }


def require_admin(user=Depends(get_current_user)):
    """
    Admin-only dependency.

    Use on ALL admin endpoints.
    """
    if not user["is_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )

    return user
