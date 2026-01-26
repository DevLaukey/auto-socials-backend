import logging
from celery import Celery
from celery.schedules import crontab

# ============================
# Logging
# ============================

logger = logging.getLogger("celery")
logger.setLevel(logging.INFO)

logger.info("[CELERY] Initializing Celery application")

# ============================
# Celery App
# ============================

celery_app = Celery(
    "social_automation",
        broker="redis://localhost:6380/0",
        backend="redis://localhost:6380/1",
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

# ============================
# Task discovery (CRITICAL)
# ============================

celery_app.autodiscover_tasks(
    [
        "app.workers.post_tasks",
    ]
)

logger.info("[CELERY] Task modules auto-discovered")

# ============================
# Celery Beat schedule
# ============================

celery_app.conf.beat_schedule = {
    "refresh-youtube-tokens-check": {
        "task": "refresh_youtube_tokens_task",
        "schedule": crontab(minute="*/5"),
    }
}

logger.info("[CELERY] Beat schedule registered")

# ============================
# Startup ping task
# ============================

@celery_app.task(name="celery_startup_ping")
def celery_startup_ping():
    logger.info("[CELERY] Startup ping task executed")
