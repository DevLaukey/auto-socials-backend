from pathlib import Path
from pydantic_settings import BaseSettings

# backend/app/config.py

APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent  # backend/

MEDIA_ROOT = BACKEND_DIR / "media"
UPLOAD_DIR = MEDIA_ROOT / "uploads"
CLIPS_DIR = MEDIA_ROOT / "clips"
SUBTITLES_DIR = MEDIA_ROOT / "subtitles"
VIDEOS_DIR = MEDIA_ROOT / "videos"

# Create all directories at import time
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
CLIPS_DIR.mkdir(parents=True, exist_ok=True)
SUBTITLES_DIR.mkdir(parents=True, exist_ok=True)
VIDEOS_DIR.mkdir(parents=True, exist_ok=True)


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
    CLIPS_DIR: Path = BACKEND_DIR / "media" / "clips"
    SUBTITLES_DIR: Path = BACKEND_DIR / "media" / "subtitles"
    VIDEOS_DIR: Path = BACKEND_DIR / "media" / "videos"

    # ------------------
    # GOOGLE / YOUTUBE OAUTH
    # ------------------
    FRONTEND_BASE_URL: str = "http://localhost:3000"
    GOOGLE_CLIENT_SECRETS_FILE: Path = APP_DIR / "client_secret.json"

    GOOGLE_CLIENT_SECRETS_JSON: dict = {}

    # AI
    OPENAI_API_KEY: str | None = None
    GROQ_API_KEY: str | None = None

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

import os
import json

# ---- Load Google OAuth secrets ----
# Priority 1: From environment variable (Fly.io)
if "GOOGLE_CLIENT_SECRET_JSON" in os.environ:
    try:
        settings.GOOGLE_CLIENT_SECRETS_JSON = json.loads(os.environ["GOOGLE_CLIENT_SECRET_JSON"])
        print("[CONFIG] Loaded Google secrets from environment variable")
    except json.JSONDecodeError as e:
        print(f"[CONFIG] Failed to parse GOOGLE_CLIENT_SECRET_JSON: {e}")

# Priority 2: From local file (development)
elif settings.GOOGLE_CLIENT_SECRETS_FILE.exists():
    try:
        with open(settings.GOOGLE_CLIENT_SECRETS_FILE) as f:
            settings.GOOGLE_CLIENT_SECRETS_JSON = json.load(f)
        print(f"[CONFIG] Loaded Google secrets from file: {settings.GOOGLE_CLIENT_SECRETS_FILE}")
    except Exception as e:
        print(f"[CONFIG] Failed to load Google secrets file: {e}")

# ------------------
# Ensure all dirs exist (again, just to be safe)
# ------------------
settings.MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
settings.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
settings.CLIPS_DIR.mkdir(parents=True, exist_ok=True)
settings.SUBTITLES_DIR.mkdir(parents=True, exist_ok=True)
settings.VIDEOS_DIR.mkdir(parents=True, exist_ok=True)