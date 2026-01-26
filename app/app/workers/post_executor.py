from pydantic import ValidationError
import logging
import os
import time
from pathlib import Path

from app.services.database import (
    update_post_status,
    get_accounts_by_post_id,
    get_instagram_credentials,
    
)


from app.services.auth_database import (
    get_valid_youtube_token, 
    check_and_consume_limit,
     require_active_subscription,
    get_conn as get_auth_conn,
)
from app.services.instagram_service import InstagramService
from app.services.youtube_service import YouTubeService
from app.utils.instagram_lock import InstagramAccountLock


# =========================
# Paths
# =========================

BASE_DIR = Path(__file__).resolve().parents[2]  # backend/
MEDIA_ROOT = BASE_DIR / "media"


# =========================
# Logging
# =========================

logger = logging.getLogger("post_executor")
logger.setLevel(logging.INFO)


# =========================
# Constants
# =========================

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5

# =========================
# Main executor
# =========================

def execute_post(post: dict):
    post_id = post.get("id")
    user_id = post.get("user_id")

    if not post_id:
        logger.error("[EXECUTOR][POST ?] Missing post ID – aborting")
        return

    if not user_id:
        logger.error(f"[EXECUTOR][POST {post_id}] Missing user_id – aborting")
        update_post_status(post_id, "failed")
        return

    logger.info(f"[EXECUTOR][POST {post_id}] ===============================")
    logger.info(f"[EXECUTOR][POST {post_id}] Execution started")

    any_success = False

    try:
        update_post_status(post_id, "processing")
        logger.info(f"[EXECUTOR][POST {post_id}] Status → processing")

        accounts = get_accounts_by_post_id(post_id)
        logger.info(
            f"[EXECUTOR][POST {post_id}] Accounts linked: {len(accounts)}"
        )

        if not accounts:
            raise RuntimeError("No accounts linked to this post")

        caption = _build_caption(
            post.get("title"),
            post.get("description"),
            post.get("hashtags"),
        )

        # --------------------------------------------------
        # GROUP accounts by platform
        # --------------------------------------------------
        accounts_by_platform = {}
        for acc in accounts:
            platform = acc["platform"].lower()
            accounts_by_platform.setdefault(platform, []).append(acc)

        for platform, platform_accounts in accounts_by_platform.items():
            # 🔒 ENFORCE LIMIT ONCE PER PLATFORM
            auth_conn = get_auth_conn()
            try:
                check_and_consume_limit(
                    auth_conn,
                    user_id=user_id,
                    platform=platform,
                    action="post",
                )
            except PermissionError as e:
                logger.error(
                    f"[EXECUTOR][POST {post_id}][{platform}] BLOCKED by subscription: {e}"
                )
                continue

            for account in platform_accounts:
                account_id = account["id"]

                logger.info(
                    f"[EXECUTOR][POST {post_id}][ACCOUNT {account_id}][{platform}] Starting"
                )

                try:
                    if platform == "instagram":
                        _execute_with_retries(
                            lambda: _post_to_instagram(
                                post=post,
                                caption=caption,
                                account_id=account_id,
                            ),
                            MAX_RETRIES,
                            RETRY_DELAY_SECONDS,
                        )
                        any_success = True

                    elif platform == "youtube":
                        creds = get_valid_youtube_token(account_id)
                        if not creds:
                            raise RuntimeError("No valid YouTube credentials")

                        _execute_with_retries(
                            lambda: _post_to_youtube(
                                post=post,
                                caption=caption,
                                creds=creds,
                            ),
                            MAX_RETRIES,
                            RETRY_DELAY_SECONDS,
                        )
                        any_success = True

                    else:
                        logger.warning(
                            f"[EXECUTOR][POST {post_id}][ACCOUNT {account_id}] "
                            f"Unsupported platform '{platform}'"
                        )

                except Exception as account_exc:
                    logger.exception(
                        f"[EXECUTOR][POST {post_id}][ACCOUNT {account_id}][{platform}] FAILED: {account_exc}"
                    )

        if any_success:
            update_post_status(post_id, "posted")
            logger.info(f"[EXECUTOR][POST {post_id}] Status → posted")
        else:
            update_post_status(post_id, "failed")
            logger.error(
                f"[EXECUTOR][POST {post_id}] All accounts failed → status failed"
            )

    except Exception as exc:
        logger.exception(f"[EXECUTOR][POST {post_id}] Fatal execution error: {exc}")
        update_post_status(post_id, "failed")
        raise

    finally:
        logger.info(f"[EXECUTOR][POST {post_id}] ===============================")



# =========================
# Retry wrapper (SAFE)
# =========================

def _execute_with_retries(
    func,
    max_attempts: int = 3,
    delay_seconds: int = 5,
):
    last_exception = None

    for attempt in range(1, max_attempts + 1):
        try:
            func()
            return  # success → stop

        except ValidationError as e:
            # instagrapi bug: upload already succeeded
            logger.warning(
                "[EXECUTOR] Instagrapi validation error AFTER upload — treating as success"
            )
            logger.warning(str(e))
            return 

        except Exception as e:
            last_exception = e
            logger.warning(
                f"[EXECUTOR] Attempt {attempt}/{max_attempts} failed: {e}"
            )

            if attempt < max_attempts:
                time.sleep(delay_seconds)

    raise last_exception


# =========================
# Instagram
# =========================

def _post_to_instagram(post, caption, account_id):
    logger.info(f"[INSTAGRAM][ACCOUNT {account_id}] Acquiring lock")

    lock = InstagramAccountLock(account_id)
    if not lock.acquire():
        raise RuntimeError("Account is currently locked")

    try:
        logger.info(f"[INSTAGRAM][ACCOUNT {account_id}] Lock acquired")

        creds = get_instagram_credentials(account_id)
        if not creds:
            raise RuntimeError("Missing Instagram credentials")

        relative_media = post.get("media_file")
        if not relative_media:
            raise FileNotFoundError("Post has no media_file")

        media_path = MEDIA_ROOT / relative_media

        if not media_path.exists():
            raise FileNotFoundError(f"Media file not found: {media_path}")

        logger.info(f"[INSTAGRAM][ACCOUNT {account_id}] Media verified → {media_path}")

        service = InstagramService(account_id)
        service.execute_post(
            media_path=str(media_path),
            caption=caption,
            post_type=post.get("post_type", "feed"),
            share_to_feed=post.get("share_to_feed", True),
        )

        logger.info(f"[INSTAGRAM][ACCOUNT {account_id}] Post successful")

    finally:
        lock.release()
        logger.info(f"[INSTAGRAM][ACCOUNT {account_id}] Lock released")


# =========================
# YouTube
# =========================

def _post_to_youtube(post, caption, creds):
    media_file = post.get("media_file")
    if not media_file:
        raise FileNotFoundError("Post has no media_file")

    media_path = MEDIA_ROOT / media_file
    if not media_path.exists():
        raise FileNotFoundError(f"Video file not found: {media_path}")

    logger.info("[YOUTUBE] Media verified")

    service = YouTubeService(credentials=creds)

    logger.info("[YOUTUBE] Uploading video")

    service.upload_video(
        video_file=str(media_path),
        title=post.get("title"),
        description=caption,
        tags=post.get("tags"),
        privacy_status=post.get("privacy_status", "private"),
    )

    logger.info("[YOUTUBE] Upload completed")


# =========================
# Helpers
# =========================

def _build_caption(title, description, hashtags):
    parts = []

    if title:
        parts.append(title)

    if description:
        parts.append(description)

    if hashtags:
        cleaned = " ".join(
            f"#{tag.strip('#')}"
            for tag in hashtags.replace(",", " ").split()
            if tag.strip()
        )
        parts.append(cleaned)

    return "\n\n".join(parts)
