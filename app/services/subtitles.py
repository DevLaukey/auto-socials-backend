"""
Subtitle Generation Service

Responsibilities:
- Convert Whisper transcript segments into SRT files
- Trim subtitles to a specific clip segment
"""

from pathlib import Path
from typing import List, Dict
from datetime import timedelta
import uuid

from app.config import settings


# ---------------------------------------------------------
# Timestamp formatting (SRT-safe)
# ---------------------------------------------------------

def _format_timestamp(seconds: float) -> str:
    """
    Convert seconds to SRT timestamp format (HH:MM:SS,mmm)
    with floating-point safety.
    """
    seconds = max(0.0, round(seconds, 3))

    millis = int((seconds % 1) * 1000)
    total_seconds = int(seconds)

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60

    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


# ---------------------------------------------------------
# Public API
# ---------------------------------------------------------

def generate_srt_for_segment(
    transcript: List[Dict],
    segment: Dict,
) -> str:
    """
    Generates an SRT file for a specific clip segment.

    Returns:
        Path to SRT file (string)
    """

    start = float(segment["start"])
    end = float(segment["end"])

    media_root = Path(settings.MEDIA_ROOT)
    subtitles_dir = media_root / "subtitles"
    subtitles_dir.mkdir(parents=True, exist_ok=True)

    srt_path = subtitles_dir / f"{uuid.uuid4()}.srt"

    index = 1
    lines: List[str] = []

    # Readability constraints for Shorts/Reels
    MIN_SUB_DURATION = 0.4  # seconds
    MAX_LINE_LENGTH = 80

    for t in transcript:
        t_start = float(t["start"])
        t_end = float(t["end"])

        # Skip subtitles completely outside clip
        if t_end < start or t_start > end:
            continue

        sub_start = max(t_start, start) - start
        sub_end = min(t_end, end) - start

        # Skip invalid or unreadable subtitles
        if sub_end - sub_start < MIN_SUB_DURATION:
            continue

        text = t.get("text", "").strip()
        if not text:
            continue

        # Prevent oversized subtitle blocks
        if len(text) > MAX_LINE_LENGTH:
            text = text[:MAX_LINE_LENGTH].rsplit(" ", 1)[0] + "…"

        lines.append(str(index))
        lines.append(
            f"{_format_timestamp(sub_start)} --> {_format_timestamp(sub_end)}"
        )
        lines.append(text)
        lines.append("")
        index += 1

    if not lines:
        raise RuntimeError("No subtitles generated for clip")

    srt_path.write_text("\n".join(lines), encoding="utf-8")

    return str(srt_path)
