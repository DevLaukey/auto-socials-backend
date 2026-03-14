from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional

from app.api.deps import get_current_user
from app.services.database import (
    add_proxy,
    get_all_proxies,
    get_proxy_by_id,
    update_proxy_status,
    delete_proxy,
)

router = APIRouter(
    prefix="/proxies",
    tags=["proxies"],
)

# -------------------------
# Schemas
# -------------------------

class ProxyCreate(BaseModel):
    proxy_address: str
    proxy_type: str  # http, https, socks5, etc
    username: Optional[str] = None
    password: Optional[str] = None


class ProxyOut(BaseModel):
    id: int
    proxy_address: str
    proxy_type: str
    username: Optional[str] = None
    is_active: bool
    created_at: Optional[str] = None


class ProxyActivate(BaseModel):
    is_active: bool


# -------------------------
# Endpoints
# -------------------------

@router.get("/proxy", response_model=List[ProxyOut])
def list_proxies(user=Depends(get_current_user)):
    """
    Return all proxies belonging to the authenticated user.
    """
    user_id = user["id"]

    rows = get_all_proxies(user_id)
    return [
        {
            "id": r[0],
            "proxy_address": r[1],
            "proxy_type": r[2],
            "username": r[4] if len(r) > 4 else None,
            "is_active": bool(r[3]),
            "created_at": r[5].isoformat() if len(r) > 5 and r[5] else None,
        }
        for r in rows
    ]


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_proxy(payload: ProxyCreate, user=Depends(get_current_user)):
    """
    Add a proxy owned by the authenticated user.
    Supports authenticated proxies with username/password.
    """
    user_id = user["id"]

    success = add_proxy(
        proxy_address=payload.proxy_address,
        proxy_type=payload.proxy_type,
        user_id=user_id,
        username=payload.username,
        password=payload.password,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Proxy already exists or could not be added",
        )

    return {"message": "Proxy added successfully"}


@router.patch("/{proxy_id}/activate")
def activate_proxy(proxy_id: int, user=Depends(get_current_user)):
    """
    Activate a proxy owned by the authenticated user.
    """
    user_id = user["id"]

    proxy = get_proxy_by_id(proxy_id, user_id)
    if not proxy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proxy not found",
        )

    update_proxy_status(proxy_id, True, user_id)
    return {"message": "Proxy activated"}


@router.patch("/{proxy_id}/deactivate")
def deactivate_proxy(proxy_id: int, user=Depends(get_current_user)):
    """
    Deactivate a proxy owned by the authenticated user.
    """
    user_id = user["id"]

    proxy = get_proxy_by_id(proxy_id, user_id)
    if not proxy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proxy not found",
        )

    update_proxy_status(proxy_id, False, user_id)
    return {"message": "Proxy deactivated"}


@router.delete("/{proxy_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_proxy(proxy_id: int, user=Depends(get_current_user)):
    """
    Delete a proxy owned by the authenticated user.
    """
    user_id = user["id"]

    proxy = get_proxy_by_id(proxy_id, user_id)
    if not proxy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proxy not found",
        )

    delete_proxy(proxy_id, user_id)
    return