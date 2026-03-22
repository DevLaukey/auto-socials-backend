from fastapi import APIRouter, Depends, HTTPException, status, Body
from pydantic import BaseModel, field_validator, ConfigDict
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
    model_config = ConfigDict(extra='forbid')  # This will reject extra fields
    
    platform: str
    account_username: str
    password: str
    group_id: Optional[int] = None

    @field_validator("platform", mode="before")
    @classmethod
    def validate_platform(cls, v):
        """Validate and normalize platform field."""
        # Handle None or non-string values
        if v is None:
            raise ValueError("Platform cannot be None")
        
        # Convert to string if needed and strip
        v_str = str(v).strip()
        
        # Check if empty
        if not v_str:
            raise ValueError("Platform cannot be empty")
        
        # Normalize to lowercase
        normalized = v_str.lower()
        
        # Check if supported
        if normalized not in SUPPORTED_PLATFORMS:
            # Try to find a match ignoring case
            for supported in SUPPORTED_PLATFORMS:
                if supported.lower() == normalized:
                    return supported
            
            # If no match found, raise error with supported platforms
            raise ValueError(
                f"Platform '{v_str}' is not supported. "
                f"Supported platforms are: {', '.join(sorted(SUPPORTED_PLATFORMS))}."
            )
        
        return normalized

    @field_validator("account_username", mode="before")
    @classmethod
    def validate_username(cls, v):
        """Validate username field."""
        if v is None:
            raise ValueError("account_username cannot be None")
        
        # Convert to string and strip
        v_str = str(v).strip()
        
        if not v_str:
            raise ValueError("account_username cannot be empty.")
        
        return v_str

    @field_validator("password", mode="before")
    @classmethod
    def validate_password(cls, v):
        """Validate password field."""
        if v is None:
            raise ValueError("Password cannot be None")
        
        # Convert to string
        v_str = str(v)
        
        if len(v_str) < 6:
            raise ValueError("Password must be at least 6 characters long.")
        
        return v_str


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
    
    # Log the incoming payload for debugging (remove in production)
    print(f"Connecting social account for user {user_id}: platform={payload.platform}, username={payload.account_username}")

    # 1️⃣ Create account
    try:
        account_id = add_account(
            user_id=user_id,
            platform=payload.platform,  # This is already normalized by validator
            account_username=payload.account_username,
            password=payload.password,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create account: {str(e)}"
        )

    # 2️⃣ Optionally attach to group (ownership enforced)
    if payload.group_id is not None:
        from app.services.database import connect

        conn = connect()
        cursor = conn.cursor()

        try:
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
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Group with ID {payload.group_id} does not exist or does not belong to your account.",
                )

            add_account_to_group(payload.group_id, account_id)
        finally:
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

    try:
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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Group with ID {group_id} does not exist or does not belong to your account.",
            )

        add_account_to_group(group_id, account_id)
    finally:
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

    try:
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
    finally:
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