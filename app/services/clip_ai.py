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

# -------------------------
# Provider detection
# -------------------------

USE_GROQ = bool(getattr(settings, "GROQ_API_KEY", None))
USE_OPENAI = bool(getattr(settings, "OPENAI_API_KEY", None))

if not USE_GROQ and not USE_OPENAI:
    raise RuntimeError(
        "No AI provider configured. Set GROQ_API_KEY or OPENAI_API_KEY."
    )

# -------------------------
# OpenAI client (optional)
# -------------------------

if USE_OPENAI:
    from openai import OpenAI
    openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)

# -------------------------
# Groq client (optional)
# -------------------------

if USE_GROQ:
    from groq import Groq
    groq_client = Groq(api_key=settings.GROQ_API_KEY)

# -------------------------
# Prompt
# -------------------------

SYSTEM_PROMPT = """
You are an expert short-form video editor.

Your job:
- Identify the most engaging moments in a long-form video transcript
- Select segments suitable for TikTok, YouTube Shorts, Instagram Reels

Rules:
- Each clip MUST be between 15 and 60 seconds
- Clips must be continuous (no jumps)
- Prefer moments with emotion, insight, humor, or strong explanations
- Avoid intros, outros, ads, sponsorships
- Return ONLY valid JSON
- Do NOT include commentary or explanation
"""

# -------------------------
# Public API
# -------------------------

def select_segments(
    transcript: List[Dict],
    max_clips: int = 5,
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

    if not transcript:
        raise ValueError("Transcript is empty")

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

Select up to {max_clips} short-form video segments.

Output JSON format:
[
  {{
    "start": number,
    "end": number,
    "reason": string
  }}
]
"""

    # -------------------------
    # Call AI provider
    # -------------------------

    if USE_GROQ:
        raw_output = _select_segments_groq(user_prompt)
    else:
        raw_output = _select_segments_openai(user_prompt)

    # -------------------------
    # Parse & validate
    # -------------------------

    try:
        segments = json.loads(raw_output)
    except json.JSONDecodeError:
        raise RuntimeError("AI returned invalid JSON")

    validated = []

    for seg in segments:
        start = float(seg["start"])
        end = float(seg["end"])

        if end <= start:
            continue

        duration = end - start
        # if duration < 15 or duration > 60:
        #     continue

        validated.append(
            {
                "start": start,
                "end": end,
                "reason": seg.get("reason", ""),
            }
        )

    if not validated:
        raise RuntimeError("AI did not produce valid clip segments")

    return validated

# -------------------------
# Provider implementations
# -------------------------

def _select_segments_openai(user_prompt: str) -> str:
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.3,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )

    return response.choices[0].message.content.strip()


def _select_segments_groq(user_prompt: str) -> str:
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        temperature=0.3,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )

    return response.choices[0].message.content.strip()

