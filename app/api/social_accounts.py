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

@router.post("/connect")
def connect_social_account(
    payload: SocialAccountCreate,
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["id"]

    # 1️⃣ Create account
    account_id = add_account(
        user_id=user_id,
        platform=payload.platform,
        account_username=payload.account_username,
        password=payload.password,
    )

    # 2️⃣ Optionally attach to group (ownership enforced)
    if payload.group_id is not None:
        from app.services.database import connect

        conn = connect()
        cursor = conn.cursor()

        # Verify group belongs to user
        cursor.execute(
            """
            SELECT 1
            FROM groups
            WHERE id = ? AND user_id = ?
            """,
            (payload.group_id, user_id),
        )

        if not cursor.fetchone():
            conn.close()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Group not found",
            )

        add_account_to_group(account_id, payload.group_id)
        conn.close()

    return {
        "id": account_id,
        "platform": payload.platform,
        "account_username": payload.account_username,
        "group_id": payload.group_id,
        "status": "connected",
    }




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
        WHERE id = ? AND user_id = ?
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
        WHERE id = ? AND user_id = ?
        """,
        (group_id, user_id),
    )
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found",
        )

    add_account_to_group(account_id, group_id)
    conn.close()
    return {"success": True}




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
        WHERE id = ? AND user_id = ?
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
        WHERE id = ? AND user_id = ?
        """,
        (group_id, user_id),
    )
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found",
        )

    remove_account_from_group(account_id, group_id)
    conn.close()
    return {"success": True}



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
    return {"success": True}
