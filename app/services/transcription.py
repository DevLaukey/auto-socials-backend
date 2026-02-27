"""
Whisper Transcription Service (API-based)

Responsibilities:
- Transcribe video/audio files using either OpenAI Whisper API or Groq
- Return timestamped segments usable for AI clipping
- Gracefully handle videos with NO speech
"""

import os
from typing import List, Dict
from app.config import settings


# ---------------------------------------------------------
# Provider detection (same as clip_ai.py)
# ---------------------------------------------------------

def _get_provider():
    """Detect which AI provider is configured and return appropriate client"""
    if getattr(settings, "OPENAI_API_KEY", None):
        from openai import OpenAI
        return "openai", OpenAI(api_key=settings.OPENAI_API_KEY)

    if getattr(settings, "GROQ_API_KEY", None):
        from groq import Groq
        return "groq", Groq(api_key=settings.GROQ_API_KEY)

    raise RuntimeError(
        "No AI provider configured. Set OPENAI_API_KEY or GROQ_API_KEY."
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

    provider, client = _get_provider()

    if provider == "openai":
        return _transcribe_with_openai(client, video_path)
    else:  # groq
        return _transcribe_with_groq(client, video_path)


def _transcribe_with_openai(client, video_path: str) -> List[Dict]:
    """Transcribe using OpenAI's Whisper API"""
    with open(video_path, "rb") as audio_file:
        result = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )

    raw_segments = result.segments or []
    return _process_segments(raw_segments)


def _transcribe_with_groq(client, video_path: str) -> List[Dict]:
    """Transcribe using Groq's Whisper API"""
    with open(video_path, "rb") as file:
        # Groq expects the file to be passed with a filename
        result = client.audio.transcriptions.create(
            file=(os.path.basename(video_path), file.read()),
            model="whisper-large-v3-turbo",  # Groq's Whisper model
            response_format="verbose_json",
            temperature=0.0
        )

    # Handle Groq's response format (might be different from OpenAI)
    raw_segments = []
    
    # Check if result has segments attribute
    if hasattr(result, 'segments') and result.segments:
        raw_segments = result.segments
    # Sometimes Groq returns words instead of segments
    elif hasattr(result, 'words') and result.words:
        # Group words into segments (simplified approach)
        current_segment = {"start": 0, "end": 0, "text": ""}
        words = result.words
        
        for word in words:
            if not current_segment["text"]:
                current_segment["start"] = word.start
            
            current_segment["end"] = word.end
            current_segment["text"] += word.word + " "
            
            # End segment at sentence boundaries or after reasonable length
            if word.word.endswith(('.', '!', '?')) or len(current_segment["text"].split()) > 15:
                if current_segment["text"].strip():
                    raw_segments.append(current_segment.copy())
                current_segment = {"start": 0, "end": 0, "text": ""}
        
        # Add the last segment if not empty
        if current_segment["text"].strip():
            raw_segments.append(current_segment)
    
    # If result itself is a list-like object
    elif isinstance(result, list):
        raw_segments = result
    # Try to convert result to dict and extract segments
    elif hasattr(result, 'dict'):
        result_dict = result.dict()
        raw_segments = result_dict.get('segments', [])
    
    return _process_segments(raw_segments)


def _process_segments(raw_segments: List[Dict]) -> List[Dict]:
    """Process and validate segments from any provider"""
    segments: List[Dict] = []

    # Minimum usable speech duration (seconds)
    MIN_SEGMENT_DURATION = 0.3

    for seg in raw_segments:
        # Handle different segment formats (dict vs object)
        if isinstance(seg, dict):
            start = float(seg.get("start", 0))
            end = float(seg.get("end", 0))
            text = seg.get("text", "").strip()
        else:
            # Handle object-style segments (like OpenAI returns)
            start = float(getattr(seg, "start", 0))
            end = float(getattr(seg, "end", 0))
            text = getattr(seg, "text", "").strip()

        if not text:
            continue

        if end <= start:
            continue

        if end - start < MIN_SEGMENT_DURATION:
            continue

        segments.append({
            "start": round(start, 3),
            "end": round(end, 3),
            "text": text,
        })

    if not segments:
        return []

    return segments