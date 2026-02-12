"""
Whisper Transcription Service

Responsibilities:
- Transcribe video/audio files using Whisper
- Return timestamped segments usable for AI clipping
- Gracefully handle videos with NO speech
"""

import os
import whisper
from typing import List, Dict


# ---------------------------------------------------------
# Load model ONCE per worker
# ---------------------------------------------------------

WHISPER_MODEL = whisper.load_model(
    "base"  # Use "small"/"medium" if GPU is available
)


# ---------------------------------------------------------
# Public API
# ---------------------------------------------------------

def transcribe_video(video_path: str) -> List[Dict]:
    """
    Transcribes a video file and returns timestamped segments.

    Returns:
    [
        {
            "start": float,
            "end": float,
            "text": str
        }
    ]
    """

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    result = WHISPER_MODEL.transcribe(
        video_path,
        fp16=False,     # CPU-safe
        verbose=False,
    )

    raw_segments = result.get("segments", [])

    segments: List[Dict] = []

    # Minimum usable speech duration (seconds)
    MIN_SEGMENT_DURATION = 0.3

    for seg in raw_segments:
        start = float(seg.get("start", 0))
        end = float(seg.get("end", 0))
        text = seg.get("text", "").strip()

        # Skip invalid segments
        if not text:
            continue

        if end <= start:
            continue

        if end - start < MIN_SEGMENT_DURATION:
            continue

        segments.append(
            {
                "start": round(start, 3),
                "end": round(end, 3),
                "text": text,
            }
        )

    # IMPORTANT:
    # Do NOT crash on music-only or silent videos
    # Let downstream logic decide what to do
    if not segments:
        return []

    return segments
