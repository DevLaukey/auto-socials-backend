import random
import logging
from datetime import datetime, timezone, timedelta

from app.celery_app import celery_app
from app.workers.post_executor import execute_post
from app.services.database import get_post_details_by_post_id
from app.services.youtube_token_service import refresh_all_youtube_tokens



# ============================
# Logger setup
# ============================

logger = logging.getLogger("post_tasks")
logger.setLevel(logging.INFO)


# ============================
# POST EXECUTION TASK
# ============================

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def execute_scheduled_post(self, post_id: int):
    """
    Celery task that executes a scheduled post.

    FULLY LOGGED:
    - Task received
    - Post lookup
    - Executor delegation
    - Retry & failure visibility
    """

    task_id = self.request.id
    logger.info(
        f"[CELERY][TASK {task_id}] Received execute_scheduled_post for post {post_id}"
    )

    try:
        logger.info(
            f"[CELERY][TASK {task_id}][POST {post_id}] Fetching post from database"
        )

        post = get_post_details_by_post_id(post_id)
        logger.info(f"[POST {post_id}] Post keys: {post.keys()}")


        if not post:
            logger.error(
                f"[CELERY][TASK {task_id}][POST {post_id}] Post not found in DB – aborting"
            )
            return

        logger.info(
            f"[CELERY][TASK {task_id}][POST {post_id}] Post fetched successfully"
        )

        logger.info(
            f"[CELERY][TASK {task_id}][POST {post_id}] Delegating execution to executor"
        )

        execute_post(post)

        logger.info(
            f"[CELERY][TASK {task_id}][POST {post_id}] Execution completed without exception"
        )

    except Exception as exc:
        retry_count = self.request.retries + 1
        logger.exception(
            f"[CELERY][TASK {task_id}][POST {post_id}] "
            f"Execution failed – retry {retry_count}/{self.max_retries}: {exc}"
        )
        raise self.retry(exc=exc)


# ============================
# YOUTUBE TOKEN REFRESH TASK
# ============================

_next_refresh_at = None



@celery_app.task(bind=True, name="refresh_youtube_tokens_task")
def refresh_youtube_tokens_task(self):
    """
    Refresh YouTube tokens at randomized intervals (20–40 minutes).

    FULLY LOGGED:
    - Initial scheduling
    - Skips
    - Refresh execution
    - Failures
    """

    global _next_refresh_at
    now = datetime.now(timezone.utc)

    task_id = self.request.id
    logger.info(f"[YT TOKEN][TASK {task_id}] Token refresh task tick")

    # Initialize on first run
    if _next_refresh_at is None:
        delay_minutes = random.randint(20, 40)
        _next_refresh_at = now + timedelta(minutes=delay_minutes)
        logger.info(
            f"[YT TOKEN][TASK {task_id}] Initial refresh scheduled in {delay_minutes} minutes"
        )
        return

    # Not time yet
    if now < _next_refresh_at:
        logger.debug(
            f"[YT TOKEN][TASK {task_id}] Not time yet – next refresh at {_next_refresh_at}"
        )
        return

    try:
        logger.info(f"[YT TOKEN][TASK {task_id}] Refreshing YouTube tokens")
        refresh_all_youtube_tokens()
        logger.info(f"[YT TOKEN][TASK {task_id}] Token refresh completed successfully")

    except Exception as e:
        logger.exception(
            f"[YT TOKEN][TASK {task_id}] Token refresh FAILED: {e}"
        )

    finally:
        delay_minutes = random.randint(20, 40)
        _next_refresh_at = now + timedelta(minutes=delay_minutes)
        logger.info(
            f"[YT TOKEN][TASK {task_id}] Next refresh scheduled in {delay_minutes} minutes"
        )
