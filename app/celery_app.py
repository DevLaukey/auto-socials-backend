import logging
import os
from urllib.parse import urlparse, urlunparse

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

_redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Both broker and backend use db 0 (many managed Redis services only support db 0)
_parsed = urlparse(_redis_url)
# Handle potential missing path
if not _parsed.path:
    _broker_url = f"{_redis_url.rstrip('/')}/0"
    _backend_url = f"{_redis_url.rstrip('/')}/0"
else:
    _broker_url = urlunparse(_parsed._replace(path="/0"))
    _backend_url = urlunparse(_parsed._replace(path="/0"))

celery_app = Celery(
    "social_automation",
    broker=_broker_url,
    backend=_backend_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)

# ============================
# Task discovery (CRITICAL)
# ============================

celery_app.autodiscover_tasks(
    [
        "app.workers.post_tasks",
        "app.workers.comment_worker",
        "app.workers.dm_worker", 
    ]
)

logger.info("[CELERY] Task modules auto-discovered")

# ============================
# Celery Beat schedule
# ============================

celery_app.conf.beat_schedule = {
    # YouTube token refresh (every 5 minutes)
    "refresh-youtube-tokens-check": {
        "task": "refresh_youtube_tokens_task",
        "schedule": crontab(minute="*/5"),
    },
    
    # Twitter token refresh (every 30 minutes)
    "refresh-twitter-tokens-check": {
        "task": "refresh_twitter_tokens_task",
        "schedule": crontab(minute="*/30"),
    },
    
    # Process due comments (every minute)
    "process-due-comments": {
        "task": "process_due_comments_task",
        "schedule": crontab(minute="*"),  # Every minute
    },
    
    # Process due DMs (every minute)
    "process-due-dms": {
        "task": "process_due_dms_task",
        "schedule": crontab(minute="*"),  # Every minute
    },
    
    # Check conversations for AI replies (every 5 minutes)
    "check-conversations-for-replies": {
        "task": "check_conversations_for_replies_task",
        "schedule": crontab(minute="*/5"),  # Every 5 minutes
    },
    
    # Clean up old/failed jobs (daily at 2 AM)
    "cleanup-old-jobs": {
        "task": "cleanup_old_jobs_task",
        "schedule": crontab(hour=2, minute=0),  # Daily at 2 AM
    },
}

logger.info("[CELERY] Beat schedule registered with %d tasks", len(celery_app.conf.beat_schedule))

# ============================
# Startup ping task
# ============================

@celery_app.task(name="celery_startup_ping")
def celery_startup_ping():
    logger.info("[CELERY] Startup ping task executed")
    return {"status": "ok", "message": "Celery is running"}


# ============================
# New Task Definitions
# ============================

@celery_app.task(name="refresh_twitter_tokens_task")
def refresh_twitter_tokens_task():
    """Refresh expired Twitter tokens."""
    from app.services.twitter_token_service import refresh_all_twitter_tokens
    logger.info("[CELERY] Running Twitter token refresh task")
    refresh_all_twitter_tokens()
    return {"status": "completed", "task": "refresh_twitter_tokens"}


@celery_app.task(name="process_due_comments_task")
def process_due_comments_task():
    """
    Process comments that are due for execution.
    This task finds all pending comment jobs that are scheduled to run now
    and queues them for execution.
    """
    from app.services.database import get_conn
    from app.workers.comment_worker import execute_comment_job
    
    logger.info("[CELERY] Checking for due comments")
    
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Find all pending comment jobs that are due
            cur.execute("""
                SELECT id
                FROM comment_jobs
                WHERE status = 'pending'
                AND (scheduled_time IS NULL OR scheduled_time <= NOW())
                AND attempts < max_attempts
                ORDER BY scheduled_time ASC NULLS FIRST
                LIMIT 100  -- Process in batches
            """)
            
            jobs = cur.fetchall()
    
    if jobs:
        logger.info(f"[CELERY] Found {len(jobs)} due comment jobs")
        for job in jobs:
            execute_comment_job.delay(job['id'])
    else:
        logger.debug("[CELERY] No due comment jobs found")
    
    return {"status": "completed", "processed": len(jobs)}


@celery_app.task(name="process_due_dms_task")
def process_due_dms_task():
    """
    Process DMs that are due for execution.
    """
    from app.services.database import get_conn
    from app.workers.dm_worker import execute_dm_job
    
    logger.info("[CELERY] Checking for due DMs")
    
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Find all pending DM jobs that are due
            cur.execute("""
                SELECT id
                FROM dm_jobs
                WHERE status = 'pending'
                AND (scheduled_time IS NULL OR scheduled_time <= NOW())
                AND attempts < max_attempts
                ORDER BY scheduled_time ASC NULLS FIRST
                LIMIT 100  -- Process in batches
            """)
            
            jobs = cur.fetchall()
    
    if jobs:
        logger.info(f"[CELERY] Found {len(jobs)} due DM jobs")
        for job in jobs:
            execute_dm_job.delay(job['id'])
    else:
        logger.debug("[CELERY] No due DM jobs found")
    
    return {"status": "completed", "processed": len(jobs)}


@celery_app.task(name="check_conversations_for_replies_task")
def check_conversations_for_replies_task():
    """
    Check for conversations that need AI replies.
    """
    from app.workers.dm_worker import check_conversations_for_replies
    logger.info("[CELERY] Checking conversations for AI replies")
    check_conversations_for_replies()
    return {"status": "completed"}


@celery_app.task(name="cleanup_old_jobs_task")
def cleanup_old_jobs_task():
    """
    Clean up old completed/failed jobs to prevent database bloat.
    Runs daily.
    """
    from app.services.database import get_conn
    from datetime import datetime, timedelta
    
    logger.info("[CELERY] Cleaning up old jobs")
    
    cutoff_date = datetime.utcnow() - timedelta(days=30)
    
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Delete old comment jobs
            cur.execute("""
                DELETE FROM comment_jobs
                WHERE status IN ('completed', 'failed')
                AND created_at < %s
            """, (cutoff_date,))
            comment_deleted = cur.rowcount
            
            # Delete old DM jobs
            cur.execute("""
                DELETE FROM dm_jobs
                WHERE status IN ('completed', 'failed')
                AND created_at < %s
            """, (cutoff_date,))
            dm_deleted = cur.rowcount
            
            # Delete old conversations (optional - be careful with this)
            # Only delete conversations with no recent activity
            cur.execute("""
                DELETE FROM dm_conversations
                WHERE last_message_at < %s
                AND NOT EXISTS (
                    SELECT 1 FROM dm_messages 
                    WHERE conversation_id = dm_conversations.id 
                    AND created_at > %s
                )
            """, (cutoff_date, cutoff_date))
            conv_deleted = cur.rowcount
            
            conn.commit()
    
    logger.info(f"[CELERY] Cleanup complete: {comment_deleted} comment jobs, "
                f"{dm_deleted} DM jobs, {conv_deleted} conversations")
    
    return {
        "status": "completed",
        "comment_jobs_deleted": comment_deleted,
        "dm_jobs_deleted": dm_deleted,
        "conversations_deleted": conv_deleted
    }