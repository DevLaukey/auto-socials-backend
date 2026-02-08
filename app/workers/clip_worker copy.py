"""
AI Clip Worker

Responsibilities:
- Orchestrate AI-based short clip generation
- Support both API-triggered and DB-backed jobs
"""

import traceback
import uuid
from typing import Optional, List, Dict

from app.services.youtube_downloader import download_youtube_video
from app.services.transcription import transcribe_video
from app.services.clip_ai import select_segments
from app.services.video_processing import generate_clip
from app.services.subtitles import generate_srt_for_segment


from app.services.database import (
    get_clip_job,
    update_clip_job_status,
    add_clip,
    mark_clip_job_failed,
)

# =========================================================
# CLIP DURATION RULES (AUTHORITATIVE)
# =========================================================

MIN_CLIP_DURATION = 30  # seconds
MAX_CLIP_DURATION = 60  # seconds


def normalize_segments(
    segments: List[Dict],
    max_clips: int,
) -> List[Dict]:
    """
    Enforce clip duration constraints regardless of AI output.
    """
    normalized: List[Dict] = []

    for seg in segments[:max_clips]:
        start = float(seg["start"])
        end = float(seg["end"])
        reason = seg.get("reason", "")

        # Ensure minimum duration
        if end - start < MIN_CLIP_DURATION:
            end = start + MIN_CLIP_DURATION

        # Cap maximum duration
        if end - start > MAX_CLIP_DURATION:
            end = start + MAX_CLIP_DURATION

        if end <= start:
            continue

        normalized.append({
            "start": start,
            "end": end,
            "reason": reason,
        })

    return normalized


# =========================================================
# API ENTRY POINT (used by FastAPI)
# =========================================================

def run_clip_pipeline(
    source_url: Optional[str] = None,
    local_video_path: Optional[str] = None,
    max_clips: int = 3,
) -> List[Dict]:
    """
    Run the full clip generation pipeline.

    Returns:
        [
            {
                "clip_id": str,
                "video_path": str,
                "duration": int,
                "reason": str,
            }
        ]
    """

    if not source_url and not local_video_path:
        raise ValueError("Either source_url or local_video_path must be provided")

    # Acquire video
    if source_url:
        video_path = download_youtube_video(source_url)
    else:
        video_path = local_video_path

    # Transcribe
    transcript = transcribe_video(video_path)

    # AI segment selection
    raw_segments = select_segments(transcript)

    if not raw_segments:
        raise RuntimeError("AI did not return any usable segments")

    segments = normalize_segments(raw_segments, max_clips)

    if not segments:
        raise RuntimeError("No valid segments after normalization")

    results: List[Dict] = []

    # Generate clips
    for segment in segments:
        srt_path = generate_srt_for_segment(transcript, segment)

        clip_path, duration = generate_clip(
            video_path=video_path,
            segment=segment,
            subtitles_path=srt_path,
        )

        results.append({
            "clip_id": str(uuid.uuid4()),
            "video_path": clip_path,
            "duration": duration,
            "reason": segment.get("reason"),
        })

    return results


# =========================================================
# DB-BACKED WORKER ENTRY POINT (background jobs)
# =========================================================

def run_clip_job(job_id: int):
    """
    Background worker entry point.

    Uses the SAME logic as run_clip_pipeline,
    but persists results to the database.
    """

    try:
        job = get_clip_job(job_id)
        if not job:
            raise RuntimeError(f"Clip job {job_id} not found")

        update_clip_job_status(job_id, "processing", progress=5)

        video_path = download_youtube_video(job["source_url"])
        update_clip_job_status(job_id, "processing", progress=20)

        transcript = transcribe_video(video_path)
        update_clip_job_status(job_id, "processing", progress=40)

        raw_segments = select_segments(transcript)

        if not raw_segments:
            raise RuntimeError("AI did not return any usable segments")

        segments = normalize_segments(raw_segments, max_clips=len(raw_segments))

        if not segments:
            raise RuntimeError("No valid segments after normalization")

        update_clip_job_status(job_id, "processing", progress=60)

        total_segments = len(segments)

        for idx, segment in enumerate(segments):
            srt_path = generate_srt_for_segment(transcript, segment)

            clip_path, duration = generate_clip(
                video_path=video_path,
                segment=segment,
                subtitles_path=srt_path,
            )

            add_clip(
                clip_job_id=job_id,
                file_path=clip_path,
                duration=duration,
            )

            progress = 60 + int((idx + 1) / total_segments * 35)
            update_clip_job_status(job_id, "processing", progress=progress)

        update_clip_job_status(job_id, "completed", progress=100)

    except Exception as e:
        traceback.print_exc()
        mark_clip_job_failed(job_id, str(e))
