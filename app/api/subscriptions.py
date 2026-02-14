from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
import datetime

from app.api.deps import get_current_user, require_admin
from app.services.auth_database import get_conn, create_payment_intent

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

    return {"status": "deleted", "plan_id": plan_id}





