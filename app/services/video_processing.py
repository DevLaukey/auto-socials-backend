"""
Video Processing Service (FFmpeg)

Responsibilities:
- Generate short video clips from long-form videos
- Crop to vertical (9:16) format for Shorts/Reels
- Optionally burn-in subtitles
- Handle videos WITH or WITHOUT audio
- Be Windows-safe for FFmpeg
"""

from pathlib import Path
import subprocess
import uuid
from typing import Dict, Optional, Tuple

from app.config import settings


def _ffmpeg_safe_path(path: Path) -> str:
    """
    Convert a path into a format FFmpeg understands on Windows.
    """
    # Convert to posix and escape drive colon (C:)
    return path.as_posix().replace(":", r"\:")


def generate_clip(
    video_path: str,
    segment: Dict,
    subtitles_path: Optional[str] = None,
) -> Tuple[str, int]:

    video_path = Path(video_path).resolve()
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    # ---- Segment validation ----
    start = float(segment["start"])
    end = float(segment["end"])
    duration = int(end - start)

    if duration <= 0:
        raise ValueError("Invalid clip duration")

    # ---- Output paths ----
    media_root = Path(settings.MEDIA_ROOT).resolve()
    output_dir = media_root / "clips"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"{uuid.uuid4()}.mp4"

    # ---- Base vertical crop (9:16) ----
    # Uses input height as reference to avoid invalid sizes
    crop_filter = (
        "crop="
        "ih*9/16:"
        "ih:"
        "(iw-ih*9/16)/2:"
        "0"
    )

    filters = [crop_filter]

    # ---- Optional burn-in subtitles ----
    if subtitles_path:
        sub_path = Path(subtitles_path).resolve()
        if not sub_path.exists():
            raise FileNotFoundError(f"Subtitles file not found: {sub_path}")

        sub_path_safe = _ffmpeg_safe_path(sub_path)

        subtitles_filter = (
            f"subtitles='{sub_path_safe}':"
            "force_style="
            "'FontName=Arial,"
            "FontSize=28,"
            "PrimaryColour=&HFFFFFF&,"
            "OutlineColour=&H000000&,"
            "Outline=2,"
            "Shadow=1,"
            "Alignment=2'"
        )

        filters.append(subtitles_filter)

    # ---- Final filter chain ----
    vf_arg = ",".join(filters)

    # ---- FFmpeg command ----
    command = [
        "ffmpeg",
        "-y",
        "-ss", str(start),
        "-to", str(end),
        "-i", str(video_path),
        "-vf", vf_arg,
        "-map", "0:v:0",
        "-map", "0:a?",  # audio is OPTIONAL
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-movflags", "+faststart",
        str(output_path),
    ]

    # ---- Run FFmpeg ----
    try:
        subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            "FFmpeg failed:\n"
            + e.stderr.decode(errors="ignore")
        )

    if not output_path.exists():
        raise RuntimeError("FFmpeg did not produce output file")

    return str(output_path), duration
