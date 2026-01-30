"""
Scheduler worker.

LOGIC:
- Periodically checks for due posts
- Marks them as queued
- Dispatches them via Celery
- Ensures posts are not executed twice
"""

import time
import logging

from app.services.database import (
    get_due_posts,
    update_post_status,
)
from app.workers.post_tasks import execute_scheduled_post

logger = logging.getLogger("scheduler")
logger.setLevel(logging.INFO)


class SchedulerWorker:
    def __init__(self, interval_seconds: int = 30):
        self.interval = interval_seconds
        self.running = False

    def start(self):
        """
        Start the scheduler loop.
        """
        self.running = True
        logger.info("[SCHEDULER] Worker started")

        while self.running:
            try:
                self._check_and_dispatch()
            except Exception as e:
                logger.exception(f"[SCHEDULER] Fatal loop error: {e}")

            time.sleep(self.interval)

    def stop(self):
        """
        Stop the scheduler loop.
        """
        self.running = False
        logger.info("[SCHEDULER] Worker stopped")

    def _check_and_dispatch(self):
        """
        Fetch due posts and dispatch them for execution.
        """
        logger.debug("[SCHEDULER] Checking for due posts")

        due_posts = get_due_posts()

        if not due_posts:
            logger.debug("[SCHEDULER] No due posts found")
            return

        logger.info(f"[SCHEDULER] Found {len(due_posts)} due post(s)")

        for post in due_posts:
            post_id = post[0]

            try:
                logger.info(f"[SCHEDULER][POST {post_id}] Marking as queued")
                update_post_status(post_id, "queued")

                logger.info(
                    f"[SCHEDULER][POST {post_id}] Dispatching to Celery"
                )
                execute_scheduled_post.delay(post_id)

            except Exception as e:
                logger.exception(
                    f"[SCHEDULER][POST {post_id}] Failed to dispatch: {e}"
                )
