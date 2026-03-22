"""
Endpoints for creating and scheduling posts.

This layer stores intent and schedules background execution via Celery.

PAYMENT FLOW:
1. User calls POST /posts/initiate-payment with post data
2. Backend stores post data and returns payment URL/order info
3. User completes payment
4. Webhook confirms payment
5. Post is automatically created and scheduled

NEW FEATURES:
- Twitter/X posting support
- AI-powered comments automation
- AI-powered DMs automation
- PayPal payment support
"""

from fastapi import APIRouter, HTTPException, Depends, status, BackgroundTasks
from pydantic import BaseModel, Field, validator
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Literal, Dict, Any
import random
import logging

from app.services.database import (
    add_post,
    get_post_status_by_id,
    get_post_details_by_post_id,
    get_all_posts_for_user,
    get_db,
    reset_post_for_repost
)
from app.services.auth_database import (
    get_conn as get_auth_conn,
    create_post_payment_intent,
    get_post_payment_status,
    get_user_post_payments,
    check_and_consume_limit,
    require_active_subscription,
)
from app.api.deps import get_current_user
from app.workers.post_tasks import execute_scheduled_post
from app.workers.comment_worker import execute_comment_job
from app.workers.dm_worker import execute_dm_job
from app.services.ai_comment_service import AICommentService
from app.config import settings

logger = logging.getLogger(__name__)

# ZeroID payment URL for post payments
ZEROID_POST_PAYMENT_URL = "https://app.zeroid.cc/paylink/89e8d2c5-be5c-4953-8b2f-43cd0bafcd95"


router = APIRouter(prefix="/posts", tags=["posts"])


# ======================
# Enhanced Schemas
# ======================

class PostCreate(BaseModel):
    # Core
    account_ids: List[int] = Field(default_factory=list)
    group_ids: Optional[List[int]] = None
    media_file: str

    # Caption
    title: Optional[str] = ""
    description: Optional[str] = ""
    hashtags: Optional[str] = ""

    # YouTube
    tags: Optional[List[str]] = None
    privacy_status: Optional[Literal["public", "private", "unlisted"]] = None

    # Instagram
    post_type: Literal["feed", "reel", "story"] = "feed"
    cover_image: Optional[str] = None
    audio_name: Optional[str] = None
    location: Optional[str] = None
    disable_comments: Optional[bool] = False
    share_to_feed: Optional[bool] = True

    # Twitter/X specific
    is_thread: Optional[bool] = False
    thread_tweets: Optional[List[str]] = None  # For multi-tweet threads
    quote_tweet_id: Optional[str] = None  # For quote tweets
    reply_to_tweet_id: Optional[str] = None  # For replies

    # Scheduling
    scheduled_time: Optional[datetime] = None

    @validator('thread_tweets')
    def validate_thread(cls, v, values):
        if values.get('is_thread') and (not v or len(v) < 2):
            raise ValueError('Thread must contain at least 2 tweets')
        return v


class PostCreateWithEngagement(PostCreate):
    """
    Extended post creation with AI engagement automation.
    """
    # AI Comments settings
    ai_comments_enabled: bool = False
    ai_comments_count: int = 3
    ai_comments_style: Literal["casual", "funny", "thoughtful", "question", "supportive"] = "casual"
    ai_comments_delay_minutes: int = 10  # Delay after posting
    ai_comments_spread: bool = True  # Spread comments over time
    
    # AI DMs settings
    ai_dms_enabled: bool = False
    ai_dms_target_users: Optional[List[str]] = None
    ai_dms_message_style: Literal["friendly", "professional", "casual", "enthusiastic", "helpful"] = "friendly"
    ai_dms_delay_minutes: int = 5  # Delay after posting


class PostResponse(BaseModel):
    id: int
    status: str
    scheduled_time: Optional[datetime]
    platform_counts: Optional[Dict[str, int]] = None  # Number of posts per platform


class PaymentInitiationResponse(BaseModel):
    payment_id: str
    payment_url: str
    message: str


class PaymentMethodResponse(BaseModel):
    payment_method: str
    action: str
    endpoint: Optional[str] = None
    data: Optional[Dict] = None
    payment_id: Optional[str] = None
    payment_url: Optional[str] = None


class CommentJobResponse(BaseModel):
    job_id: int
    account_id: int
    target_url: str
    comment: str
    scheduled_time: Optional[datetime]
    status: str


class DMJobResponse(BaseModel):
    job_id: int
    account_id: int
    recipient: str
    message: str
    scheduled_time: Optional[datetime]
    status: str


# ======================
# Helper Functions
# ======================

def _get_platform_for_account(account_id: int, db) -> str:
    """Get platform for an account ID."""
    cursor = db.cursor()
    cursor.execute(
        "SELECT platform FROM accounts WHERE id = %s",
        (account_id,)
    )
    row = cursor.fetchone()
    return row[0].lower() if row else None


def _build_post_url(platform: str, post_id: int, account_username: str = None) -> str:
    """
    Build a URL to the post for comment targeting.
    This is used by the AI comment system to know where to post comments.
    """
    # In a real implementation, you'd store the actual post URLs after posting
    # This is a placeholder - you might need to store these in the database
    from app.config import settings
    
    if platform == "youtube":
        # YouTube video ID would be stored in posts table after posting
        return f"https://youtube.com/watch?v=PLACEHOLDER_{post_id}"
    elif platform == "instagram":
        # Instagram post URL format
        return f"https://instagram.com/p/PLACEHOLDER_{post_id}"
    elif platform == "twitter":
        # Twitter tweet URL format
        return f"https://twitter.com/i/web/status/PLACEHOLDER_{post_id}"
    else:
        return f"https://{platform}.com/post/{post_id}"


def _schedule_ai_comments(
    post_id: int,
    user_id: int,
    account_ids: List[int],
    post_content: str,
    settings: Dict[str, Any],
    db
):
    """
    Schedule AI-generated comments for a post.
    """
    from app.services.database import get_conn
    
    ai_service = AICommentService("general")
    scheduled_jobs = []
    
    with get_conn() as app_conn:
        with app_conn.cursor() as cur:
            for account_id in account_ids:
                # Get account platform
                cur.execute(
                    "SELECT platform FROM accounts WHERE id = %s",
                    (account_id,)
                )
                account = cur.fetchone()
                if not account:
                    continue
                
                platform = account[0].lower()
                
                # Generate comments
                context = {
                    "hashtags": post_content.get('hashtags'),
                    "post_type": platform
                }
                
                comments = ai_service.generate_comments(
                    post_content=post_content.get('title') or post_content.get('description') or "New post",
                    post_type=platform,
                    count=settings['ai_comments_count'],
                    style=settings['ai_comments_style'],
                    context=context
                )
                
                # Build target URL (you might want to store actual URLs after posting)
                target_url = _build_post_url(platform, post_id, None)
                
                # Schedule each comment with delays
                base_delay = settings['ai_comments_delay_minutes'] * 60
                
                for i, comment in enumerate(comments):
                    if settings.get('ai_comments_spread', True):
                        # Spread comments with random delays between 2-10 minutes apart
                        delay_seconds = base_delay + (i * random.randint(120, 600))
                    else:
                        # All comments at once after initial delay
                        delay_seconds = base_delay
                    
                    scheduled_time = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
                    
                    # Insert comment job
                    cur.execute("""
                        INSERT INTO comment_jobs (
                            user_id, post_id, account_id, target_url,
                            comment_text, scheduled_time, status, max_attempts
                        ) VALUES (%s, %s, %s, %s, %s, %s, 'pending', 3)
                        RETURNING id
                    """, (
                        user_id, post_id, account_id, target_url,
                        comment, scheduled_time
                    ))
                    
                    job_id = cur.fetchone()[0]
                    scheduled_jobs.append({
                        "job_id": job_id,
                        "account_id": account_id,
                        "comment": comment,
                        "scheduled_time": scheduled_time
                    })
                    
                    # Schedule Celery task
                    execute_comment_job.apply_async(
                        args=[job_id],
                        eta=scheduled_time
                    )
            
            app_conn.commit()
    
    return scheduled_jobs


def _schedule_ai_dms(
    post_id: int,
    user_id: int,
    account_ids: List[int],
    target_users: List[str],
    settings: Dict[str, Any],
    db
):
    """
    Schedule AI-generated DMs to promote a post.
    """
    from app.services.database import get_conn
    
    ai_service = AICommentService("general")
    scheduled_jobs = []
    
    # Use first account for DMs (or you could round-robin)
    account_id = account_ids[0] if account_ids else None
    if not account_id:
        return []
    
    with get_conn() as app_conn:
        with app_conn.cursor() as cur:
            # Get account platform
            cur.execute(
                "SELECT platform FROM accounts WHERE id = %s",
                (account_id,)
            )
            account = cur.fetchone()
            if not account:
                return []
            
            platform = account[0].lower()
            
            # Generate message template
            post_content = f"Check out my new post!"
            if settings.get('custom_message'):
                message_template = settings['custom_message']
            else:
                # Generate a friendly message
                message = ai_service.generate_dm_reply(
                    conversation_history=[],
                    recipient_info={"username": "{username}"},
                    tone=settings['ai_dms_message_style']
                )
                message_template = message
            
            # Schedule DMs to each target user
            base_delay = settings.get('ai_dms_delay_minutes', 5) * 60
            
            for i, username in enumerate(target_users):
                # Add small delays between DMs to avoid rate limits
                delay_seconds = base_delay + (i * 30)
                scheduled_time = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
                
                # Personalize message
                personalized_message = message_template.replace("{username}", username)
                
                # Insert DM job
                cur.execute("""
                    INSERT INTO dm_jobs (
                        user_id, account_id, recipient_username, message_text,
                        scheduled_time, status, max_attempts
                    ) VALUES (%s, %s, %s, %s, %s, 'pending', 3)
                    RETURNING id
                """, (
                    user_id, account_id, username, personalized_message,
                    scheduled_time
                ))
                
                job_id = cur.fetchone()[0]
                scheduled_jobs.append({
                    "job_id": job_id,
                    "account_id": account_id,
                    "recipient": username,
                    "message": personalized_message,
                    "scheduled_time": scheduled_time
                })
                
                # Schedule Celery task
                execute_dm_job.apply_async(
                    args=[job_id],
                    eta=scheduled_time
                )
            
            app_conn.commit()
    
    return scheduled_jobs


# ======================
# Payment Routes
# ======================

@router.post("/initiate-payment", response_model=PaymentInitiationResponse)
def initiate_post_payment(
    payload: PostCreate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Initiate payment for creating a post using ZeroID."""
    # Normalize scheduled_time to UTC
    scheduled_time = payload.scheduled_time
    if scheduled_time:
        if scheduled_time.tzinfo is None:
            scheduled_time = scheduled_time.replace(tzinfo=timezone.utc)
        else:
            scheduled_time = scheduled_time.astimezone(timezone.utc)

    # Resolve accounts from groups
    final_account_ids = set(payload.account_ids or [])

    if payload.group_ids:
        cursor = db.cursor()
        placeholders = ",".join("%s" for _ in payload.group_ids)

        cursor.execute(
            f"""
            SELECT DISTINCT account_id
            FROM group_accounts
            WHERE group_id IN ({placeholders})
            """,
            tuple(payload.group_ids),
        )

        final_account_ids.update(row[0] for row in cursor.fetchall())

    final_account_ids = list(final_account_ids)

    if not final_account_ids:
        raise HTTPException(
            status_code=400,
            detail="No accounts resolved for this post",
        )

    # Check subscription limits for each platform
    with get_auth_conn() as auth_conn:
        for account_id in final_account_ids:
            cursor = db.cursor()
            cursor.execute(
                "SELECT platform FROM accounts WHERE id = %s",
                (account_id,)
            )
            platform = cursor.fetchone()[0].lower()
            
            try:
                # Check if user has available post slots for this platform
                check_and_consume_limit(
                    auth_conn,
                    user_id=current_user["id"],
                    platform=platform,
                    action="post"
                )
            except PermissionError as e:
                raise HTTPException(status_code=403, detail=str(e))

    # Store post data for later creation
    post_data = {
        "account_ids": final_account_ids,
        "media_file": payload.media_file,
        "title": payload.title,
        "description": payload.description,
        "hashtags": payload.hashtags,
        "tags": payload.tags,
        "privacy_status": payload.privacy_status,
        "post_type": payload.post_type,
        "cover_image": payload.cover_image,
        "audio_name": payload.audio_name,
        "location": payload.location,
        "disable_comments": payload.disable_comments,
        "share_to_feed": payload.share_to_feed,
        "is_thread": getattr(payload, 'is_thread', False),
        "thread_tweets": getattr(payload, 'thread_tweets', None),
        "quote_tweet_id": getattr(payload, 'quote_tweet_id', None),
        "reply_to_tweet_id": getattr(payload, 'reply_to_tweet_id', None),
        "scheduled_time": scheduled_time.isoformat() if scheduled_time else None,
    }

    # Create payment intent with post data
    with get_auth_conn() as auth_conn:
        payment_id = create_post_payment_intent(
            auth_conn,
            user_id=current_user["id"],
            post_data=post_data,
            amount=100,  # KES - adjust as needed
        )

    return PaymentInitiationResponse(
        payment_id=str(payment_id),
        payment_url=f"{ZEROID_POST_PAYMENT_URL}?reference={payment_id}",
        message="Complete payment to create your post",
    )


@router.post("/initiate-payment/select-method")
def initiate_post_payment_with_method(
    payload: PostCreate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Initiate payment for creating a post with selectable payment method.
    Returns appropriate response based on payment method.
    """
    # Normalize scheduled_time to UTC
    scheduled_time = payload.scheduled_time
    if scheduled_time:
        if scheduled_time.tzinfo is None:
            scheduled_time = scheduled_time.replace(tzinfo=timezone.utc)
        else:
            scheduled_time = scheduled_time.astimezone(timezone.utc)

    # Resolve accounts from groups
    final_account_ids = set(payload.account_ids or [])

    if payload.group_ids:
        cursor = db.cursor()
        placeholders = ",".join("%s" for _ in payload.group_ids)

        cursor.execute(
            f"""
            SELECT DISTINCT account_id
            FROM group_accounts
            WHERE group_id IN ({placeholders})
            """,
            tuple(payload.group_ids),
        )

        final_account_ids.update(row[0] for row in cursor.fetchall())

    final_account_ids = list(final_account_ids)

    if not final_account_ids:
        raise HTTPException(
            status_code=400,
            detail="No accounts resolved for this post",
        )

    # Check subscription limits for each platform
    with get_auth_conn() as auth_conn:
        for account_id in final_account_ids:
            cursor = db.cursor()
            cursor.execute(
                "SELECT platform FROM accounts WHERE id = %s",
                (account_id,)
            )
            platform = cursor.fetchone()[0].lower()
            
            try:
                check_and_consume_limit(
                    auth_conn,
                    user_id=current_user["id"],
                    platform=platform,
                    action="post"
                )
            except PermissionError as e:
                raise HTTPException(status_code=403, detail=str(e))

    # Store post data for later creation
    post_data = {
        "account_ids": final_account_ids,
        "media_file": payload.media_file,
        "title": payload.title,
        "description": payload.description,
        "hashtags": payload.hashtags,
        "tags": payload.tags,
        "privacy_status": payload.privacy_status,
        "post_type": payload.post_type,
        "cover_image": payload.cover_image,
        "audio_name": payload.audio_name,
        "location": payload.location,
        "disable_comments": payload.disable_comments,
        "share_to_feed": payload.share_to_feed,
        "is_thread": getattr(payload, 'is_thread', False),
        "thread_tweets": getattr(payload, 'thread_tweets', None),
        "quote_tweet_id": getattr(payload, 'quote_tweet_id', None),
        "reply_to_tweet_id": getattr(payload, 'reply_to_tweet_id', None),
        "scheduled_time": scheduled_time.isoformat() if scheduled_time else None,
    }

    # Get payment method from payload
    payment_method = getattr(payload, 'payment_method', 'zeroid').lower()
    return_url = getattr(payload, 'return_url', None)
    cancel_url = getattr(payload, 'cancel_url', None)

    if payment_method == "zeroid":
        # Create payment intent
        with get_auth_conn() as auth_conn:
            payment_id = create_post_payment_intent(
                auth_conn,
                user_id=current_user["id"],
                post_data=post_data,
                amount=100,
            )

        return PaymentMethodResponse(
            payment_method="zeroid",
            action="redirect",
            payment_id=str(payment_id),
            payment_url=f"{ZEROID_POST_PAYMENT_URL}?reference={payment_id}",
        )

    elif payment_method == "paypal":
        # Return PayPal order creation info
        return PaymentMethodResponse(
            payment_method="paypal",
            action="create_paypal_order",
            endpoint="/paypal/create-post-order",
            data={
                "post_data": post_data,
                "return_url": return_url,
                "cancel_url": cancel_url
            }
        )

    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported payment method: {payment_method}"
        )


@router.post("/initiate-payment/paypal")
def initiate_post_payment_paypal(
    payload: PostCreate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Initiate PayPal payment for creating a post.
    Returns PayPal order creation info.
    """
    # Normalize scheduled_time to UTC
    scheduled_time = payload.scheduled_time
    if scheduled_time:
        if scheduled_time.tzinfo is None:
            scheduled_time = scheduled_time.replace(tzinfo=timezone.utc)
        else:
            scheduled_time = scheduled_time.astimezone(timezone.utc)

    # Resolve accounts from groups
    final_account_ids = set(payload.account_ids or [])

    if payload.group_ids:
        cursor = db.cursor()
        placeholders = ",".join("%s" for _ in payload.group_ids)

        cursor.execute(
            f"""
            SELECT DISTINCT account_id
            FROM group_accounts
            WHERE group_id IN ({placeholders})
            """,
            tuple(payload.group_ids),
        )

        final_account_ids.update(row[0] for row in cursor.fetchall())

    final_account_ids = list(final_account_ids)

    if not final_account_ids:
        raise HTTPException(
            status_code=400,
            detail="No accounts resolved for this post",
        )

    # Check subscription limits for each platform
    with get_auth_conn() as auth_conn:
        for account_id in final_account_ids:
            cursor = db.cursor()
            cursor.execute(
                "SELECT platform FROM accounts WHERE id = %s",
                (account_id,)
            )
            platform = cursor.fetchone()[0].lower()
            
            try:
                check_and_consume_limit(
                    auth_conn,
                    user_id=current_user["id"],
                    platform=platform,
                    action="post"
                )
            except PermissionError as e:
                raise HTTPException(status_code=403, detail=str(e))

    # Store post data for later creation
    post_data = {
        "account_ids": final_account_ids,
        "media_file": payload.media_file,
        "title": payload.title,
        "description": payload.description,
        "hashtags": payload.hashtags,
        "tags": payload.tags,
        "privacy_status": payload.privacy_status,
        "post_type": payload.post_type,
        "cover_image": payload.cover_image,
        "audio_name": payload.audio_name,
        "location": payload.location,
        "disable_comments": payload.disable_comments,
        "share_to_feed": payload.share_to_feed,
        "is_thread": getattr(payload, 'is_thread', False),
        "thread_tweets": getattr(payload, 'thread_tweets', None),
        "quote_tweet_id": getattr(payload, 'quote_tweet_id', None),
        "reply_to_tweet_id": getattr(payload, 'reply_to_tweet_id', None),
        "scheduled_time": scheduled_time.isoformat() if scheduled_time else None,
    }

    # Return PayPal order creation info for frontend
    return PaymentMethodResponse(
        payment_method="paypal",
        action="create_paypal_order",
        endpoint="/paypal/create-post-order",
        data={
            "post_data": post_data,
            "return_url": getattr(payload, 'return_url', None),
            "cancel_url": getattr(payload, 'cancel_url', None)
        }
    )


@router.get("/payment-status/{payment_id}")
def check_payment_status(
    payment_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Check if a post payment has been completed."""
    payment = get_post_payment_status(payment_id)

    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    if payment["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    return {
        "payment_id": str(payment["id"]),
        "status": payment["status"],
        "is_paid": payment["status"] == "paid",
        "payment_method": payment.get("payment_method", "zeroid"),
        "created_at": payment["created_at"],
        "updated_at": payment["updated_at"],
    }


@router.get("/my-payments")
def list_my_post_payments(
    status_filter: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """List all post payment intents for the current user."""
    payments = get_user_post_payments(current_user["id"], status_filter)

    return [
        {
            "payment_id": str(p["id"]),
            "status": p["status"],
            "is_paid": p["status"] == "paid",
            "payment_method": p.get("payment_method", "zeroid"),
            "amount": p["amount"],
            "currency": p["currency"],
            "created_at": p["created_at"],
            "updated_at": p["updated_at"],
        }
        for p in payments
    ]


@router.get("/payment-methods")
def get_post_payment_methods():
    """
    Get available payment methods for post creation.
    """
    methods = [
        {
            "id": "zeroid",
            "name": "ZeroID",
            "description": "Pay with ZeroID",
            "icon": "https://app.zeroid.cc/favicon.ico",
            "enabled": True,
            "amount": 100,
            "currency": "KES"
        }
    ]
    
    # Add PayPal if configured
    if settings.PAYPAL_CLIENT_ID and settings.PAYPAL_CLIENT_SECRET:
        methods.append({
            "id": "paypal",
            "name": "PayPal",
            "description": "Pay with PayPal account or credit card",
            "icon": "https://www.paypal.com/favicon.ico",
            "enabled": True,
            "amount": 1.00,
            "currency": "USD"
        })

    return {"payment_methods": methods}


# ======================
# Main Post Routes
# ======================

@router.post("/", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
def create_post(
    payload: PostCreate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Create a post and schedule it via Celery.
    Supports Instagram, YouTube, and Twitter/X.
    """
    # Normalize scheduled_time to UTC
    scheduled_time = payload.scheduled_time
    if scheduled_time:
        if scheduled_time.tzinfo is None:
            scheduled_time = scheduled_time.replace(tzinfo=timezone.utc)
        else:
            scheduled_time = scheduled_time.astimezone(timezone.utc)

    # Resolve accounts from groups
    final_account_ids = set(payload.account_ids or [])

    if payload.group_ids:
        cursor = db.cursor()
        placeholders = ",".join("%s" for _ in payload.group_ids)

        cursor.execute(
            f"""
            SELECT DISTINCT account_id
            FROM group_accounts
            WHERE group_id IN ({placeholders})
            """,
            tuple(payload.group_ids),
        )

        final_account_ids.update(row[0] for row in cursor.fetchall())

    final_account_ids = list(final_account_ids)

    if not final_account_ids:
        raise HTTPException(
            status_code=400,
            detail="No accounts resolved for this post",
        )

    # Check subscription limits for each platform
    platform_counts = {}
    with get_auth_conn() as auth_conn:
        # First, verify user has active subscription
        subscription = require_active_subscription(auth_conn, current_user["id"])
        
        for account_id in final_account_ids:
            cursor = db.cursor()
            cursor.execute(
                "SELECT platform FROM accounts WHERE id = %s",
                (account_id,)
            )
            platform = cursor.fetchone()[0].lower()
            
            # Count per platform
            platform_counts[platform] = platform_counts.get(platform, 0) + 1
            
            try:
                # Check if user has available post slots for this platform
                check_and_consume_limit(
                    auth_conn,
                    user_id=current_user["id"],
                    platform=platform,
                    action="post"
                )
            except PermissionError as e:
                raise HTTPException(status_code=403, detail=str(e))

    try:
        post_id = add_post(
            user_id=current_user["id"], 
            account_ids=final_account_ids,
            filename=payload.media_file,

            # Caption
            title=payload.title,
            description=payload.description,
            hashtags=payload.hashtags,

            # YouTube
            tags=payload.tags,
            privacy_status=payload.privacy_status,

            # Instagram
            post_type=payload.post_type,
            cover_image=payload.cover_image,
            audio_name=payload.audio_name,
            location=payload.location,
            disable_comments=payload.disable_comments,
            share_to_feed=payload.share_to_feed,

            # Scheduling
            scheduled_time=scheduled_time,
        )

        # Store Twitter-specific data if needed
        if hasattr(payload, 'is_thread') and payload.is_thread:
            # You might want to store thread data in a separate table
            pass

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create post: {str(e)}",
        )

    # Schedule Celery task
    if scheduled_time:
        execute_scheduled_post.apply_async(
            args=[post_id],
            eta=scheduled_time,
        )
    else:
        execute_scheduled_post.delay(post_id)

    return PostResponse(
        id=post_id,
        status="Pending",
        scheduled_time=scheduled_time,
        platform_counts=platform_counts,
    )


@router.post("/with-engagement", response_model=dict)
def create_post_with_engagement(
    payload: PostCreateWithEngagement,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Create a post with AI-powered engagement automation.
    This includes automatic comments and DMs.
    """
    # First create the base post
    post_response = create_post(payload, current_user, db)
    post_id = post_response.id
    
    engagement_jobs = {
        "comments": [],
        "dms": []
    }
    
    # Schedule AI comments if enabled
    if payload.ai_comments_enabled:
        post_content = {
            "title": payload.title,
            "description": payload.description,
            "hashtags": payload.hashtags
        }
        
        comment_settings = {
            "ai_comments_count": payload.ai_comments_count,
            "ai_comments_style": payload.ai_comments_style,
            "ai_comments_delay_minutes": payload.ai_comments_delay_minutes,
            "ai_comments_spread": True
        }
        
        comment_jobs = _schedule_ai_comments(
            post_id=post_id,
            user_id=current_user["id"],
            account_ids=payload.account_ids,
            post_content=post_content,
            settings=comment_settings,
            db=db
        )
        
        engagement_jobs["comments"] = comment_jobs
    
    # Schedule AI DMs if enabled and targets provided
    if payload.ai_dms_enabled and payload.ai_dms_target_users:
        dm_settings = {
            "ai_dms_message_style": payload.ai_dms_message_style,
            "ai_dms_delay_minutes": payload.ai_dms_delay_minutes
        }
        
        dm_jobs = _schedule_ai_dms(
            post_id=post_id,
            user_id=current_user["id"],
            account_ids=payload.account_ids,
            target_users=payload.ai_dms_target_users,
            settings=dm_settings,
            db=db
        )
        
        engagement_jobs["dms"] = dm_jobs
    
    return {
        "post_id": post_id,
        "status": "created with engagement automation",
        "scheduled_time": post_response.scheduled_time,
        "engagement_jobs": engagement_jobs
    }


# ======================
# Comment Management Routes
# ======================

@router.get("/{post_id}/comments", response_model=List[CommentJobResponse])
def get_post_comments(
    post_id: int,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Get all comment jobs for a post."""
    cursor = db.cursor()
    cursor.execute("""
        SELECT 
            id, account_id, target_url, comment_text,
            scheduled_time, status
        FROM comment_jobs
        WHERE post_id = %s
        ORDER BY created_at DESC
    """, (post_id,))
    
    jobs = cursor.fetchall()
    
    return [
        {
            "job_id": j[0],
            "account_id": j[1],
            "target_url": j[2],
            "comment": j[3],
            "scheduled_time": j[4],
            "status": j[5]
        }
        for j in jobs
    ]


@router.delete("/comments/{job_id}")
def cancel_comment_job(
    job_id: int,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Cancel a scheduled comment job."""
    cursor = db.cursor()
    
    # Verify ownership
    cursor.execute("""
        UPDATE comment_jobs
        SET status = 'cancelled'
        WHERE id = %s AND user_id = %s AND status = 'pending'
        RETURNING id
    """, (job_id, current_user["id"]))
    
    if not cursor.fetchone():
        raise HTTPException(
            status_code=404,
            detail="Comment job not found or cannot be cancelled"
        )
    
    db.commit()
    return {"message": "Comment job cancelled"}


# ======================
# DM Management Routes
# ======================

@router.get("/{post_id}/dms", response_model=List[DMJobResponse])
def get_post_dms(
    post_id: int,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Get all DM jobs for a post."""
    cursor = db.cursor()
    cursor.execute("""
        SELECT 
            dj.id, dj.account_id, dj.recipient_username,
            dj.message_text, dj.scheduled_time, dj.status
        FROM dm_jobs dj
        WHERE dj.post_id = %s
        ORDER BY dj.created_at DESC
    """, (post_id,))
    
    jobs = cursor.fetchall()
    
    return [
        {
            "job_id": j[0],
            "account_id": j[1],
            "recipient": j[2],
            "message": j[3],
            "scheduled_time": j[4],
            "status": j[5]
        }
        for j in jobs
    ]


@router.delete("/dms/{job_id}")
def cancel_dm_job(
    job_id: int,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Cancel a scheduled DM job."""
    cursor = db.cursor()
    
    cursor.execute("""
        UPDATE dm_jobs
        SET status = 'cancelled'
        WHERE id = %s AND user_id = %s AND status = 'pending'
        RETURNING id
    """, (job_id, current_user["id"]))
    
    if not cursor.fetchone():
        raise HTTPException(
            status_code=404,
            detail="DM job not found or cannot be cancelled"
        )
    
    db.commit()
    return {"message": "DM job cancelled"}


# ======================
# Existing Routes (Unchanged)
# ======================

@router.get("/post/{post_id}")
def get_post(
    post_id: int,
    current_user: dict = Depends(get_current_user),
):
    post = get_post_details_by_post_id(post_id)

    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    return post


@router.get("/{post_id}/status")
def get_post_status(
    post_id: int,
    current_user: dict = Depends(get_current_user),
):
    status_value = get_post_status_by_id(post_id)

    if status_value is None:
        raise HTTPException(status_code=404, detail="Post not found")

    return {
        "id": post_id,
        "status": status_value,
    }


@router.get("")
def list_posts(current_user: dict = Depends(get_current_user)):
    """List all posts for the current user."""
    return get_all_posts_for_user(current_user["id"])


@router.post("/{post_id}/execute")
def execute_post_now(post_id: int):
    """Trigger immediate execution of a scheduled post."""
    execute_scheduled_post.delay(post_id)
    return {"message": "Post execution triggered"}


@router.patch("/{post_id}/cancel")
def cancel_post(
    post_id: int,
    db=Depends(get_db),
):
    """Cancel a scheduled post."""
    cursor = db.cursor()

    cursor.execute("SELECT status FROM posts WHERE id = %s", (post_id,))
    row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Post not found")

    cursor.execute(
        """
        UPDATE posts
        SET status = %s, scheduled_time = NULL
        WHERE id = %s
        """,
        ("cancelled", post_id),
    )
    db.commit()

    return {"message": "Post cancelled"}


class RescheduleRequest(BaseModel):
    scheduled_time: datetime


@router.patch("/{post_id}/reschedule")
def reschedule_post(
    post_id: int,
    payload: RescheduleRequest,
    db=Depends(get_db),
):
    """Reschedule a post to a new time."""
    cursor = db.cursor()

    cursor.execute("SELECT id FROM posts WHERE id = %s", (post_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Post not found")

    cursor.execute(
        """
        UPDATE posts
        SET scheduled_time = %s, status = %s
        WHERE id = %s
        """,
        (payload.scheduled_time.isoformat(), "Pending", post_id),
    )
    db.commit()

    return {"message": "Post rescheduled"}


@router.post("/resolve-groups")
def resolve_group_accounts(
    group_ids: List[int],
    db=Depends(get_db),
):
    """Resolve group IDs to account IDs."""
    placeholders = ",".join("%s" for _ in group_ids)

    cursor = db.cursor()
    cursor.execute(
        f"""
        SELECT DISTINCT account_id
        FROM group_accounts
        WHERE group_id IN ({placeholders})
        """,
        tuple(group_ids),
    )

    return {
        "group_ids": group_ids,
        "account_ids": [row[0] for row in cursor.fetchall()],
    }


@router.post("/{post_id}/retry")
def retry_post_execution(post_id: int):
    """Retry a failed post."""
    execute_scheduled_post.delay(post_id)
    return {"message": "Post retry triggered"}


@router.post("/{post_id}/repost")
def repost_failed_post(
    post_id: int,
    current_user: dict = Depends(get_current_user),
):
    """Repost a failed post."""
    try:
        reset_post_for_repost(post_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Post not found")
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reset post: {str(e)}",
        )

    execute_scheduled_post.delay(post_id)
    return {"message": "Post repost triggered"}