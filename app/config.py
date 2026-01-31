from pathlib import Path
from pydantic_settings import BaseSettings

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
    API_BASE_URL: str = "http://localhost:8000"

    # ------------------
    # CORS - comma-separated list of allowed origins
    # ------------------
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000,https://localhost:3000,https://auto-socials-hxvi.vercel.app,https://auto-socials.vercel.app"

    # ------------------
    # Security
    # ------------------
    SECRET_KEY: str = "CHANGE_ME_IMMEDIATELY"

    # ------------------
    # Database (Fly.io sets DATABASE_URL automatically)
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
    # GOOGLE_CLIENT_SECRETS_FILE: Path = BACKEND_DIR / "client_secret.json"
    FRONTEND_BASE_URL: str = "http://localhost:3000"
    GOOGLE_CLIENT_SECRETS_FILE: Path = APP_DIR / "client_secret.json"

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
# FAIL FAST if OAuth misconfigured
# ------------------
# if not settings.GOOGLE_CLIENT_SECRETS_FILE.exists():
#     raise RuntimeError(
#         f"Missing Google OAuth config file: {settings.GOOGLE_CLIENT_SECRETS_FILE}"
#     )
