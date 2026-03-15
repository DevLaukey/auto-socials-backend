from fastapi import APIRouter, Depends, HTTPException, status, Body
from pydantic import BaseModel, field_validator
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

SUPPORTED_PLATFORMS = {"instagram", "youtube", "tiktok", "twitter", "facebook"}

# ---------------- Schemas ----------------

class SocialAccountCreate(BaseModel):
    platform: str
    account_username: str
    password: str
    group_id: Optional[int] = None

    @field_validator("platform")
    @classmethod
    def validate_platform(cls, v: str) -> str:
        normalized = v.strip().lower()
        if normalized not in SUPPORTED_PLATFORMS:
            raise ValueError(
                f"Platform '{v}' is not supported. "
                f"Supported platforms are: {', '.join(sorted(SUPPORTED_PLATFORMS))}."
            )
        return normalized

    @field_validator("account_username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("account_username cannot be empty.")
        return v.strip()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not v or len(v) < 6:
            raise ValueError("Password must be at least 6 characters long.")
        return v


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
    try:
        account_id = add_account(
            user_id=user_id,
            platform=payload.platform,
            account_username=payload.account_username,
            password=payload.password,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

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
            WHERE id = %s AND user_id = %s
            """,
            (payload.group_id, user_id),
        )

        if not cursor.fetchone():
            conn.close()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Group with ID {payload.group_id} does not exist or does not belong to your account.",
            )

        add_account_to_group(payload.group_id, account_id)
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
        WHERE id = %s AND user_id = %s
        """,
        (account_id, user_id),
    )
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Social account with ID {account_id} does not exist or does not belong to your account.",
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
            detail=f"Group with ID {group_id} does not exist or does not belong to your account.",
        )

    add_account_to_group(group_id, account_id)
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
        WHERE id = %s AND user_id = %s
        """,
        (account_id, user_id),
    )
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Social account with ID {account_id} does not exist or does not belong to your account.",
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
            detail=f"Group with ID {group_id} does not exist or does not belong to your account.",
        )

    remove_account_from_group(group_id, account_id)
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
            detail=f"Social account with ID {account_id} does not exist or does not belong to your account.",
        )

    delete_account(account_id)
    return {"success": True}
