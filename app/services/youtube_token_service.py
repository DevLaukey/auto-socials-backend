import os
import logging
from datetime import datetime, timezone

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from app.services.database import (
    get_all_youtube_accounts_with_tokens,
    update_youtube_tokens,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


YOUTUBE_CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID")
YOUTUBE_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET")
TOKEN_URI = "https://oauth2.googleapis.com/token"


def refresh_all_youtube_tokens():
    """
    Refresh OAuth tokens for all connected YouTube accounts.
    Uses tokens table + accounts table (schema-accurate).
    """

    if not YOUTUBE_CLIENT_ID or not YOUTUBE_CLIENT_SECRET:
        logger.error("[YT TOKEN] Missing YOUTUBE_CLIENT_ID or YOUTUBE_CLIENT_SECRET")
        return

    accounts = get_all_youtube_accounts_with_tokens()

    if not accounts:
        logger.info("[YT TOKEN] No YouTube accounts found")
        return

    for account in accounts:
        account_id = account["account_id"]

        try:
            creds = Credentials(
                token=account["access_token"],
                refresh_token=account["refresh_token"],
                token_uri=TOKEN_URI,
                client_id=YOUTUBE_CLIENT_ID,
                client_secret=YOUTUBE_CLIENT_SECRET,
            )

            # Skip if token is still valid
            if creds.expiry and creds.expiry.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc):
                continue

            if not creds.refresh_token:
                logger.warning(
                    f"[YT TOKEN] Account {account_id} has no refresh token – skipping"
                )
                continue

            creds.refresh(Request())

            expires_at = int(creds.expiry.timestamp())

            update_youtube_tokens(
                account_id=account_id,
                access_token=creds.token,
                expires_at=expires_at,
            )

            logger.info(f"[YT TOKEN] Refreshed tokens for account {account_id}")

        except Exception as e:
            logger.exception(
                f"[YT TOKEN] Failed to refresh tokens for account {account_id}: {e}"
            )
