from pydantic import BaseModel, HttpUrl
from typing import Optional, List


class YouTubeClipRequest(BaseModel):
    youtube_url: HttpUrl
    max_clips: int = 3


class UploadClipRequest(BaseModel):
    max_clips: int = 3


class ClipResponse(BaseModel):
    clip_id: str
    video_path: str
    duration: int
    reason: Optional[str]


class ClipJobResponse(BaseModel):
    clips: List[ClipResponse]
