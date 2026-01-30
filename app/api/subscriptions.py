from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
import datetime

from app.api.deps import get_current_user
from app.services.auth_database import get_conn, create_payment_intent

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


# -----------------------------
# Schemas
# -----------------------------

class Subscription(BaseModel):
    plan_id: int


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
                    dms_per_day
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
    plan_id = payload.get("plan_id")

    if not plan_id:
        raise HTTPException(status_code=400, detail="Missing plan_id")

    with get_conn() as conn:
        # Example: hardcode amount for now
        amount = 1000  # KES – replace later per plan

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



