from fastapi import APIRouter, UploadFile, File, HTTPException
from typing import List
import shutil
import os
import uuid

from app.api.schemas.clips import (
    YouTubeClipRequest,
    ClipJobResponse,
    ClipResponse,
)
from app.workers.clip_worker import run_clip_pipeline
from app.config import settings

router = APIRouter(prefix="/api/clips", tags=["clips"])


@router.post("/from-youtube", response_model=ClipJobResponse)
def create_clips_from_youtube(payload: YouTubeClipRequest):
    """
    Generate short clips from a YouTube video URL.
    """

    try:
        clips = run_clip_pipeline(
            source_url=str(payload.youtube_url),
            max_clips=payload.max_clips,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "clips": [
            ClipResponse(
                clip_id=c["clip_id"],
                video_path=c["video_path"],
                duration=c["duration"],
                reason=c.get("reason"),
            )
            for c in clips
        ]
    }


@router.post("/from-upload", response_model=ClipJobResponse)
def create_clips_from_upload(
    file: UploadFile = File(...),
    max_clips: int = 3,
):
    """
    Generate clips from a locally uploaded video.
    """

    uploads_dir = f"{settings.MEDIA_ROOT}/uploads"
    os.makedirs(uploads_dir, exist_ok=True)

    input_path = os.path.join(
        uploads_dir,
        f"{uuid.uuid4()}_{file.filename}"
    )

    try:
        with open(input_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        clips = run_clip_pipeline(
            local_video_path=input_path,
            max_clips=max_clips,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "clips": [
            ClipResponse(
                clip_id=c["clip_id"],
                video_path=c["video_path"],
                duration=c["duration"],
                reason=c.get("reason"),
            )
            for c in clips
        ]
    }
