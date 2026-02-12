from fastapi import APIRouter, Depends
from app.api.deps import get_current_user
from app.services.database import (
    get_post_overview,
    get_platform_breakdown,
    get_daily_post_counts,
    get_engagement_stats,
    calculate_account_health,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview")
def get_analytics(current_user=Depends(get_current_user)):
    user_id = current_user["id"]

    overview = get_post_overview(user_id)
    platform = get_platform_breakdown(user_id)
    activity = get_daily_post_counts(user_id)
    engagement = get_engagement_stats(user_id)
    health = calculate_account_health(user_id)

    return {
        "overview": overview,
        "platform_breakdown": platform,
        "posting_activity": activity,
        "engagement": engagement,
        "account_health": health
    }
