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
        WHERE user_id = ?
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



@router.post("/")
def create_group(
    payload: GroupCreate,
    user=Depends(get_current_user),
    db=Depends(get_db)
):
    cursor = db.cursor()

    cursor.execute(
        """
        INSERT INTO groups (group_name, user_id)
        VALUES (?, ?)
        """,
        (payload.group_name, user["id"]),
    )

    db.commit()

    return {
        "id": cursor.lastrowid,
        "name": payload.group_name,
    }



@router.delete("/{group_id}")
def delete_group(group_id: int, db=Depends(get_db)):
    cursor = db.cursor()

    cursor.execute(
        """
        DELETE FROM groups
        WHERE id = ?
        """,
        (group_id,),
    )

    db.commit()
    return {"success": True}


@router.get("/{group_id}/accounts")
def group_accounts(group_id: int, db=Depends(get_db)):
    cursor = db.cursor()

    cursor.execute(
        """
        SELECT
            a.id,
            a.user_id,
            a.platform,
            a.account_username
        FROM accounts a
        JOIN group_accounts ga ON ga.account_id = a.id
        WHERE ga.group_id = ?
        ORDER BY a.id DESC
        """,
        (group_id,),
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
def add_account_to_group(group_id: int, account_id: int, db=Depends(get_db)):
    cursor = db.cursor()

    cursor.execute(
        """
        INSERT OR IGNORE INTO group_accounts (group_id, account_id)
        VALUES (?, ?)
        """,
        (group_id, account_id),
    )

    db.commit()
    return {"success": True}


@router.delete("/{group_id}/accounts/{account_id}")
def remove_account_from_group(group_id: int, account_id: int, db=Depends(get_db)):
    cursor = db.cursor()

    cursor.execute(
        """
        DELETE FROM group_accounts
        WHERE group_id = ? AND account_id = ?
        """,
        (group_id, account_id),
    )

    db.commit()
    return {"success": True}
