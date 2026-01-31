from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class AdminUserOut(BaseModel):
    id: int
    email: str
    is_active: bool
    is_admin: bool
    created_at: datetime

    # Subscription info (nullable)
    plan_name: Optional[str]
    subscription_active: Optional[bool]
    subscription_start: Optional[datetime]
    subscription_end: Optional[datetime]


class AdminUserStatusUpdate(BaseModel):
    is_active: bool


class AdminExtendSubscription(BaseModel):
    days: int
