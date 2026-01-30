from fastapi import APIRouter, Depends, HTTPException, status
from typing import List

from app.api.deps import require_admin
from app.api.schemas.admin import (
    AdminUserOut,
    AdminUserStatusUpdate,
    AdminExtendSubscription,
)

from app.services.auth_database import (
    admin_list_users,
    admin_set_user_active,
    admin_extend_subscription,
    admin_get_user_payments,
    get_admin_count,
    set_user_admin_status,
    
)

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
)

# -------------------------------------------------
# USERS
# -------------------------------------------------

@router.get("/users", response_model=List[AdminUserOut])
def list_users(admin=Depends(require_admin)):
    """
    List all users with subscription status.
    """
    rows = admin_list_users()

    users = []
    for r in rows:
        users.append({
            "id": r["id"],
            "email": r["email"],
            "is_active": r["is_active"],
            "is_admin": r["is_admin"],
            "created_at": r["created_at"],
            "plan_name": r.get("plan_name"),
            "subscription_active": r.get("subscription_active"),
            "subscription_start": r.get("start_date"),
            "subscription_end": r.get("end_date"),
        })

    return users


@router.patch("/users/{user_id}/status")
def set_user_status(
    user_id: int,
    payload: AdminUserStatusUpdate,
    admin=Depends(require_admin),
):
    """
    Activate or deactivate a user.
    """
    # Prevent admin from disabling themselves
    if admin["id"] == user_id and not payload.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admins cannot deactivate themselves",
        )

    admin_set_user_active(user_id, payload.is_active)
    return {"message": "User status updated"}


# -------------------------------------------------
# SUBSCRIPTIONS
# -------------------------------------------------

@router.post("/users/{user_id}/extend-subscription")
def extend_subscription(
    user_id: int,
    payload: AdminExtendSubscription,
    admin=Depends(require_admin),
):
    """
    Extend an active subscription by N days.
    """
    if payload.days <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Days must be greater than zero",
        )

    admin_extend_subscription(user_id, payload.days)
    return {"message": f"Subscription extended by {payload.days} days"}


# -------------------------------------------------
# PAYMENTS
# -------------------------------------------------

@router.get("/users/{user_id}/payments")
def get_user_payments(
    user_id: int,
    admin=Depends(require_admin),
):
    """
    View payment history for a user.
    """
    return admin_get_user_payments(user_id)



@router.post("/users/{user_id}/promote")
def promote_user_to_admin(
    user_id: int,
    admin=Depends(require_admin),
):
    success = set_user_admin_status(user_id, True)

    if not success:
        raise HTTPException(status_code=404, detail="User not found")

    return {"message": "User promoted to admin"}


@router.post("/users/{user_id}/revoke-admin")
def revoke_admin_privileges(
    user_id: int,
    admin=Depends(require_admin),
):
    # Rule 1: admin cannot revoke themselves
    if user_id == admin["id"]:
        raise HTTPException(
            status_code=400,
            detail="You cannot revoke your own admin privileges",
        )

    # Optional Rule 2: ensure at least one admin remains
    admin_count = get_admin_count()
    if admin_count <= 1:
        raise HTTPException(
            status_code=400,
            detail="Cannot revoke admin privileges from the last admin",
        )

    success = set_user_admin_status(user_id, False)

    if not success:
        raise HTTPException(status_code=404, detail="User not found")

    return {"message": "Admin privileges revoked"}
