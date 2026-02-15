"""
Whisper Transcription Service (OpenAI API)

Responsibilities:
- Transcribe video/audio files using the OpenAI Whisper API
- Return timestamped segments usable for AI clipping
- Gracefully handle videos with NO speech
"""

import os
from typing import List, Dict
from openai import OpenAI
from app.config import settings


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

    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    with open(video_path, "rb") as audio_file:
        result = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )

    raw_segments = result.segments or []

    segments: List[Dict] = []

    # Minimum usable speech duration (seconds)
    MIN_SEGMENT_DURATION = 0.3

    for seg in raw_segments:
        start = float(seg.get("start", 0))
        end = float(seg.get("end", 0))
        text = seg.get("text", "").strip()

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

    if not segments:
        return []

    return segments
