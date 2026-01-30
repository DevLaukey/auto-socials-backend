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
    ZeroID payment confirmation webhook (AUTHORITATIVE)

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
        row = mark_payment_paid(conn, reference)

        # Already processed → idempotent success
        if not row:
            return {"ok": True, "duplicate": True}

        activate_subscription_for_user(
            conn,
            user_id=row["user_id"],
            plan_id=row["plan_id"],
        )

    return {"ok": True}

