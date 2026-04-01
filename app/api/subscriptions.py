from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
import datetime
import logging

from app.api.deps import get_current_user, require_admin
from app.services.auth_database import get_conn, create_payment_intent
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


# -----------------------------
# Schemas
# -----------------------------

class Subscription(BaseModel):
    plan_id: int


class CreateSubscriptionPlan(BaseModel):
    name: str
    max_channels: int
    posts_per_day: int
    comments_per_day: int
    dms_per_day: int
    price: int
    duration_days: int = 30


class UpdateSubscriptionPlan(BaseModel):
    name: str | None = None
    max_channels: int | None = None
    posts_per_day: int | None = None
    comments_per_day: int | None = None
    dms_per_day: int | None = None
    price: int | None = None
    duration_days: int | None = None


class PayPalSubscribeRequest(BaseModel):
    plan_id: int
    return_url: str | None = None
    cancel_url: str | None = None


class MoneyMotionSubscribeRequest(BaseModel):
    plan_id: int
    return_url: str | None = None
    cancel_url: str | None = None


class PaymentMethodResponse(BaseModel):
    payment_method: str
    action: str
    endpoint: str | None = None
    data: dict | None = None
    payment_id: str | None = None
    payment_url: str | None = None


class PayPalSubscribeResponse(BaseModel):
    payment_method: str
    action: str
    endpoint: str
    data: dict


# -----------------------------
# GET ALL PLANS
# -----------------------------

@router.get("/plans")
def get_subscription_plans():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    id,
                    name,
                    max_channels,
                    posts_per_day,
                    comments_per_day,
                    dms_per_day,
                    price
                FROM subscription_plans
                ORDER BY id ASC
            """)
            rows = cur.fetchall()

    plans = [
        {
            "id": r["id"],
            "name": r["name"],
            "max_channels": r["max_channels"],
            "posts_per_day": r["posts_per_day"],
            "comments_per_day": r["comments_per_day"],
            "dms_per_day": r["dms_per_day"],
            "price": r["price"],
        }
        for r in rows
    ]

    return plans


# -----------------------------
# SUBSCRIBE USER TO PLAN
# -----------------------------

@router.post("/subscribe")
def subscribe(
    payload: dict,
    current_user: dict = Depends(get_current_user),
):
    """
    Subscribe to a plan using ZeroID (default payment method).
    """
    plan_id = payload.get("plan_id")

    if not plan_id:
        raise HTTPException(status_code=400, detail="Missing plan_id")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT price FROM subscription_plans WHERE id = %s",
                (plan_id,),
            )
            plan = cur.fetchone()

            if not plan:
                raise HTTPException(status_code=404, detail="Invalid plan")

            amount = plan["price"]

            if amount <= 0:
                raise HTTPException(
                    status_code=400,
                    detail="Plan price is not configured"
                )

        payment_id = create_payment_intent(
            conn,
            user_id=current_user["id"],
            plan_id=plan_id,
            amount=amount,
        )

    return {
        "payment_id": str(payment_id),
        "payment_url": "https://app.zeroid.cc/paylink/89e8d2c5-be5c-4953-8b2f-43cd0bafcd95"
    }


@router.post("/subscribe/paypal")
def subscribe_paypal(
    payload: PayPalSubscribeRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Subscribe to a plan using PayPal.
    Returns PayPal order creation endpoint info.
    """
    plan_id = payload.plan_id

    if not plan_id:
        raise HTTPException(status_code=400, detail="Missing plan_id")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT price, name FROM subscription_plans WHERE id = %s",
                (plan_id,),
            )
            plan = cur.fetchone()

            if not plan:
                raise HTTPException(status_code=404, detail="Invalid plan")

            amount = plan["price"]
            plan_name = plan["name"]

            if amount <= 0:
                raise HTTPException(
                    status_code=400,
                    detail="Plan price is not configured"
                )

    # Return PayPal order creation info for frontend
    return PayPalSubscribeResponse(
        payment_method="paypal",
        action="create_paypal_order",
        endpoint="/paypal/create-subscription-order",
        data={
            "plan_id": plan_id,
            "plan_name": plan_name,
            "amount": amount,
            "return_url": payload.return_url,
            "cancel_url": payload.cancel_url
        }
    )


@router.post("/subscribe/moneymotion")
def subscribe_moneymotion(
    payload: MoneyMotionSubscribeRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Subscribe to a plan using MoneyMotion.
    Returns MoneyMotion order creation endpoint info.
    """
    plan_id = payload.plan_id

    if not plan_id:
        raise HTTPException(status_code=400, detail="Missing plan_id")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT price, name FROM subscription_plans WHERE id = %s",
                (plan_id,),
            )
            plan = cur.fetchone()

            if not plan:
                raise HTTPException(status_code=404, detail="Invalid plan")

            amount = plan["price"]
            plan_name = plan["name"]

            if amount <= 0:
                raise HTTPException(
                    status_code=400,
                    detail="Plan price is not configured"
                )

    # Return MoneyMotion order creation info for frontend
    return PaymentMethodResponse(
        payment_method="moneymotion",
        action="create_moneymotion_order",
        endpoint="/moneymotion/create-subscription-order",
        data={
            "plan_id": plan_id,
            "plan_name": plan_name,
            "amount": amount,
            "return_url": payload.return_url,
            "cancel_url": payload.cancel_url
        }
    )


@router.post("/subscribe/select-method")
def subscribe_with_method(
    payload: dict,
    current_user: dict = Depends(get_current_user),
):
    """
    Subscribe to a plan with a specified payment method.
    Returns appropriate response based on payment method.
    """
    plan_id = payload.get("plan_id")
    payment_method = payload.get("payment_method", "zeroid").lower()
    return_url = payload.get("return_url")
    cancel_url = payload.get("cancel_url")

    if not plan_id:
        raise HTTPException(status_code=400, detail="Missing plan_id")

    # Validate plan exists
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT price, name FROM subscription_plans WHERE id = %s",
                (plan_id,),
            )
            plan = cur.fetchone()

            if not plan:
                raise HTTPException(status_code=404, detail="Invalid plan")

            amount = plan["price"]
            plan_name = plan["name"]

            if amount <= 0:
                raise HTTPException(
                    status_code=400,
                    detail="Plan price is not configured"
                )

    # Handle different payment methods
    if payment_method == "zeroid":
        payment_id = create_payment_intent(
            conn,
            user_id=current_user["id"],
            plan_id=plan_id,
            amount=amount,
        )
        return {
            "payment_method": "zeroid",
            "payment_id": str(payment_id),
            "payment_url": "https://app.zeroid.cc/paylink/89e8d2c5-be5c-4953-8b2f-43cd0bafcd95",
            "action": "redirect"
        }

    elif payment_method == "paypal":
        return PayPalSubscribeResponse(
            payment_method="paypal",
            action="create_paypal_order",
            endpoint="/paypal/create-subscription-order",
            data={
                "plan_id": plan_id,
                "plan_name": plan_name,
                "amount": amount,
                "return_url": return_url,
                "cancel_url": cancel_url
            }
        )

    elif payment_method == "moneymotion":
        return PaymentMethodResponse(
            payment_method="moneymotion",
            action="create_moneymotion_order",
            endpoint="/moneymotion/create-subscription-order",
            data={
                "plan_id": plan_id,
                "plan_name": plan_name,
                "amount": amount,
                "return_url": return_url,
                "cancel_url": cancel_url
            }
        )

    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported payment method: {payment_method}"
        )


# -----------------------------
# PLAN MANAGEMENT (ADMIN)
# -----------------------------

@router.get("/plans/{plan_id}")
def get_subscription_plan(plan_id: int):
    """Get a single subscription plan by ID."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    id, name, max_channels,
                    posts_per_day, comments_per_day, dms_per_day,
                    price, duration_days
                FROM subscription_plans
                WHERE id = %s
            """, (plan_id,))
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Plan not found")

    return dict(row)


@router.post("/plans", status_code=status.HTTP_201_CREATED)
def create_subscription_plan(
    payload: CreateSubscriptionPlan,
    admin=Depends(require_admin),
):
    """Admin: create a new subscription plan."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO subscription_plans
                    (name, max_channels, posts_per_day, comments_per_day, dms_per_day, price, duration_days)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                payload.name,
                payload.max_channels,
                payload.posts_per_day,
                payload.comments_per_day,
                payload.dms_per_day,
                payload.price,
                payload.duration_days,
            ))
            row = cur.fetchone()
        conn.commit()

    logger.info(f"Admin {admin['id']} created subscription plan: {payload.name}")

    return {"status": "created", "plan_id": row["id"]}


@router.put("/plans/{plan_id}")
def update_subscription_plan(
    plan_id: int,
    payload: UpdateSubscriptionPlan,
    admin=Depends(require_admin),
):
    """Admin: update an existing subscription plan."""
    fields = []
    values = []

    for field, value in payload.dict(exclude_unset=True).items():
        fields.append(f"{field} = %s")
        values.append(value)

    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    values.append(plan_id)

    query = f"""
        UPDATE subscription_plans
        SET {", ".join(fields)}
        WHERE id = %s
        RETURNING id;
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, values)
            row = cur.fetchone()

        conn.commit()

    if not row:
        raise HTTPException(status_code=404, detail="Plan not found")

    logger.info(f"Admin {admin['id']} updated subscription plan {plan_id}")

    return {"status": "updated", "plan_id": plan_id}


@router.delete("/plans/{plan_id}")
def delete_subscription_plan(
    plan_id: int,
    admin=Depends(require_admin),
):
    """Admin: delete a subscription plan (only if no active subscriptions use it)."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Check if any active subscriptions reference this plan
            cur.execute("""
                SELECT COUNT(*) AS cnt
                FROM user_subscriptions
                WHERE plan_id = %s AND is_active = TRUE
            """, (plan_id,))
            count = cur.fetchone()["cnt"]

            if count > 0:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Cannot delete: {count} active subscription(s) use this plan",
                )

            cur.execute("""
                DELETE FROM subscription_plans
                WHERE id = %s
                RETURNING id
            """, (plan_id,))
            row = cur.fetchone()

        conn.commit()

    if not row:
        raise HTTPException(status_code=404, detail="Plan not found")

    logger.info(f"Admin {admin['id']} deleted subscription plan {plan_id}")

    return {"status": "deleted", "plan_id": plan_id}


# -----------------------------
# PAYMENT METHODS
# -----------------------------

@router.get("/payment-methods")
def get_payment_methods():
    """
    Get available payment methods for subscriptions.
    """
    methods = [
        {
            "id": "zeroid",
            "name": "ZeroID",
            "description": "Pay with ZeroID",
            "icon": "https://app.zeroid.cc/favicon.ico",
            "enabled": True
        },
        {
            "id": "paypal",
            "name": "PayPal",
            "description": "Pay with PayPal account or credit card",
            "icon": "https://www.paypal.com/favicon.ico",
            "enabled": bool(settings.PAYPAL_CLIENT_ID and settings.PAYPAL_CLIENT_SECRET)
        }
    ]
    
    # Add MoneyMotion if configured
    if settings.MONEYMOTION_API_KEY:
        methods.append({
            "id": "moneymotion",
            "name": "MoneyMotion",
            "description": "Pay with MoneyMotion (MPesa, cards, etc.)",
            "icon": "https://moneymotion.io/favicon.ico",
            "enabled": True
        })

    return {"payment_methods": methods}


# -----------------------------
# WEBHOOK HANDLERS (if needed)
# -----------------------------

@router.post("/webhook/zeroid")
async def zeroid_webhook(request: Request):
    """
    Handle ZeroID payment webhook.
    This is a passthrough to the main payments webhook.
    """
    # Forward to the payments webhook
    from app.api.payments import zeroid_webhook as handle_zeroid
    return await handle_zeroid(request)