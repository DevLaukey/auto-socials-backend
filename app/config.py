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

    # ------------------
    # TWITTER/X OAUTH
    # ------------------
    TWITTER_CLIENT_ID: str = ""
    TWITTER_CLIENT_SECRET: str = ""
    TWITTER_BEARER_TOKEN: str = ""  # Optional, for app-only auth

    # ------------------
    # PAYPAL CONFIGURATION
    # ------------------
    PAYPAL_CLIENT_ID: str = ""
    PAYPAL_CLIENT_SECRET: str = ""
    PAYPAL_MODE: str = "sandbox"  # sandbox or live
    PAYPAL_WEBHOOK_ID: str = ""  # For webhook verification
    PAYPAL_RECEIVER_EMAIL: str = ""  # PayPal email for receiving payments

    # ------------------
    # MONEYMOTION CONFIGURATION (UPDATED - API KEY ONLY)
    # ------------------
    MONEYMOTION_API_KEY: str = ""  # Only this is required
    MONEYMOTION_WEBHOOK_SECRET: str = ""  # Optional, for webhook verification
    MONEYMOTION_MODE: str = "live"  # sandbox or live
    MONEYMOTION_BASE_URL: str = "https://api.moneymotion.io"  # Base API URL

    # ------------------
    # Cloud Storage (Tigris / S3-compatible)
    # ------------------
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_ENDPOINT_URL_S3: str = "https://fly.storage.tigris.dev"
    AWS_REGION: str = "auto"
    BUCKET_NAME: str = ""
    BUCKET_PUBLIC_URL: str = ""  

    # ------------------
    # AI Providers
    # ------------------
    OPENAI_API_KEY: str | None = None
    GROQ_API_KEY: str | None = None

    # ------------------
    # PayPal API URL (computed property)
    # ------------------
    @property
    def PAYPAL_API_URL(self) -> str:
        if self.PAYPAL_MODE == "live":
            return "https://api.paypal.com"
        return "https://api.sandbox.paypal.com"

    # ------------------
    # MoneyMotion API URL (UPDATED)
    # ------------------
    @property
    def MONEYMOTION_API_URL(self) -> str:
        """Get the MoneyMotion API URL. Sandbox vs live is determined by the API key prefix (mk_test_ vs mk_live_), not the URL."""
        return self.MONEYMOTION_BASE_URL

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

# ---- Load MoneyMotion credentials from environment variables (UPDATED) ----
if "MONEYMOTION_API_KEY" in os.environ:
    settings.MONEYMOTION_API_KEY = os.environ["MONEYMOTION_API_KEY"]
    print("[CONFIG] Loaded MoneyMotion API key from environment")

if "MONEYMOTION_WEBHOOK_SECRET" in os.environ:
    settings.MONEYMOTION_WEBHOOK_SECRET = os.environ["MONEYMOTION_WEBHOOK_SECRET"]
    print("[CONFIG] Loaded MoneyMotion webhook secret from environment")

# ---- Validate Twitter OAuth configuration in production ----
if settings.ENV == "production":
    if not settings.TWITTER_CLIENT_ID or not settings.TWITTER_CLIENT_SECRET:
        print("[WARNING] Twitter OAuth credentials not configured. Twitter/X integration will not work.")
    else:
        print("[CONFIG] Twitter OAuth credentials loaded")

# ---- Validate PayPal configuration in production ----
if settings.ENV == "production":
    if not settings.PAYPAL_CLIENT_ID or not settings.PAYPAL_CLIENT_SECRET:
        print("[WARNING] PayPal credentials not configured. PayPal integration will not work.")
    elif settings.PAYPAL_MODE == "sandbox":
        print("[CONFIG] PayPal running in SANDBOX mode")
    else:
        print("[CONFIG] PayPal running in LIVE mode")

# ---- Validate MoneyMotion configuration in production (UPDATED) ----
if settings.ENV == "production":
    if not settings.MONEYMOTION_API_KEY:
        print("[WARNING] MoneyMotion API key not configured. MoneyMotion integration will not work.")
    elif settings.MONEYMOTION_MODE == "sandbox":
        print("[CONFIG] MoneyMotion running in SANDBOX mode")
    else:
        print("[CONFIG] MoneyMotion running in LIVE mode")
elif settings.MONEYMOTION_API_KEY:
    # Development mode with credentials - show info
    print(f"[CONFIG] MoneyMotion configured in {settings.MONEYMOTION_MODE.upper()} mode")

# ------------------
# Ensure all dirs exist (again, just to be safe)
# ------------------
settings.MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
settings.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
settings.CLIPS_DIR.mkdir(parents=True, exist_ok=True)
settings.SUBTITLES_DIR.mkdir(parents=True, exist_ok=True)
settings.VIDEOS_DIR.mkdir(parents=True, exist_ok=True)