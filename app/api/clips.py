from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from typing import Optional, List
import shutil
import os
import uuid
from pathlib import Path

from app.api.schemas.clips import ClipResponse
from app.workers.clip_worker import run_clip_job
from app.services.database import (
    create_clip_job,
    get_clip_job,
    get_clips_for_job,
)
from app.config import settings

router = APIRouter(prefix="/api/clips", tags=["clips"])


# =========================================================
# TEMP USER RESOLUTION (REPLACE WITH REAL AUTH LATER)
# =========================================================

def get_current_user_id() -> int:
    return 1  # TODO: replace with authenticated user id


# =========================================================
# CREATE CLIP JOB
# =========================================================

@router.post("/jobs")
def create_clip_job_endpoint(
    background_tasks: BackgroundTasks,
    video_file: Optional[UploadFile] = File(None),
    source_url: Optional[str] = Form(None),
    clip_length: int = Form(30),
    max_clips: int = Form(3),
    style: str = Form("highlight"),
):
    if not video_file and not source_url:
        raise HTTPException(
            status_code=400,
            detail="Either video_file or source_url must be provided",
        )

    user_id = get_current_user_id()

    input_path = None

    # Save uploaded file
    if video_file:
        uploads_dir = Path(settings.MEDIA_ROOT) / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)

        input_path = uploads_dir / f"{uuid.uuid4()}_{video_file.filename}"

        with open(input_path, "wb") as f:
            shutil.copyfileobj(video_file.file, f)

        input_path = str(input_path)

    # Create DB job
    job_id = create_clip_job(
        user_id=user_id,
        source_url=source_url,
        local_video_path=input_path,
        clip_length=clip_length,
        max_clips=max_clips,
        style=style,
    )

    # Run background worker
    background_tasks.add_task(run_clip_job, job_id)

    return {
        "job_id": job_id,
        "status": "queued",
        "progress": 0,
    }


# =========================================================
# POLL JOB STATUS
# =========================================================

@router.get("/jobs/{job_id}")
def get_clip_job_status(job_id: int):
    job = get_clip_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": job["id"],
        "status": job["status"],
        "progress": job["progress"],
        "error": job.get("error"),
    }


# =========================================================
# FETCH GENERATED CLIPS
# =========================================================

@router.get("/jobs/{job_id}/clips", response_model=List[ClipResponse])
def get_generated_clips(job_id: int):
    job = get_clip_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail="Clips not ready yet",
        )

    clips = get_clips_for_job(job_id)

    results = []

    for c in clips:
        file_path = Path(c["file_path"]).resolve()

        # Extract only filename
        filename = file_path.name

        # Public URL served via /media mount
        public_url = f"/media/clips/{filename}"

        results.append({
            "clip_id": str(c["id"]),
            "video_url": public_url,
            "duration": c["duration"],
            "reason": None,
        })

    return results
