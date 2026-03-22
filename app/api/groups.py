from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from app.services.database import get_db
from app.api.deps import get_current_user


router = APIRouter(
    prefix="/groups",
    tags=["Groups"]
)


# -------------------------
# Schemas
# -------------------------
class GroupCreate(BaseModel):
    group_name: str

    @field_validator("group_name")
    @classmethod
    def validate_group_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("group_name cannot be empty.")
        if len(v.strip()) > 100:
            raise ValueError("group_name cannot exceed 100 characters.")
        return v.strip()


class GroupUpdate(BaseModel):
    group_name: str

    @field_validator("group_name")
    @classmethod
    def validate_group_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("group_name cannot be empty.")
        if len(v.strip()) > 100:
            raise ValueError("group_name cannot exceed 100 characters.")
        return v.strip()


# -------------------------
# Routes
# -------------------------
@router.get("/")
def list_groups(user=Depends(get_current_user), db=Depends(get_db)):
    cursor = db.cursor()

    cursor.execute(
        """
        SELECT id, group_name
        FROM groups
        WHERE user_id = %s
        ORDER BY id DESC
        """,
        (user["id"],),
    )

    rows = cursor.fetchall()

    return [
        {
            "id": row[0],
            "name": row[1],
        }
        for row in rows
    ]



@router.post("/create")
def create_group(
    payload: GroupCreate,
    user=Depends(get_current_user),
    db=Depends(get_db)
):
    cursor = db.cursor()

    # Check for duplicate group name under this user
    cursor.execute(
        """
        SELECT 1 FROM groups
        WHERE group_name = %s AND user_id = %s
        """,
        (payload.group_name, user["id"]),
    )
    if cursor.fetchone():
        raise HTTPException(
            status_code=409,
            detail=f"You already have a group named '{payload.group_name}'. Please choose a different name.",
        )

    cursor.execute(
        """
        INSERT INTO groups (group_name, user_id)
        VALUES (%s, %s)
        RETURNING id
        """,
        (payload.group_name, user["id"]),
    )

    row = cursor.fetchone()
    db.commit()

    return {
        "id": row[0],
        "name": payload.group_name,
    }



@router.patch("/{group_id}")
def update_group(
    group_id: int,
    payload: GroupUpdate,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    cursor = db.cursor()

    cursor.execute(
        """
        UPDATE groups
        SET group_name = %s
        WHERE id = %s AND user_id = %s
        RETURNING id, group_name
        """,
        (payload.group_name, group_id, user["id"]),
    )

    row = cursor.fetchone()
    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"Group with ID {group_id} was not found or you do not have permission to update it.",
        )

    db.commit()
    return {
        "id": row[0],
        "name": row[1],
    }


@router.delete("/{group_id}")
def delete_group(
    group_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    cursor = db.cursor()

    # Ensure group belongs to user
    cursor.execute(
        """
        SELECT 1
        FROM groups
        WHERE id = %s AND user_id = %s
        """,
        (group_id, user["id"]),
    )

    if not cursor.fetchone():
        raise HTTPException(
            status_code=404,
            detail=f"Group with ID {group_id} was not found or you do not have permission to delete it.",
        )

    cursor.execute(
        """
        DELETE FROM groups
        WHERE id = %s AND user_id = %s
        """,
        (group_id, user["id"]),
    )

    db.commit()
    return {"success": True}



@router.get("/{group_id}/accounts")
def group_accounts(
    group_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    cursor = db.cursor()

    # Verify ownership of group
    cursor.execute(
        """
        SELECT 1
        FROM groups
        WHERE id = %s AND user_id = %s
        """,
        (group_id, user["id"]),
    )

    if not cursor.fetchone():
        raise HTTPException(
            status_code=404,
            detail=f"Group with ID {group_id} was not found or you do not have permission to access it.",
        )

    cursor.execute(
        """
        SELECT
            a.id,
            a.user_id,
            a.platform,
            a.account_username
        FROM accounts a
        JOIN group_accounts ga ON ga.account_id = a.id
        WHERE ga.group_id = %s
          AND a.user_id = %s
        ORDER BY a.id DESC
        """,
        (group_id, user["id"]),
    )

    rows = cursor.fetchall()

    return [
        {
            "id": row[0],
            "userId": row[1],
            "platform": row[2],
            "accountUsername": row[3],
        }
        for row in rows
    ]



@router.post("/{group_id}/accounts/{account_id}")
def add_account_to_group(
    group_id: int,
    account_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    cursor = db.cursor()

    # Verify group ownership
    cursor.execute(
        """
        SELECT 1
        FROM groups
        WHERE id = %s AND user_id = %s
        """,
        (group_id, user["id"]),
    )
    if not cursor.fetchone():
        raise HTTPException(
            status_code=404,
            detail=f"Group with ID {group_id} was not found or you do not have permission to modify it.",
        )

    # Verify account ownership
    cursor.execute(
        """
        SELECT 1
        FROM accounts
        WHERE id = %s AND user_id = %s
        """,
        (account_id, user["id"]),
    )
    if not cursor.fetchone():
        raise HTTPException(
            status_code=404,
            detail=f"Social account with ID {account_id} was not found or does not belong to your account.",
        )

    # Check if account is already in this group
    cursor.execute(
        """
        SELECT 1 FROM group_accounts
        WHERE group_id = %s AND account_id = %s
        """,
        (group_id, account_id),
    )
    if cursor.fetchone():
        raise HTTPException(
            status_code=409,
            detail=f"Social account with ID {account_id} is already a member of group {group_id}.",
        )

    cursor.execute(
        """
        INSERT INTO group_accounts (group_id, account_id)
        VALUES (%s, %s)
        """,
        (group_id, account_id),
    )

    db.commit()
    return {"success": True}



@router.delete("/{group_id}/accounts/{account_id}")
def remove_account_from_group(
    group_id: int,
    account_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    cursor = db.cursor()

    # Verify group ownership
    cursor.execute(
        """
        SELECT 1
        FROM groups
        WHERE id = %s AND user_id = %s
        """,
        (group_id, user["id"]),
    )
    if not cursor.fetchone():
        raise HTTPException(
            status_code=404,
            detail=f"Group with ID {group_id} was not found or you do not have permission to modify it.",
        )

    # Check if the account is actually in this group before deleting
    cursor.execute(
        """
        SELECT 1 FROM group_accounts
        WHERE group_id = %s AND account_id = %s
        """,
        (group_id, account_id),
    )
    if not cursor.fetchone():
        raise HTTPException(
            status_code=404,
            detail=f"Social account with ID {account_id} is not a member of group {group_id}.",
        )

    cursor.execute(
        """
        DELETE FROM group_accounts
        WHERE group_id = %s AND account_id = %s
        """,
        (group_id, account_id),
    )

    db.commit()
    return {"success": True}
