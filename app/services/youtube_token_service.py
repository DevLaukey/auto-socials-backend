import logging
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from app.services.database import get_all_youtube_accounts, update_youtube_tokens

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def refresh_all_youtube_tokens():
    """
    Refresh OAuth tokens for all connected YouTube accounts.
    """

    accounts = get_all_youtube_accounts()

    if not accounts:
        logger.info("[YT TOKEN] No YouTube accounts found")
        return

    for account in accounts:
        try:
            creds = Credentials(
                token=account["access_token"],
                refresh_token=account["refresh_token"],
                token_uri="https://oauth2.googleapis.com/token",
                client_id=account["client_id"],
                client_secret=account["client_secret"],
            )

            if not creds.expired or not creds.refresh_token:
                continue

            creds.refresh(Request())

            update_youtube_tokens(
                account_id=account["id"],
                access_token=creds.token,
                expiry=creds.expiry,
            )

            logger.info(
                f"[YT TOKEN] Refreshed tokens for account {account['id']}"
            )

        except Exception as e:
            logger.exception(
                f"[YT TOKEN] Failed to refresh account {account['id']}: {e}"
            )
