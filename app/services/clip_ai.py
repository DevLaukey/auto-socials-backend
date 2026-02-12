"""
AI Segment Selection Service

Responsibilities:
- Analyze Whisper transcript segments
- Select engaging, short-form clip segments
- Return deterministic, machine-readable timestamps
"""

import json
from typing import List, Dict

from app.config import settings


# =========================================================
# Provider detection (lazy, safe)
# =========================================================

def _get_provider():
    if getattr(settings, "OPENAI_API_KEY", None):
        from openai import OpenAI
        return "openai", OpenAI(api_key=settings.OPENAI_API_KEY)

    if getattr(settings, "GROQ_API_KEY", None):
        from groq import Groq
        return "groq", Groq(api_key=settings.GROQ_API_KEY)

    raise RuntimeError(
        "No AI provider configured. Set OPENAI_API_KEY or GROQ_API_KEY."
    )


# =========================================================
# Prompt builder
# =========================================================

def build_system_prompt(clip_length: int, style: str) -> str:
    style_rules = {
        "highlight": "Focus on emotionally engaging, insightful, or impactful moments.",
        "fast_cuts": "Prefer fast-paced, punchy moments with quick delivery.",
        "podcast": "Prefer longer, coherent explanations or storytelling segments.",
    }

    return f"""
You are an expert short-form video editor.

Your job:
- Identify the most engaging moments in a long-form video transcript
- Select segments suitable for TikTok, YouTube Shorts, Instagram Reels

RULES:
- Target clip length: ~{clip_length} seconds
- Clips must be continuous
- Avoid intros, outros, ads, sponsorships
- Prefer natural sentence boundaries

STYLE:
{style_rules.get(style, style_rules["highlight"])}

OUTPUT RULES:
- Return ONLY valid JSON
- No commentary, no markdown

JSON FORMAT:
[
  {{
    "start": number,
    "end": number,
    "reason": string
  }}
]
"""


# =========================================================
# Public API
# =========================================================

def select_segments(
    transcript: List[Dict],
    max_clips: int,
    clip_length: int,
    style: str = "highlight",
) -> List[Dict]:
    """
    Returns:
    [
        {
            "start": float,
            "end": float,
            "reason": str
        }
    ]
    """

    # Graceful handling for music / silent videos
    if not transcript:
        return []

    provider, client = _get_provider()

    # Transcript duration safety
    video_start = transcript[0]["start"]
    video_end = transcript[-1]["end"]

    # Reduce token size
    compact_transcript = [
        {
            "start": round(s["start"], 2),
            "end": round(s["end"], 2),
            "text": s["text"],
        }
        for s in transcript
    ]

    user_prompt = f"""
Here is a transcript with timestamps:

{json.dumps(compact_transcript, indent=2)}

Select up to {max_clips} engaging segments.

IMPORTANT:
- Each segment should be around {clip_length} seconds
- Do NOT exceed transcript bounds
"""

    system_prompt = build_system_prompt(
        clip_length=clip_length,
        style=style,
    )

    # -------------------------------------------------
    # Call provider
    # -------------------------------------------------

    if provider == "openai":
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.3,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw_output = response.choices[0].message.content.strip()

    else:  # groq
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            temperature=0.3,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw_output = response.choices[0].message.content.strip()

    # -------------------------------------------------
    # Parse & validate (AUTHORITATIVE)
    # -------------------------------------------------

    try:
        segments = json.loads(raw_output)
    except json.JSONDecodeError:
        raise RuntimeError("AI returned invalid JSON")

    validated: List[Dict] = []
    used_ranges = []

    for seg in segments:
        if len(validated) >= max_clips:
            break

        start = float(seg.get("start", 0))
        end = start + clip_length

        # Clamp to video bounds
        if start < video_start:
            start = video_start
            end = start + clip_length

        if end > video_end:
            end = video_end
            start = end - clip_length

        if end <= start:
            continue

        # Prevent overlapping clips
        if any(abs(start - s) < clip_length for s in used_ranges):
            continue

        used_ranges.append(start)

        validated.append(
            {
                "start": round(start, 3),
                "end": round(end, 3),
                "reason": seg.get("reason", ""),
            }
        )

    return validated
