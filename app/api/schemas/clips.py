from pydantic import BaseModel, HttpUrl
from typing import Optional, List, Literal


# =====================================================
# Job creation request (THIS WAS MISSING)
# =====================================================

class ClipJobCreateRequest(BaseModel):
    """
    Request payload sent from frontend to start a clipping job
    """

    # Source
    youtube_url: Optional[HttpUrl] = None

    # Clipping controls
    max_clips: int = 3
    clip_length: int = 30  # seconds
    style: Literal["highlight", "fast_cuts", "podcast"] = "highlight"


# =====================================================
# Individual clip response
# =====================================================

class ClipResponse(BaseModel):
    clip_id: str
    video_url: str
    duration: int
    reason: Optional[str] = None


# =====================================================
# Job result response
# =====================================================

class ClipJobResponse(BaseModel):
    clips: List[ClipResponse]
