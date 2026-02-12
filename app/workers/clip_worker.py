"""
AI Clip Worker

Responsibilities:
- Orchestrate AI-based short clip generation
- Support both API-triggered and DB-backed jobs
"""

import traceback
import uuid
import os
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
# CLIP DURATION RULES
# =========================================================

MIN_CLIP_DURATION = 30
MAX_CLIP_DURATION = 60


def normalize_segments(
    segments: List[Dict],
    max_clips: int,
) -> List[Dict]:

    normalized: List[Dict] = []

    for seg in segments[:max_clips]:
        start = float(seg["start"])
        end = float(seg["end"])
        reason = seg.get("reason", "")

        if end - start < MIN_CLIP_DURATION:
            end = start + MIN_CLIP_DURATION

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
# SHARED SOURCE RESOLUTION
# =========================================================

def resolve_video_source(
    source_url: Optional[str],
    local_video_path: Optional[str],
) -> str:

    if local_video_path and os.path.exists(local_video_path):
        return local_video_path

    if source_url:
        return download_youtube_video(source_url)

    raise ValueError("No valid video source provided")


# =========================================================
# API PIPELINE
# =========================================================

def run_clip_pipeline(
    source_url: Optional[str] = None,
    local_video_path: Optional[str] = None,
    max_clips: int = 3,
    clip_length: int = 30,
    style: str = "highlight",
) -> List[Dict]:

    video_path = resolve_video_source(source_url, local_video_path)

    transcript = transcribe_video(video_path)

    raw_segments = select_segments(
        transcript=transcript,
        max_clips=max_clips,
        clip_length=clip_length,
        style=style,
    )

    if not raw_segments:
        raise RuntimeError("AI did not return any usable segments")

    segments = normalize_segments(raw_segments, max_clips)

    if not segments:
        raise RuntimeError("No valid segments after normalization")

    results: List[Dict] = []

    for segment in segments:
        srt_path = None
        if transcript:
            try:
                srt_path = generate_srt_for_segment(transcript, segment)
            except RuntimeError:
                pass

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
# DB BACKGROUND WORKER
# =========================================================

def run_clip_job(job_id: int):

    try:
        job = get_clip_job(job_id)
        if not job:
            raise RuntimeError(f"Clip job {job_id} not found")

        update_clip_job_status(job_id, "processing", progress=5)

        video_path = resolve_video_source(
            job.get("source_url"),
            job.get("local_video_path"),
        )

        update_clip_job_status(job_id, "processing", progress=20)

        transcript = transcribe_video(video_path)
        update_clip_job_status(job_id, "processing", progress=40)

        raw_segments = select_segments(
            transcript=transcript,
            max_clips=job["max_clips"],
            clip_length=job["clip_length"],
            style=job["style"],
        )

        if not raw_segments:
            raise RuntimeError("AI did not return any usable segments")

        segments = normalize_segments(
            raw_segments,
            max_clips=job["max_clips"],
        )

        if not segments:
            raise RuntimeError("No valid segments after normalization")

        update_clip_job_status(job_id, "processing", progress=60)

        total_segments = len(segments)

        for idx, segment in enumerate(segments):

            srt_path = None
            if transcript:
                try:
                    srt_path = generate_srt_for_segment(transcript, segment)
                except RuntimeError:
                    pass

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
