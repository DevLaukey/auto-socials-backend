"""
Endpoints for creating and scheduling posts.

This layer NEVER posts content directly.
It only stores intent and schedules background execution via Celery.

PAYMENT FLOW:
1. User calls POST /posts/initiate-payment with post data
2. Backend stores post data and returns ZeroID payment URL
3. User completes payment on ZeroID
4. ZeroID webhook confirms payment
5. Post is automatically created and scheduled
"""

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import List, Optional, Literal

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
)
from app.api.deps import get_current_user
from app.workers.post_tasks import execute_scheduled_post

# ZeroID payment URL for post payments
ZEROID_POST_PAYMENT_URL = "https://app.zeroid.cc/paylink/89e8d2c5-be5c-4953-8b2f-43cd0bafcd95"


router = APIRouter(prefix="/posts", tags=["posts"])


# ======================
# Schemas
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

    # Scheduling
    scheduled_time: Optional[datetime] = None


class PostResponse(BaseModel):
    id: int
    status: str
    scheduled_time: Optional[datetime]


class PaymentInitiationResponse(BaseModel):
    payment_id: str
    payment_url: str
    message: str


# ======================
# Routes
# ======================

@router.post("/initiate-payment", response_model=PaymentInitiationResponse)
def initiate_post_payment(
    payload: PostCreate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Initiate payment for creating a post.

    This endpoint:
    1. Validates the post data
    2. Stores the post data temporarily
    3. Returns the ZeroID payment URL

    After payment is confirmed via webhook, the post will be automatically created.
    """

    # Normalize scheduled_time to UTC
    scheduled_time = payload.scheduled_time
    if scheduled_time:
        if scheduled_time.tzinfo is None:
            scheduled_time = scheduled_time.replace(tzinfo=timezone.utc)
        else:
            scheduled_time = scheduled_time.astimezone(timezone.utc)

    # Resolve accounts from groups (validation only)
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


@router.get("/payment-status/{payment_id}")
def check_payment_status(
    payment_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Check if a post payment has been completed.

    Returns:
    - status: 'pending', 'paid', or 'failed'
    - is_paid: boolean for easy checking
    """
    payment = get_post_payment_status(payment_id)

    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    # Verify user owns this payment
    if payment["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    return {
        "payment_id": str(payment["id"]),
        "status": payment["status"],
        "is_paid": payment["status"] == "paid",
        "created_at": payment["created_at"],
        "updated_at": payment["updated_at"],
    }


@router.get("/my-payments")
def list_my_post_payments(
    status_filter: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """
    List all post payment intents for the current user.

    Query params:
    - status: Filter by 'pending', 'paid', or 'failed' (optional)
    """
    payments = get_user_post_payments(current_user["id"], status_filter)

    return [
        {
            "payment_id": str(p["id"]),
            "status": p["status"],
            "is_paid": p["status"] == "paid",
            "amount": p["amount"],
            "currency": p["currency"],
            "created_at": p["created_at"],
            "updated_at": p["updated_at"],
        }
        for p in payments
    ]


@router.post("/", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
def create_post(
    payload: PostCreate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Create a post and schedule it via Celery.
    """

    # Normalize scheduled_time to UTC
    scheduled_time = payload.scheduled_time
    if scheduled_time:
        if scheduled_time.tzinfo is None:
            scheduled_time = scheduled_time.replace(tzinfo=timezone.utc)
        else:
            scheduled_time = scheduled_time.astimezone(timezone.utc)

    # ======================
    # RESOLVE ACCOUNTS FROM GROUPS
    # ======================
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

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create post: {str(e)}",
        )

    # ======================
    # Celery scheduling
    # ======================
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
    )


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
    """
    Used by PostHistory and ScheduledPostsModal
    """
    return get_all_posts_for_user(current_user["id"])


@router.post("/{post_id}/execute")
def execute_post_now(post_id: int):
    execute_scheduled_post.delay(post_id)
    return {"message": "Post execution triggered"}



@router.patch("/{post_id}/cancel")
def cancel_post(
    post_id: int,
    db=Depends(get_db),
):
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
    execute_scheduled_post.delay(post_id)
    return {"message": "Post retry triggered"}

@router.post("/{post_id}/repost")
def repost_failed_post(
    post_id: int,
    current_user: dict = Depends(get_current_user),
):
    """
    Repost a failed post by resetting its status
    and re-triggering Celery execution.
    """

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
