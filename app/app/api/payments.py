from fastapi import APIRouter, Request, HTTPException, status
from app.services.auth_database import (
    get_conn,
    mark_payment_paid,
    activate_subscription_for_user,
)

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/zeroid/webhook", status_code=200)
async def zeroid_webhook(request: Request):
    """
    ZeroID payment confirmation webhook
    """

    payload = await request.json()

    # ---- BASIC VALIDATION ----
    zeroid_reference = payload.get("reference")
    payment_status = payload.get("status")

    if not zeroid_reference or not payment_status:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook payload",
        )

    # We only care about successful payments
    if payment_status.lower() != "paid":
        return {"ok": True, "ignored": True}

    # ---- TRANSACTION ----
    with get_conn() as conn:
        with conn:
            row = mark_payment_paid(conn, zeroid_reference)

            # Already processed → idempotent success
            if not row:
                return {"ok": True, "duplicate": True}

            activate_subscription_for_user(
                conn,
                user_id=row["user_id"],
                plan_id=row["plan_id"],
            )

    return {"ok": True}
