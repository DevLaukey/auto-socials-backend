from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
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

    cursor.execute(
        """
        INSERT INTO group_accounts (group_id, account_id)
        VALUES (%s, %s)
        ON CONFLICT (group_id, account_id) DO NOTHING
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
        raise HTTPException(status_code=404, detail="Group not found")

    cursor.execute(
        """
        DELETE FROM group_accounts
        WHERE group_id = %s AND account_id = %s
        """,
        (group_id, account_id),
    )

    db.commit()
    return {"success": True}
