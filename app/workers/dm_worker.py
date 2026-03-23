"""
DM automation worker.

Handles:
- Sending scheduled DMs
- AI-powered replies
- Conversation management
"""

import logging
from datetime import datetime, timezone

from app.celery_app import celery_app
from app.services.dm_service import DMService
from app.services.database import connect

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
def execute_dm_job(self, dm_job_id: int):
    """Execute a DM job."""
    logger.info(f"[DM WORKER] Starting DM job {dm_job_id}")

    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                dj.id, dj.user_id, dj.account_id,
                dj.recipient_username, dj.message_text,
                dj.status, dj.attempts, dj.max_attempts,
                a.platform
            FROM dm_jobs dj
            JOIN accounts a ON a.id = dj.account_id
            WHERE dj.id = %s
        """, (dm_job_id,))

        job = cur.fetchone()

        if not job:
            logger.error(f"DM job {dm_job_id} not found")
            return

        # Update to processing
        cur.execute("""
            UPDATE dm_jobs
            SET status = 'processing', attempts = attempts + 1
            WHERE id = %s
        """, (dm_job_id,))
        conn.commit()
    finally:
        conn.close()

    try:
        # Initialize DM service
        dm_service = DMService(
            account_id=job['account_id'],
            platform=job['platform'].lower()
        )

        # Send the DM
        success = dm_service.send_dm(
            recipient=job['recipient_username'],
            message=job['message_text'],
            dm_job_id=dm_job_id
        )

        if success:
            conn = connect()
            try:
                cur = conn.cursor()
                cur.execute("""
                    UPDATE dm_jobs
                    SET status = 'completed', executed_time = NOW()
                    WHERE id = %s
                """, (dm_job_id,))
                conn.commit()
            finally:
                conn.close()

            logger.info(f"[DM WORKER] DM job {dm_job_id} completed")
        else:
            raise Exception("DM sending failed")

    except Exception as e:
        logger.error(f"[DM WORKER] DM job {dm_job_id} failed: {e}")

        conn = connect()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT attempts, max_attempts
                FROM dm_jobs
                WHERE id = %s
            """, (dm_job_id,))
            job_status = cur.fetchone()

            if job_status and job_status['attempts'] < job_status['max_attempts']:
                retry_delay = 60 * (2 ** (job_status['attempts'] - 1))
                logger.info(f"Retrying DM job {dm_job_id} in {retry_delay}s")
                self.retry(countdown=retry_delay)
            else:
                cur.execute("""
                    UPDATE dm_jobs
                    SET status = 'failed', error_message = %s
                    WHERE id = %s
                """, (str(e), dm_job_id))
                conn.commit()
        finally:
            conn.close()


@celery_app.task
def check_conversations_for_replies():
    """
    Periodically check all conversations that might need AI replies.
    This should be scheduled via Celery beat.
    """
    logger.info("Checking conversations for AI replies")

    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                dc.id as conversation_id,
                dc.account_id,
                dc.recipient_username,
                a.platform,
                MAX(m.created_at) as last_message_time,
                COUNT(*) FILTER (WHERE m.is_from_me = TRUE) as our_messages
            FROM dm_conversations dc
            JOIN accounts a ON a.id = dc.account_id
            JOIN dm_messages m ON m.conversation_id = dc.id
            WHERE m.is_from_me = FALSE  -- Last message was from them
            AND dc.last_message_at < NOW() - INTERVAL '30 minutes'  -- No recent reply
            GROUP BY dc.id, dc.account_id, dc.recipient_username, a.platform
            HAVING COUNT(*) FILTER (WHERE m.is_from_me = TRUE) < 10  -- Not too many replies
            AND MAX(m.created_at) > NOW() - INTERVAL '24 hours'  -- Active conversation
            ORDER BY dc.last_message_at ASC
            LIMIT 50  -- Process in batches
        """)
        conversations = cur.fetchall()
    finally:
        conn.close()

    for conv in conversations:
        try:
            logger.info(f"Processing AI reply for conversation {conv['conversation_id']}")

            schedule_dm_reply.delay(
                conversation_id=conv['conversation_id'],
                account_id=conv['account_id'],
                recipient=conv['recipient_username']
            )

        except Exception as e:
            logger.error(f"Failed to schedule reply for conversation {conv['conversation_id']}: {e}")


@celery_app.task
def schedule_dm_reply(conversation_id: int, account_id: int, recipient: str):
    """
    Schedule an AI-powered reply for a conversation.
    """
    logger.info(f"Generating AI reply for conversation {conversation_id}")

    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                COUNT(*) as recent_replies,
                MAX(created_at) as last_reply
            FROM dm_messages dm
            WHERE conversation_id = %s
            AND dm.is_from_me = TRUE
            AND dm.created_at > NOW() - INTERVAL '1 hour'
        """, (conversation_id,))

        stats = cur.fetchone()

        if stats and stats['recent_replies'] >= 3:
            logger.info(f"Rate limit hit for conversation {conversation_id}, skipping")
            return

        cur.execute("""
            SELECT platform FROM accounts WHERE id = %s
        """, (account_id,))
        account = cur.fetchone()

        if not account:
            logger.error(f"Account {account_id} not found")
            return
    finally:
        conn.close()

    # Generate and send AI reply
    try:
        dm_service = DMService(account_id, account['platform'].lower())
        success = dm_service.send_ai_dm(recipient)

        if success:
            logger.info(f"AI reply sent for conversation {conversation_id}")
        else:
            logger.warning(f"Failed to send AI reply for conversation {conversation_id}")

    except Exception as e:
        logger.error(f"Error sending AI reply for conversation {conversation_id}: {e}")
