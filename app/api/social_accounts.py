from fastapi import APIRouter, Depends, HTTPException, status, Body
from pydantic import BaseModel
from typing import Optional, List

from app.api.deps import get_current_user
from app.services.database import (
    add_account,
    get_accounts,
    delete_account,
    add_account_to_group,
    remove_account_from_group,
)

router = APIRouter(
    prefix="/social-accounts",
    tags=["Social Accounts"]
)


# ---------------- Schemas ----------------

class SocialAccountCreate(BaseModel):
    platform: str
    account_username: str
    password: str
    group_id: Optional[int] = None


class SocialAccountResponse(BaseModel):
    id: int
    platform: str
    account_username: str
    group_id: Optional[int]
    status: str


# ---------------- Endpoints ----------------

@router.post("/connect", status_code=status.HTTP_201_CREATED)
def connect_social_account(
    payload: SocialAccountCreate,
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["id"]

    # Check if account already exists for this user
    from app.services.database import connect as db_connect
    conn = db_connect()
    cursor = conn.cursor()
    
    cursor.execute(
        """
        SELECT id FROM accounts
        WHERE user_id = %s AND platform = %s AND account_username = %s
        """,
        (user_id, payload.platform, payload.account_username),
    )
    
    existing = cursor.fetchone()
    if existing:
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Account '{payload.account_username}' on {payload.platform} already exists"
        )

    # 1️⃣ Create account
    account_id = add_account(
        user_id=user_id,
        platform=payload.platform,
        account_username=payload.account_username,
        password=payload.password,
    )

    response_data = {
        "id": account_id,
        "platform": payload.platform,
        "account_username": payload.account_username,
        "group_id": payload.group_id,
        "status": "connected",
        "message": "Account connected successfully"
    }

    # 2️⃣ Optionally attach to group (ownership enforced)
    if payload.group_id is not None:
        # Verify group belongs to user
        cursor.execute(
            """
            SELECT 1
            FROM groups
            WHERE id = %s AND user_id = %s
            """,
            (payload.group_id, user_id),
        )

        if not cursor.fetchone():
            conn.close()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Group not found",
            )

        # Check if account is already in this group
        cursor.execute(
            """
            SELECT 1
            FROM group_accounts
            WHERE group_id = %s AND account_id = %s
            """,
            (payload.group_id, account_id),
        )
        
        if cursor.fetchone():
            conn.close()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Account is already in this group"
            )

        add_account_to_group(payload.group_id, account_id)
        response_data["group_id"] = payload.group_id
        response_data["message"] = "Account connected and added to group successfully"

    conn.close()
    return response_data


@router.get("/", response_model=List[SocialAccountResponse])
def list_social_accounts(user=Depends(get_current_user)):
    rows = get_accounts(user["id"])

    return [
        SocialAccountResponse(
            id=row[0],
            platform=row[1],
            account_username=row[2],
            group_id=None,
            status="connected",
        )
        for row in rows
    ]


@router.post("/{account_id}/groups/{group_id}")
def add_account_group_link(
    account_id: int,
    group_id: int,
    user=Depends(get_current_user),
):
    user_id = user["id"]

    from app.services.database import connect
    conn = connect()
    cursor = conn.cursor()

    # Verify account ownership
    cursor.execute(
        """
        SELECT 1
        FROM accounts
        WHERE id = %s AND user_id = %s
        """,
        (account_id, user_id),
    )
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    # Verify group ownership
    cursor.execute(
        """
        SELECT 1
        FROM groups
        WHERE id = %s AND user_id = %s
        """,
        (group_id, user_id),
    )
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found",
        )

    # Check if account is already in group
    cursor.execute(
        """
        SELECT 1
        FROM group_accounts
        WHERE group_id = %s AND account_id = %s
        """,
        (group_id, account_id),
    )
    if cursor.fetchone():
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account is already in this group"
        )

    add_account_to_group(group_id, account_id)
    conn.close()
    return {
        "success": True,
        "message": "Account added to group successfully"
    }


@router.delete("/{account_id}/groups/{group_id}")
def remove_account_group_link(
    account_id: int,
    group_id: int,
    user=Depends(get_current_user),
):
    user_id = user["id"]

    from app.services.database import connect
    conn = connect()
    cursor = conn.cursor()

    # Verify account ownership
    cursor.execute(
        """
        SELECT 1
        FROM accounts
        WHERE id = %s AND user_id = %s
        """,
        (account_id, user_id),
    )
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    # Verify group ownership
    cursor.execute(
        """
        SELECT 1
        FROM groups
        WHERE id = %s AND user_id = %s
        """,
        (group_id, user_id),
    )
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found",
        )

    remove_account_from_group(group_id, account_id)
    conn.close()
    return {
        "success": True,
        "message": "Account removed from group successfully"
    }


@router.delete("/{account_id}")
def remove_social_account(
    account_id: int,
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["id"]

    accounts = get_accounts(user_id)
    account_ids = [acc[0] for acc in accounts]

    if account_id not in account_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    delete_account(account_id)
    return {
        "success": True,
        "message": "Account disconnected successfully"
    }