"""
YouTube Downloader Service

Responsibilities:
- Accept either a local file path OR a YouTube URL
- Download YouTube videos using yt-dlp
- Return a local file path usable by FFmpeg / Whisper

"""

import os
import re
import subprocess
import uuid

from app.config import settings


YOUTUBE_REGEX = re.compile(
    r"(https?://)?(www\.)?(youtube\.com|youtu\.be)/"
)


def is_youtube_url(value: str) -> bool:
    return bool(YOUTUBE_REGEX.match(value))


def download_youtube_video(source: str) -> str:
    """
    If source is:
    - local file → return as-is
    - YouTube URL → download and return local path
    """

    # Local upload → skip download
    if os.path.exists(source):
        return source

    # Must be YouTube
    if not is_youtube_url(source):
        raise ValueError("Invalid video source: not a file or YouTube URL")

    output_dir = settings.MEDIA_ROOT + "/videos"
    os.makedirs(output_dir, exist_ok=True)

    output_path = os.path.join(
        output_dir,
        f"{uuid.uuid4()}.mp4"
    )

    command = [
        "yt-dlp",
        "-f", "mp4",
        "-o", output_path,
        source,
    ]

    try:
        subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"YouTube download failed: {e.stderr.decode()}"
        )

    if not os.path.exists(output_path):
        raise RuntimeError("YouTube download did not produce a file")

    return output_path
