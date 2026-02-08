"""
Whisper Transcription Service

Responsibilities:
- Transcribe video/audio files using Whisper
- Return timestamped segments usable for AI clipping

"""

import os
import whisper
import tempfile


# Load model ONCE per worker
WHISPER_MODEL = whisper.load_model("base") # Change to "small" or "medium" with GPU resources for speed.


def transcribe_video(video_path: str) -> list[dict]:
    """
    Transcribes a video file and returns timestamped segments.

    Returns:
    [
        {
            "start": 12.34,
            "end": 18.90,
            "text": "Some spoken words"
        },
        ...
    ]
    """

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    result = WHISPER_MODEL.transcribe(
        video_path,
        fp16=False,  # safer for CPU environments
    )

    segments = []
    for seg in result.get("segments", []):
        segments.append({
            "start": seg["start"],
            "end": seg["end"],
            "text": seg["text"].strip(),
        })

    if not segments:
        raise RuntimeError("Whisper returned no transcription segments")

    return segments
