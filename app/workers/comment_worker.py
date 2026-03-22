"""
Comment automation worker.

Handles:
- Posting comments on posts
- Retry logic
- Rate limiting per platform
"""

import logging
import re
from datetime import datetime

from app.celery_app import celery_app
from app.services.database import get_conn

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
def execute_comment_job(self, comment_job_id: int):
    """Execute a comment job."""
    logger.info(f"[COMMENT WORKER] Starting comment job {comment_job_id}")
    
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Get job details
            cur.execute("""
                SELECT 
                    cj.id, cj.user_id, cj.account_id, cj.post_id,
                    cj.target_url, cj.comment_text, cj.status,
                    cj.attempts, cj.max_attempts,
                    a.platform, a.account_username, a.password
                FROM comment_jobs cj
                JOIN accounts a ON a.id = cj.account_id
                WHERE cj.id = %s
            """, (comment_job_id,))
            
            job = cur.fetchone()
            
            if not job:
                logger.error(f"Comment job {comment_job_id} not found")
                return
            
            # Update to processing
            cur.execute("""
                UPDATE comment_jobs
                SET status = 'processing', attempts = attempts + 1
                WHERE id = %s
            """, (comment_job_id,))
            conn.commit()
    
    try:
        # Determine platform and post comment
        platform = job['platform'].lower()
        
        success = False
        
        if platform == 'instagram':
            success = _post_instagram_comment(
                account_id=job['account_id'],
                username=job['account_username'],
                password=job['password'],
                target_url=job['target_url'],
                comment=job['comment_text']
            )
        elif platform == 'youtube':
            success = _post_youtube_comment(
                account_id=job['account_id'],
                target_url=job['target_url'],
                comment=job['comment_text']
            )
        elif platform == 'twitter':
            success = _post_twitter_comment(
                account_id=job['account_id'],
                target_url=job['target_url'],
                comment=job['comment_text']
            )
        else:
            raise ValueError(f"Unsupported platform: {platform}")
        
        if success:
            # Mark as completed
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE comment_jobs
                        SET status = 'completed', executed_time = NOW()
                        WHERE id = %s
                    """, (comment_job_id,))
                    conn.commit()
            
            logger.info(f"[COMMENT WORKER] Comment job {comment_job_id} completed")
        else:
            raise Exception("Comment posting failed")
            
    except Exception as e:
        logger.error(f"[COMMENT WORKER] Comment job {comment_job_id} failed: {e}")
        
        # Retry logic
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT attempts, max_attempts
                    FROM comment_jobs
                    WHERE id = %s
                """, (comment_job_id,))
                job_status = cur.fetchone()
                
                if job_status and job_status['attempts'] < job_status['max_attempts']:
                    # Retry with exponential backoff
                    retry_delay = 60 * (2 ** (job_status['attempts'] - 1))
                    logger.info(f"Retrying comment job {comment_job_id} in {retry_delay}s")
                    self.retry(countdown=retry_delay)
                else:
                    # Mark as failed
                    cur.execute("""
                        UPDATE comment_jobs
                        SET status = 'failed', error_message = %s
                        WHERE id = %s
                    """, (str(e), comment_job_id))
                    conn.commit()


def _post_instagram_comment(account_id, username, password, target_url, comment):
    """Post comment on Instagram."""
    try:
        from instagrapi import Client
        
        client = Client()
        client.login(username, password)
        
        # Extract media ID from URL
        media_id = client.media_pk_from_url(target_url)
        
        # Post comment
        result = client.media_comment(media_id, comment)
        logger.info(f"Instagram comment posted: {result}")
        return True
    except Exception as e:
        logger.error(f"Instagram comment failed: {e}")
        return False


def _post_youtube_comment(account_id, target_url, comment):
    """Post comment on YouTube."""
    try:
        from app.services.auth_database import get_valid_youtube_token
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
        
        video_id = _extract_video_id(target_url)
        if not video_id:
            raise ValueError(f"Could not extract video ID from URL: {target_url}")
        
        creds = get_valid_youtube_token(account_id)
        if not creds:
            raise ValueError(f"No valid YouTube token for account {account_id}")
        
        youtube = build('youtube', 'v3', credentials=creds)
        
        request = youtube.commentThreads().insert(
            part='snippet',
            body={
                'snippet': {
                    'videoId': video_id,
                    'topLevelComment': {
                        'snippet': {
                            'textOriginal': comment
                        }
                    }
                }
            }
        )
        response = request.execute()
        logger.info(f"YouTube comment posted: {response.get('id')}")
        return True
        
    except HttpError as e:
        logger.error(f"YouTube API error: {e}")
        return False
    except Exception as e:
        logger.error(f"YouTube comment failed: {e}")
        return False


def _post_twitter_comment(account_id, target_url, comment):
    """Post comment/reply on Twitter."""
    try:
        from app.services.auth_database import get_twitter_token
        from app.services.twitter_service import TwitterService
        
        tweet_id = _extract_tweet_id(target_url)
        if not tweet_id:
            raise ValueError(f"Could not extract tweet ID from URL: {target_url}")
        
        creds = get_twitter_token(account_id)
        if not creds:
            raise ValueError(f"No Twitter token for account {account_id}")
        
        service = TwitterService(account_id, creds)
        result = service.post_tweet(
            text=comment,
            reply_to_tweet_id=tweet_id
        )
        
        logger.info(f"Twitter reply posted: {result.get('tweet_id')}")
        return True
        
    except Exception as e:
        logger.error(f"Twitter comment failed: {e}")
        return False


def _extract_video_id(url: str) -> str:
    """Extract YouTube video ID from URL."""
    patterns = [
        r'(?:youtube\.com\/watch\?v=)([\w-]+)',
        r'(?:youtu\.be\/)([\w-]+)',
        r'(?:youtube\.com\/embed\/)([\w-]+)',
        r'(?:youtube\.com\/v\/)([\w-]+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return url


def _extract_tweet_id(url: str) -> str:
    """Extract tweet ID from Twitter URL."""
    patterns = [
        r'(?:twitter\.com\/\w+\/status\/)(\d+)',
        r'(?:x\.com\/\w+\/status\/)(\d+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return url