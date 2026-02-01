from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional
import json
import os
import tempfile

# backend/app/config.py

APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent  # backend/

MEDIA_ROOT = BACKEND_DIR / "media"
UPLOAD_DIR = MEDIA_ROOT / "uploads"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    # ------------------
    # Core
    # ------------------
    APP_NAME: str = "Social Automation Backend"
    ENV: str = "development"

    # MUST be overridden in Fly.io
    API_BASE_URL: str = "http://localhost:8000"

    # ------------------
    # CORS
    # ------------------
    CORS_ORIGINS: str = (
        "http://localhost:3000,"
        "http://127.0.0.1:3000,"
        "https://localhost:3000,"
        "https://auto-socials-hxvi.vercel.app,"
        "https://auto-socials.vercel.app"
    )

    # ------------------
    # Security
    # ------------------
    SECRET_KEY: str = "CHANGE_ME_IMMEDIATELY"

    # ------------------
    # Database
    # ------------------
    DATABASE_URL: str = ""

    # ------------------
    # Redis / Celery
    # ------------------
    REDIS_URL: str = "redis://localhost:6380/0"

    # ------------------
    # Media
    # ------------------
    MEDIA_ROOT: Path = BACKEND_DIR / "media"
    UPLOADS_DIR: Path = BACKEND_DIR / "media" / "uploads"

    # ------------------
    # 🔥 GOOGLE / YOUTUBE OAUTH
    # ------------------
    FRONTEND_BASE_URL: str = "http://localhost:3000"

    # Stored in Fly.io secrets
    GOOGLE_CLIENT_SECRET_JSON: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

# ------------------
# Ensure dirs exist
# ------------------
settings.MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
settings.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


# ------------------
# Google OAuth helper
# ------------------
def get_google_client_secrets_file() -> str:
    """
    Writes GOOGLE_CLIENT_SECRET_JSON to a temp file
    and returns the file path.

    Required because google-auth expects a file path.
    """

    if not settings.GOOGLE_CLIENT_SECRET_JSON:
        raise RuntimeError(
            "Missing GOOGLE_CLIENT_SECRET_JSON. "
            "Set it using `fly secrets set`."
        )

    try:
        json.loads(settings.GOOGLE_CLIENT_SECRET_JSON)
    except json.JSONDecodeError:
        raise RuntimeError("GOOGLE_CLIENT_SECRET_JSON is not valid JSON")

    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        delete=False,
    )
    tmp.write(settings.GOOGLE_CLIENT_SECRET_JSON)
    tmp.flush()
    tmp.close()

    return tmp.name
