from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks, Depends
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
    get_all_clip_jobs_for_user,  # Add this function
    delete_clip_job_and_clips,    # Add this function
)
from app.config import settings
from app.api.deps import get_current_user

router = APIRouter(prefix="/api/clips", tags=["clips"])

# =========================================================
# GET ALL CLIP JOBS FOR USER
# =========================================================

@router.get("/jobs/all")
def get_all_jobs(current_user: dict = Depends(get_current_user)):
    """Get all clip jobs for the current user with their clips"""
    user_id = current_user["id"]
    
    jobs = get_all_clip_jobs_for_user(user_id)
    
    # For each job, get its clips and ensure they have valid URLs
    result = []
    for job in jobs:
        clips = get_clips_for_job(job["id"])
        
        # Process clips to ensure video_url is always present
        processed_clips = []
        for clip in clips:
            file_path = Path(clip["file_path"]).resolve()
            try:
                media_root = Path(settings.MEDIA_ROOT).resolve()
                relative_path = file_path.relative_to(media_root)
                public_url = f"/media/{relative_path.as_posix()}"
            except ValueError:
                public_url = f"/media/clips/{file_path.name}"
            
            processed_clips.append({
                "clip_id": str(clip["id"]),
                "video_url": public_url,
                "duration": clip["duration"],
                "reason": None,
                "created_at": clip["created_at"].isoformat() if clip.get("created_at") else None,
                "job_id": job["id"]
            })
        
        job["clips"] = processed_clips
        result.append(job)
    
    return result


# =========================================================
# GET SINGLE JOB WITH CLIPS
# =========================================================

@router.get("/jobs/{job_id}/with-clips")
def get_job_with_clips(
    job_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Get a specific job with its clips"""
    job = get_clip_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized to view this job")
    
    clips = get_clips_for_job(job_id)
    job["clips"] = clips
    
    return job


# =========================================================
# DELETE CLIP JOB
# =========================================================

@router.delete("/jobs/{job_id}")
def delete_job(
    job_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Delete a clip job and all its clips"""
    job = get_clip_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized to delete this job")
    
    # Delete the job and its clips from database
    delete_clip_job_and_clips(job_id)
    
    # Optionally delete the actual video files from disk
    try:
        for clip in get_clips_for_job(job_id):
            clip_path = Path(clip["file_path"])
            if clip_path.exists():
                clip_path.unlink()
    except Exception as e:
        print(f"Error deleting clip files: {e}")
    
    return {"success": True, "message": "Clip job deleted successfully"}


# =========================================================
# CREATE CLIP JOB (Existing)
# =========================================================

@router.post("/jobs")
def create_clip_job_endpoint(
    background_tasks: BackgroundTasks,
    video_file: Optional[UploadFile] = File(None),
    source_url: Optional[str] = Form(None),
    clip_length: int = Form(30),
    max_clips: int = Form(3),
    style: str = Form("highlight"),
    current_user: dict = Depends(get_current_user)
):
    # ... existing code with user_id from current_user ...
    if not video_file and not source_url:
        raise HTTPException(
            status_code=400,
            detail="Either video_file or source_url must be provided",
        )

    user_id = current_user["id"]

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
# POLL JOB STATUS (Existing)
# =========================================================

@router.get("/jobs/{job_id}")
def get_clip_job_status(
    job_id: int,
    current_user: dict = Depends(get_current_user)
):
    job = get_clip_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized to view this job")

    return {
        "job_id": job["id"],
        "status": job["status"],
        "progress": job["progress"],
        "error": job.get("error"),
    }


# =========================================================
# FETCH GENERATED CLIPS (Existing)
# =========================================================

@router.get("/jobs/{job_id}/clips", response_model=List[ClipResponse])
def get_generated_clips(
    job_id: int,
    current_user: dict = Depends(get_current_user)
):
    job = get_clip_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized to view this job")

    if job["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail="Clips not ready yet",
        )

    clips = get_clips_for_job(job_id)

    results = []

    for c in clips:
        file_path = Path(c["file_path"]).resolve()
        
        try:
            media_root = Path(settings.MEDIA_ROOT).resolve()
            relative_path = file_path.relative_to(media_root)
            public_url = f"/media/{relative_path.as_posix()}"
        except ValueError:
            public_url = f"/media/clips/{file_path.name}"

        results.append({
            "clip_id": str(c["id"]),
            "video_url": public_url,
            "duration": c["duration"],
            "reason": None,
            "created_at": c["created_at"].isoformat() if c.get("created_at") else None,
        })

    return results