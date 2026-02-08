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


def _format_timestamp(seconds: float) -> str:
    td = timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    millis = int((seconds - total_seconds) * 1000)

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60

    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def generate_srt_for_segment(
    transcript: List[Dict],
    segment: Dict,
) -> str:
    """
    Generates an SRT file for a specific clip segment.

    Returns:
        Path to SRT file (string)
    """

    start = segment["start"]
    end = segment["end"]

    media_root = Path(settings.MEDIA_ROOT)
    subtitles_dir = media_root / "subtitles"
    subtitles_dir.mkdir(parents=True, exist_ok=True)

    srt_path = subtitles_dir / f"{uuid.uuid4()}.srt"

    index = 1
    lines = []

    for t in transcript:
        if t["end"] < start or t["start"] > end:
            continue

        sub_start = max(t["start"], start) - start
        sub_end = min(t["end"], end) - start

        if sub_end <= sub_start:
            continue

        lines.append(str(index))
        lines.append(
            f"{_format_timestamp(sub_start)} --> {_format_timestamp(sub_end)}"
        )
        lines.append(t["text"])
        lines.append("")
        index += 1

    if not lines:
        raise RuntimeError("No subtitles generated for clip")

    srt_path.write_text("\n".join(lines), encoding="utf-8")

    return str(srt_path)
