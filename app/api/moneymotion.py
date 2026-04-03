"""
MoneyMotion Payment Endpoints
"""

from fastapi import APIRouter, HTTPException, Depends, Request, status
from pydantic import BaseModel
from typing import Optional
import logging
import json

from app.api.deps import get_current_user
from app.services.moneymotion_service import MoneyMotionService
from app.services.auth_database import (
    get_conn,
    create_payment_intent,
    create_post_payment_intent,
    activate_subscription_for_user,
    mark_post_payment_paid,
)
from app.services.database import add_post
from app.workers.post_tasks import execute_scheduled_post
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/moneymotion", tags=["moneymotion"])

moneymotion_service = MoneyMotionService()


class CreateMoneyMotionOrderRequest(BaseModel):
    plan_id: int
    return_url: Optional[str] = None
    cancel_url: Optional[str] = None


class CreatePostMoneyMotionOrderRequest(BaseModel):
    post_data: dict
    return_url: Optional[str] = None
    cancel_url: Optional[str] = None


class MoneyMotionOrderResponse(BaseModel):
    payment_id: str
    checkout_url: str
    reference: str


@router.post("/create-subscription-order")
async def create_subscription_order(
    payload: CreateMoneyMotionOrderRequest,
    current_user: dict = Depends(get_current_user)
):
    """Create a MoneyMotion order for subscription payment."""
    # Check if MoneyMotion is configured
    if not settings.MONEYMOTION_API_KEY:
        raise HTTPException(
            status_code=503, 
            detail="MoneyMotion payment method is not configured"
        )
    
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
        # Create MoneyMotion payment
        payment = moneymotion_service.create_payment(
            user_id=current_user["id"],
            amount=float(plan["price"]),
            currency="USD",
            description=f"Subscription: {plan['name']}",
            reference=str(payment_id),
            return_url=payload.return_url,
            cancel_url=payload.cancel_url,
            email=current_user.get("email")
        )

        session_id = payment.get("checkoutSessionId")

        # Update payment intent with MoneyMotion payment ID
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE payment_intents
                    SET payment_method = 'moneymotion',
                        provider_payment_id = %s
                    WHERE id = %s
                """, (session_id, str(payment_id)))
                conn.commit()

        return MoneyMotionOrderResponse(
            payment_id=session_id,
            checkout_url=payment.get("checkoutUrl"),
            reference=str(payment_id)
        )
        
    except Exception as e:
        logger.error(f"Failed to create MoneyMotion subscription order: {e}")
        raise HTTPException(status_code=500, detail="Failed to create payment order")


@router.post("/create-post-order")
async def create_post_order(
    payload: CreatePostMoneyMotionOrderRequest,
    current_user: dict = Depends(get_current_user)
):
    """Create a MoneyMotion order for pay-per-post payment."""
    # Check if MoneyMotion is configured
    if not settings.MONEYMOTION_API_KEY:
        raise HTTPException(
            status_code=503, 
            detail="MoneyMotion payment method is not configured"
        )
    
    try:
        # Create payment intent
        with get_conn() as conn:
            payment_id = create_post_payment_intent(
                conn,
                user_id=current_user["id"],
                post_data=payload.post_data,
                amount=100  # KES
            )
            payment_id_str = str(payment_id)
        
        # Create MoneyMotion payment
        payment = moneymotion_service.create_payment(
            user_id=current_user["id"],
            amount=100.00,  # KES
            currency="USD",
            description="Social Media Post",
            reference=payment_id_str,
            return_url=payload.return_url,
            cancel_url=payload.cancel_url,
            email=current_user.get("email")
        )

        session_id = payment.get("checkoutSessionId")

        # Update payment intent with MoneyMotion payment ID
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE post_payment_intents
                    SET payment_method = 'moneymotion',
                        provider_payment_id = %s
                    WHERE id = %s
                """, (session_id, payment_id_str))
                conn.commit()

        return MoneyMotionOrderResponse(
            payment_id=session_id,
            checkout_url=payment.get("checkoutUrl"),
            reference=payment_id_str
        )
        
    except Exception as e:
        logger.error(f"Failed to create MoneyMotion post order: {e}")
        raise HTTPException(status_code=500, detail="Failed to create payment order")


@router.post("/webhook")
async def moneymotion_webhook(request: Request):
    """
    MoneyMotion webhook handler for async payment events.
    """
    # Try multiple header variations for signature
    signature = (
        request.headers.get("x-moneymotion-signature", "") or
        request.headers.get("x-moneymoov-signature", "") or
        request.headers.get("x-signature", "")
    )
    
    # Get raw body for signature verification
    body = await request.body()
    
    # Verify signature (only if webhook secret is configured)
    is_valid = moneymotion_service.verify_webhook_signature(body, signature)
    if not is_valid and settings.ENV == "production":
        logger.warning("Invalid MoneyMotion webhook signature")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    
    # Parse webhook event
    try:
        event = await request.json()
    except:
        event = {}
    
    # Handle different webhook payload structures
    event_type = event.get("event_type") or event.get("type") or event.get("event")
    payment_id = event.get("payment_id") or event.get("id") or event.get("resource_id")
    reference = event.get("reference") or event.get("merchant_reference")
    status = event.get("status") or event.get("state")
    
    logger.info(f"Received MoneyMotion webhook: {event_type} for payment {payment_id}")
    
    # Store webhook event for audit (optional)
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO auth.moneymotion_webhook_events 
                    (event_id, event_type, resource_id, resource, processed)
                    VALUES (%s, %s, %s, %s, FALSE)
                """, (payment_id, event_type, reference, json.dumps(event)))
                conn.commit()
    except Exception as e:
        logger.warning(f"Failed to store webhook event: {e}")
    
    # Handle successful payment
    if status in ["completed", "success", "paid", "succeeded"]:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Check subscription payment
                cur.execute("""
                    SELECT id, user_id, plan_id, status
                    FROM auth.payment_intents
                    WHERE id = %s AND status != 'paid'
                """, (reference,))
                payment = cur.fetchone()
                
                if payment:
                    activate_subscription_for_user(
                        conn,
                        user_id=payment["user_id"],
                        plan_id=payment["plan_id"]
                    )
                    cur.execute("""
                        UPDATE auth.payment_intents
                        SET status = 'paid', 
                            provider_payment_id = %s,
                            updated_at = NOW()
                        WHERE id = %s
                    """, (payment_id, payment["id"]))
                    conn.commit()
                    logger.info(f"Subscription activated via MoneyMotion webhook for payment {payment_id}")
                    return {"status": "success"}
                
                # Check post payment
                cur.execute("""
                    SELECT id, user_id, post_data, status
                    FROM auth.post_payment_intents
                    WHERE id = %s AND status != 'paid'
                """, (reference,))
                post_payment = cur.fetchone()
                
                if post_payment:
                    # Create the post
                    post_data = post_payment["post_data"]
                    user_id = post_payment["user_id"]
                    
                    from datetime import datetime, timezone
                    scheduled_time = None
                    if post_data.get("scheduled_time"):
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
                        UPDATE auth.post_payment_intents
                        SET status = 'paid', 
                            provider_payment_id = %s,
                            updated_at = NOW()
                        WHERE id = %s
                    """, (payment_id, post_payment["id"]))
                    conn.commit()
                    
                    # Schedule the post
                    if scheduled_time:
                        execute_scheduled_post.apply_async(
                            args=[post_id],
                            eta=scheduled_time
                        )
                    else:
                        execute_scheduled_post.delay(post_id)
                    
                    logger.info(f"Post {post_id} created via MoneyMotion payment")
                    return {"status": "success", "post_id": post_id}
    
    return {"status": "ignored"}