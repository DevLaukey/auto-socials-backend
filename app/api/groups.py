from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.services.database import get_db
from app.api.deps import get_current_user
import psycopg2


router = APIRouter(
    prefix="/groups",
    tags=["Groups"]
)


# -------------------------
# Schemas
# -------------------------
class GroupCreate(BaseModel):
    group_name: str


class GroupUpdate(BaseModel):
    group_name: str


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


@router.post("/create", status_code=status.HTTP_201_CREATED)
def create_group(
    payload: GroupCreate,
    user=Depends(get_current_user),
    db=Depends(get_db)
):
    cursor = db.cursor()

    # First check if group already exists for this user
    cursor.execute(
        """
        SELECT id FROM groups 
        WHERE user_id = %s AND LOWER(group_name) = LOWER(%s)
        """,
        (user["id"], payload.group_name),
    )
    
    existing = cursor.fetchone()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Group '{payload.group_name}' already exists"
        )

    try:
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
            "message": "Group created successfully"
        }
    except psycopg2.IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Group '{payload.group_name}' already exists"
        )


@router.patch("/{group_id}")
def update_group(
    group_id: int,
    payload: GroupUpdate,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    cursor = db.cursor()

    # Check if new name already exists for this user (excluding current group)
    cursor.execute(
        """
        SELECT id FROM groups 
        WHERE user_id = %s AND LOWER(group_name) = LOWER(%s) AND id != %s
        """,
        (user["id"], payload.group_name, group_id),
    )
    
    existing = cursor.fetchone()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Group '{payload.group_name}' already exists"
        )

    try:
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
            raise HTTPException(status_code=404, detail="Group not found")

        db.commit()
        return {
            "id": row[0],
            "name": row[1],
            "message": "Group renamed successfully"
        }
    except psycopg2.IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Group '{payload.group_name}' already exists"
        )


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
        raise HTTPException(status_code=404, detail="Group not found")

    cursor.execute(
        """
        DELETE FROM groups
        WHERE id = %s AND user_id = %s
        """,
        (group_id, user["id"]),
    )

    db.commit()
    return {"success": True, "message": "Group deleted successfully"}


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
        raise HTTPException(status_code=404, detail="Group not found")

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
        raise HTTPException(status_code=404, detail="Group not found")

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
        raise HTTPException(status_code=404, detail="Account not found")

    # ✅ CHECK FOR DUPLICATE: Verify account is not already in the group
    cursor.execute(
        """
        SELECT 1
        FROM group_accounts
        WHERE group_id = %s AND account_id = %s
        """,
        (group_id, account_id),
    )
    if cursor.fetchone():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This account is already in the group"
        )

    cursor.execute(
        """
        INSERT INTO group_accounts (group_id, account_id)
        VALUES (%s, %s)
        ON CONFLICT (group_id, account_id) DO NOTHING
        """,
        (group_id, account_id),
    )

    db.commit()
    return {
        "success": True,
        "message": "Account added to group successfully"
    }


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
        raise HTTPException(status_code=404, detail="Group not found")

    cursor.execute(
        """
        DELETE FROM group_accounts
        WHERE group_id = %s AND account_id = %s
        """,
        (group_id, account_id),
    )

    db.commit()
    return {
        "success": True,
        "message": "Account removed from group successfully"
    }