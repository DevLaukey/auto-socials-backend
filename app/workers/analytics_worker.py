"""
Analytics worker.

LOGIC:
- Periodically refreshes YouTube statistics
- Updates likes, views, comments
"""

import time
import logging

from app.services.youtube_analytics import fetch_and_update_youtube_stats

logger = logging.getLogger("analytics_worker")
logger.setLevel(logging.INFO)


class AnalyticsWorker:
    def __init__(self, interval_seconds: int = 600):
        self.interval = interval_seconds
        self.running = False

    def start(self):
        self.running = True
        logger.info("[ANALYTICS] Worker started")

        while self.running:
            try:
                logger.info("[ANALYTICS] Refreshing YouTube statistics")
                fetch_and_update_youtube_stats()
                logger.info("[ANALYTICS] Refresh complete")

            except Exception as e:
                logger.exception(f"[ANALYTICS] Error refreshing stats: {e}")

            time.sleep(self.interval)

    def stop(self):
        self.running = False
        logger.info("[ANALYTICS] Worker stopped")
