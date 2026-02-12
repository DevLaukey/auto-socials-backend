from fastapi import APIRouter
from app.services.youtube_analytics import fetch_and_update_youtube_stats

router = APIRouter(prefix="/youtube", tags=["youtube"])


@router.post("/refresh-stats")
def refresh_youtube_stats():
    fetch_and_update_youtube_stats()
    return {"message": "YouTube stats updated"}
