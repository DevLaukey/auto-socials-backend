from fastapi import APIRouter, Request, HTTPException, status
from datetime import datetime, timezone

from app.services.auth_database import (
    get_conn,
    mark_payment_paid,
    activate_subscription_for_user,
    get_pending_post_payment,
    mark_post_payment_paid,
)
from app.services.database import add_post
from app.workers.post_tasks import execute_scheduled_post

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/zeroid/webhook", status_code=200)
async def zeroid_webhook(request: Request):
    """
    ZeroID payment confirmation webhook (AUTHORITATIVE)

    Handles both:
    1. Subscription payments (activates subscription)
    2. Post payments (creates and schedules post)

    Idempotent, tolerant to payload variations.
    """

    payload = await request.json()

    reference = payload.get("reference")
    status_raw = payload.get("status")
    event = payload.get("event")

    if not reference:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing payment reference",
        )

    # Normalize success conditions
    is_success = False

    if status_raw:
        is_success = status_raw.lower() in ("paid", "success", "successful")

    if event:
        is_success = is_success or event.lower() in (
            "payment.success",
            "payment.paid",
        )

    # Ignore non-successful events (ACK but no action)
    if not is_success:
        return {"ok": True, "ignored": True}

    with get_conn() as conn:
        # First, check if this is a POST payment
        post_payment = get_pending_post_payment(conn, reference)

        if post_payment and post_payment["status"] == "pending":
            # This is a post payment - create the post
            row = mark_post_payment_paid(conn, reference)

            if not row:
                return {"ok": True, "duplicate": True}

            # Create the actual post
            post_data = row["post_data"]
            user_id = row["user_id"]

            # Parse scheduled_time back to datetime
            scheduled_time = None
            if post_data.get("scheduled_time"):
                scheduled_time = datetime.fromisoformat(post_data["scheduled_time"])
                if scheduled_time.tzinfo is None:
                    scheduled_time = scheduled_time.replace(tzinfo=timezone.utc)

            try:
                post_id = add_post(
                    user_id=user_id,
                    account_ids=post_data["account_ids"],
                    filename=post_data["media_file"],
                    title=post_data.get("title", ""),
                    description=post_data.get("description", ""),
                    hashtags=post_data.get("hashtags", ""),
                    tags=post_data.get("tags"),
                    privacy_status=post_data.get("privacy_status"),
                    post_type=post_data.get("post_type", "feed"),
                    cover_image=post_data.get("cover_image"),
                    audio_name=post_data.get("audio_name"),
                    location=post_data.get("location"),
                    disable_comments=post_data.get("disable_comments", False),
                    share_to_feed=post_data.get("share_to_feed", True),
                    scheduled_time=scheduled_time,
                )

                # Schedule the post via Celery
                if scheduled_time:
                    execute_scheduled_post.apply_async(
                        args=[post_id],
                        eta=scheduled_time,
                    )
                else:
                    execute_scheduled_post.delay(post_id)

                return {
                    "ok": True,
                    "type": "post_payment",
                    "post_id": post_id,
                }

            except Exception as e:
                # Log error but don't fail webhook
                return {
                    "ok": False,
                    "type": "post_payment",
                    "error": str(e),
                }

        # Otherwise, check if it's a subscription payment
        row = mark_payment_paid(conn, reference)

        # Already processed → idempotent success
        if not row:
            return {"ok": True, "duplicate": True}

        activate_subscription_for_user(
            conn,
            user_id=row["user_id"],
            plan_id=row["plan_id"],
        )

    return {"ok": True, "type": "subscription_payment"}

