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

# These are now soft limits - actual clip length comes from user
MIN_CLIP_DURATION = 15  # Reduced to allow shorter clips if user wants
MAX_CLIP_DURATION = 120  # Increased to allow longer clips if user wants


# =========================================================
# SEGMENT NORMALIZATION
# =========================================================

def normalize_segments(
    segments: List[Dict],
    max_clips: int,
    target_duration: int,  # Add target duration from user
) -> List[Dict]:

    normalized: List[Dict] = []
    
    # Allow some flexibility (±5 seconds) around user's requested duration
    min_allowed = max(MIN_CLIP_DURATION, target_duration - 5)
    max_allowed = min(MAX_CLIP_DURATION, target_duration + 5)

    for seg in segments[:max_clips]:
        start = float(seg["start"])
        end = float(seg["end"])
        reason = seg.get("reason", "")
        
        current_duration = end - start

        # Adjust to match user's requested duration more closely
        if current_duration < min_allowed:
            # Try to extend to reach minimum
            end = start + min_allowed
        elif current_duration > max_allowed:
            # Trim to maximum allowed
            end = start + max_allowed

        # Final validation
        final_duration = end - start
        if final_duration < MIN_CLIP_DURATION or final_duration > MAX_CLIP_DURATION:
            continue
            
        if end <= start:
            continue

        normalized.append({
            "start": start,
            "end": end,
            "reason": reason,
        })

    return normalized


# =========================================================
# SOURCE RESOLUTION
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
# BACKGROUND JOB WORKER
# =========================================================

def run_clip_job(job_id: int):

    try:
        job = get_clip_job(job_id)
        if not job:
            raise RuntimeError(f"Clip job {job_id} not found")

        # ----------------------------------
        # Stage 1: Initial Setup
        # ----------------------------------
        print(f"[Job {job_id}] Starting clip generation")
        update_clip_job_status(job_id, "processing", progress=5)
        print(f"[Job {job_id}] Progress updated to 5%")

        video_path = resolve_video_source(
            job.get("source_url"),
            job.get("local_video_path"),
        )
        print(f"[Job {job_id}] Video source resolved: {video_path}")

        update_clip_job_status(job_id, "processing", progress=15)
        print(f"[Job {job_id}] Progress updated to 15%")

        # ----------------------------------
        # Stage 2: Transcription (heavy)
        # ----------------------------------
        update_clip_job_status(job_id, "processing", progress=25)
        print(f"[Job {job_id}] Starting transcription")

        transcript = transcribe_video(video_path)
        print(f"[Job {job_id}] Transcription complete: {len(transcript)} segments")

        update_clip_job_status(job_id, "processing", progress=45)
        print(f"[Job {job_id}] Progress updated to 45%")

        # ----------------------------------
        # Stage 3: AI Segment Selection
        # ----------------------------------
        print(f"[Job {job_id}] Selecting segments with AI (style: {job['style']}, target length: {job['clip_length']}s)")
        
        raw_segments = select_segments(
            transcript=transcript,
            max_clips=job["max_clips"],
            clip_length=job["clip_length"],  # Pass user's requested length to AI
            style=job["style"],
        )

        if not raw_segments:
            raise RuntimeError("AI did not return any usable segments")
        
        print(f"[Job {job_id}] AI returned {len(raw_segments)} raw segments")

        # Normalize segments with user's target duration
        segments = normalize_segments(
            raw_segments,
            max_clips=job["max_clips"],
            target_duration=job["clip_length"],  # Pass user's requested length
        )

        if not segments:
            raise RuntimeError("No valid segments after normalization")
        
        print(f"[Job {job_id}] Normalized to {len(segments)} segments")

        update_clip_job_status(job_id, "processing", progress=60)
        print(f"[Job {job_id}] Progress updated to 60%")

        # ----------------------------------
        # Stage 4: Clip Generation Loop
        # ----------------------------------
        total_segments = len(segments)
        print(f"[Job {job_id}] Generating {total_segments} clips")

        for idx, segment in enumerate(segments):
            clip_number = idx + 1
            print(f"[Job {job_id}] Generating clip {clip_number}/{total_segments} ({segment['start']:.2f}s - {segment['end']:.2f}s)")

            base_progress = 60
            progress_span = 35  # from 60 to 95

            # Update before starting each clip
            incremental_progress = base_progress + int(
                (idx / total_segments) * progress_span
            )
            update_clip_job_status(
                job_id,
                "processing",
                progress=incremental_progress,
            )
            print(f"[Job {job_id}] Progress updated to {incremental_progress}%")

            srt_path = None
            if transcript:
                try:
                    srt_path = generate_srt_for_segment(transcript, segment)
                    print(f"[Job {job_id}] Subtitles generated: {srt_path}")
                except RuntimeError as e:
                    print(f"[Job {job_id}] Warning: Could not generate subtitles: {e}")
                    pass

            clip_path, duration = generate_clip(
                video_path=video_path,
                segment=segment,
                subtitles_path=srt_path,
            )
            
            print(f"[Job {job_id}] Clip {clip_number} generated: {clip_path} (duration: {duration}s)")

            add_clip(
                clip_job_id=job_id,
                file_path=clip_path,
                duration=duration,
            )
            print(f"[Job {job_id}] Clip {clip_number} saved to database")

            # Update after clip is generated
            incremental_progress = base_progress + int(
                ((idx + 1) / total_segments) * progress_span
            )
            update_clip_job_status(
                job_id,
                "processing",
                progress=incremental_progress,
            )
            print(f"[Job {job_id}] Progress updated to {incremental_progress}%")

        # ----------------------------------
        # Final Completion
        # ----------------------------------
        print(f"[Job {job_id}] All clips generated successfully")
        update_clip_job_status(job_id, "completed", progress=100)
        print(f"[Job {job_id}] Job marked as completed")

    except Exception as e:
        print(f"[Job {job_id}] ERROR: {str(e)}")
        traceback.print_exc()
        mark_clip_job_failed(job_id, str(e))
        print(f"[Job {job_id}] Job marked as failed")