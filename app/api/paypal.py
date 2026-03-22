"""
PayPal Payment Endpoints
"""

from fastapi import APIRouter, HTTPException, Depends, Request, status
from pydantic import BaseModel
from typing import Optional
import logging

from app.api.deps import get_current_user
from app.services.paypal_service import PayPalService
from app.services.auth_database import (
    get_conn,
    create_payment_intent,
    create_post_payment_intent,
    activate_subscription_for_user,
    mark_post_payment_paid,
    get_pending_post_payment,
)
from app.services.database import add_post
from app.workers.post_tasks import execute_scheduled_post
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/paypal", tags=["paypal"])

paypal_service = PayPalService()


class CreatePayPalOrderRequest(BaseModel):
    plan_id: int
    return_url: Optional[str] = None
    cancel_url: Optional[str] = None


class CreatePostPayPalOrderRequest(BaseModel):
    post_data: dict
    return_url: Optional[str] = None
    cancel_url: Optional[str] = None


class PayPalOrderResponse(BaseModel):
    order_id: str
    approval_url: str
    payment_id: str


@router.post("/create-subscription-order")
async def create_subscription_order(
    payload: CreatePayPalOrderRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a PayPal order for subscription payment.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Get plan details
            cur.execute(
                "SELECT name, price FROM subscription_plans WHERE id = %s",
                (payload.plan_id,)
            )
            plan = cur.fetchone()

            if not plan:
                raise HTTPException(status_code=404, detail="Plan not found")

            # Create payment intent in database
            payment_id = create_payment_intent(
                conn,
                user_id=current_user["id"],
                plan_id=payload.plan_id,
                amount=plan["price"]
            )

    try:
        # Create PayPal order
        order = paypal_service.create_subscription_order(
            user_id=current_user["id"],
            plan_name=plan["name"],
            amount=float(plan["price"]),
            return_url=payload.return_url,
            cancel_url=payload.cancel_url
        )

        # Update payment intent with PayPal order ID
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE payment_intents
                    SET payment_method = 'paypal',
                        paypal_order_id = %s
                    WHERE id = %s
                """, (order["id"], str(payment_id)))
                conn.commit()

        # Find approval URL
        approval_url = None
        for link in order.get("links", []):
            if link.get("rel") == "approve":
                approval_url = link.get("href")
                break

        return PayPalOrderResponse(
            order_id=order["id"],
            approval_url=approval_url,
            payment_id=str(payment_id)
        )

    except Exception as e:
        logger.error(f"Failed to create PayPal subscription order: {e}")
        raise HTTPException(status_code=500, detail="Failed to create payment order")


@router.post("/create-post-order")
async def create_post_order(
    payload: CreatePostPayPalOrderRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a PayPal order for pay-per-post payment.
    """
    try:
        # Create payment intent
        with get_conn() as conn:
            payment_id = create_post_payment_intent(
                conn,
                user_id=current_user["id"],
                post_data=payload.post_data,
                amount=100  # KES - convert to appropriate currency
            )
            payment_id_str = str(payment_id)

        # Create PayPal order
        order = paypal_service.create_post_payment_order(
            user_id=current_user["id"],
            post_data=payload.post_data
        )

        # Update payment intent with PayPal order ID
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE post_payment_intents
                    SET payment_method = 'paypal',
                        paypal_order_id = %s
                    WHERE id = %s
                """, (order["id"], payment_id_str))
                conn.commit()

        # Find approval URL
        approval_url = None
        for link in order.get("links", []):
            if link.get("rel") == "approve":
                approval_url = link.get("href")
                break

        return PayPalOrderResponse(
            order_id=order["id"],
            approval_url=approval_url,
            payment_id=payment_id_str
        )

    except Exception as e:
        logger.error(f"Failed to create PayPal post order: {e}")
        raise HTTPException(status_code=500, detail="Failed to create payment order")


@router.post("/capture-order/{order_id}")
async def capture_paypal_order(
    order_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Capture a PayPal order after user approval.
    """
    try:
        # Capture the order
        capture_result = paypal_service.capture_order(order_id)

        if capture_result.get("status") != "COMPLETED":
            raise HTTPException(
                status_code=400,
                detail=f"Payment not completed. Status: {capture_result.get('status')}"
            )

        # Get capture ID
        capture_id = None
        for purchase_unit in capture_result.get("purchase_units", []):
            for capture in purchase_unit.get("payments", {}).get("captures", []):
                capture_id = capture.get("id")
                break

        # Find the payment intent by PayPal order ID
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Check subscription payment
                cur.execute("""
                    SELECT id, user_id, plan_id, status
                    FROM payment_intents
                    WHERE paypal_order_id = %s
                """, (order_id,))
                payment = cur.fetchone()

                if payment:
                    if payment["status"] == "paid":
                        return {"message": "Payment already processed"}

                    # Update payment intent with capture ID
                    cur.execute("""
                        UPDATE payment_intents
                        SET status = 'paid',
                            paypal_capture_id = %s,
                            updated_at = NOW()
                        WHERE id = %s
                    """, (capture_id, payment["id"]))

                    # Activate subscription
                    activate_subscription_for_user(
                        conn,
                        user_id=payment["user_id"],
                        plan_id=payment["plan_id"]
                    )

                    conn.commit()
                    logger.info(f"Subscription activated for user {payment['user_id']} via PayPal")
                    return {"message": "Subscription activated successfully"}

                # Check post payment
                cur.execute("""
                    SELECT id, user_id, post_data, status
                    FROM post_payment_intents
                    WHERE paypal_order_id = %s
                """, (order_id,))
                post_payment = cur.fetchone()

                if post_payment:
                    if post_payment["status"] == "paid":
                        return {"message": "Payment already processed"}

                    # Create the post
                    post_data = post_payment["post_data"]
                    user_id = post_payment["user_id"]

                    scheduled_time = None
                    if post_data.get("scheduled_time"):
                        from datetime import datetime, timezone
                        scheduled_time = datetime.fromisoformat(post_data["scheduled_time"])
                        if scheduled_time.tzinfo is None:
                            scheduled_time = scheduled_time.replace(tzinfo=timezone.utc)

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

                    # Update payment intent
                    cur.execute("""
                        UPDATE post_payment_intents
                        SET status = 'paid',
                            paypal_capture_id = %s,
                            updated_at = NOW()
                        WHERE id = %s
                    """, (capture_id, post_payment["id"]))

                    conn.commit()

                    # Schedule the post
                    if scheduled_time:
                        execute_scheduled_post.apply_async(
                            args=[post_id],
                            eta=scheduled_time
                        )
                    else:
                        execute_scheduled_post.delay(post_id)

                    logger.info(f"Post {post_id} created via PayPal payment")
                    return {"message": "Post created successfully", "post_id": post_id}

                raise HTTPException(status_code=404, detail="Payment not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to capture PayPal order {order_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to process payment")


@router.post("/webhook")
async def paypal_webhook(request: Request):
    """
    PayPal webhook handler for async payment events.
    """
    # Get webhook headers and body
    headers = dict(request.headers)
    body = await request.body()
    body_str = body.decode()
    
    # Normalize headers to lowercase for easier access
    normalized_headers = {k.lower(): v for k, v in headers.items()}

    # Verify signature (optional - can skip in development)
    if settings.PAYPAL_MODE == "live":
        is_valid = paypal_service.verify_webhook_signature(normalized_headers, body_str)
        if not is_valid:
            logger.warning("Invalid PayPal webhook signature")
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # Parse webhook event
    event = await request.json()
    event_type = event.get("event_type")

    logger.info(f"Received PayPal webhook: {event_type}")

    # Store webhook event for audit
    paypal_service.store_webhook_event(event)

    # Handle different event types
    if event_type == "PAYMENT.CAPTURE.COMPLETED":
        resource = event.get("resource", {})
        capture_id = resource.get("id")
        
        if capture_id:
            # Find payment by capture ID
            with get_conn() as conn:
                with conn.cursor() as cur:
                    # Check subscription payment
                    cur.execute("""
                        SELECT id, user_id, plan_id, status
                        FROM payment_intents
                        WHERE paypal_capture_id = %s AND status != 'paid'
                    """, (capture_id,))
                    payment = cur.fetchone()

                    if payment:
                        activate_subscription_for_user(
                            conn,
                            user_id=payment["user_id"],
                            plan_id=payment["plan_id"]
                        )
                        cur.execute("""
                            UPDATE payment_intents
                            SET status = 'paid', updated_at = NOW()
                            WHERE id = %s
                        """, (payment["id"],))
                        conn.commit()
                        logger.info(f"Subscription activated via webhook for capture {capture_id}")

    elif event_type == "PAYMENT.CAPTURE.REFUNDED":
        resource = event.get("resource", {})
        capture_id = resource.get("id")
        # Handle refund logic if needed
        logger.info(f"Payment refunded for capture {capture_id}")

    elif event_type == "PAYMENT.CAPTURE.DENIED":
        resource = event.get("resource", {})
        capture_id = resource.get("id")
        logger.warning(f"Payment denied for capture {capture_id}")

    return {"status": "success"}