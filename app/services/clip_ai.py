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

    # Calculate acceptable range
    min_length = max(15, clip_length - 5)
    max_length = clip_length + 5

    return f"""
You are an expert short-form video editor.

Your job:
- Identify the most engaging moments in a long-form video transcript
- Select segments suitable for TikTok, YouTube Shorts, Instagram Reels

RULES:
- Target clip length: ~{clip_length} seconds (acceptable range: {min_length}-{max_length} seconds)
- Clips must be continuous and flow naturally
- Start and end at natural sentence boundaries when possible
- Avoid intros, outros, ads, sponsorships
- Prefer moments with high engagement potential

STYLE GUIDANCE:
{style_rules.get(style, style_rules["highlight"])}

IMPORTANT:
- Return EXACT start and end times based on the transcript
- Do NOT force clips to be exactly {clip_length} seconds if it would cut mid-sentence
- It's better to have a slightly shorter or longer clip that makes sense
- Use the actual transcript timestamps to determine natural boundaries

OUTPUT RULES:
- Return ONLY valid JSON
- No commentary, no markdown

JSON FORMAT:
[
  {{
    "start": number,     # Start time in seconds (from transcript)
    "end": number,       # End time in seconds (from transcript)
    "reason": string     # Brief explanation of why this segment was chosen
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

    # Reduce token size but keep enough context for AI
    compact_transcript = [
        {
            "start": round(s["start"], 2),
            "end": round(s["end"], 2),
            "text": s["text"][:200],  # Limit text length to reduce tokens
        }
        for s in transcript
    ]

    # Calculate acceptable range for the AI
    min_acceptable = max(15, clip_length - 5)
    max_acceptable = clip_length + 5

    user_prompt = f"""
Here is a transcript with timestamps:

{json.dumps(compact_transcript, indent=2)}

Select up to {max_clips} engaging segments from this transcript.

IMPORTANT REQUIREMENTS:
1. Each segment should ideally be around {clip_length} seconds long
2. Acceptable range: {min_acceptable} to {max_acceptable} seconds
3. Use the ACTUAL transcript timestamps to determine start and end
4. Start and end at natural breaks in speech when possible
5. Segments should be spaced apart (avoid overlapping)
6. Return segments in chronological order

For each segment, provide:
- "start": The exact start time from the transcript
- "end": The exact end time from the transcript (this should be a real timestamp from the transcript, not calculated)
- "reason": A brief explanation of why this segment is engaging
"""

    system_prompt = build_system_prompt(
        clip_length=clip_length,
        style=style,
    )

    # -------------------------------------------------
    # Call provider
    # -------------------------------------------------

    try:
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

        # Clean the output - remove markdown code blocks if present
        if raw_output.startswith("```json"):
            raw_output = raw_output.replace("```json", "").replace("```", "")
        elif raw_output.startswith("```"):
            raw_output = raw_output.replace("```", "")

        raw_output = raw_output.strip()
    except Exception as e:
        raise RuntimeError(f"AI provider call failed: {str(e)}")

    # -------------------------------------------------
    # Parse & validate
    # -------------------------------------------------

    try:
        segments = json.loads(raw_output)
        if not isinstance(segments, list):
            raise RuntimeError("AI did not return a list")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"AI returned invalid JSON: {raw_output[:200]}...")

    validated: List[Dict] = []
    used_ranges = []  # Store (start, end) tuples to check overlap

    for seg in segments:
        if len(validated) >= max_clips:
            break

        # Validate required fields
        if "start" not in seg or "end" not in seg:
            continue

        try:
            start = float(seg["start"])
            end = float(seg["end"])
            reason = str(seg.get("reason", ""))[:200]  # Truncate long reasons
        except (ValueError, TypeError):
            continue

        # Basic validation
        if end <= start:
            continue

        # Check if within video bounds
        if start < video_start or end > video_end:
            continue

        # Check duration against acceptable range
        duration = end - start
        min_acceptable = max(15, clip_length - 5)
        max_acceptable = clip_length + 5
        
        if duration < min_acceptable or duration > max_acceptable:
            continue

        # Check for overlap with existing segments (allow small gap)
        overlap_threshold = 2.0  # seconds
        overlap_detected = False
        
        for used_start, used_end in used_ranges:
            if not (end < used_start - overlap_threshold or start > used_end + overlap_threshold):
                overlap_detected = True
                break
        
        if overlap_detected:
            continue

        used_ranges.append((start, end))
        
        validated.append({
            "start": round(start, 3),
            "end": round(end, 3),
            "reason": reason,
        })

    if not validated:
        # Fallback: If AI didn't return valid segments, create some based on transcript
        print("AI returned no valid segments, using fallback segmentation")
        return fallback_segments(transcript, max_clips, clip_length)

    return validated


# =========================================================
# Fallback segmentation (if AI fails)
# =========================================================

def fallback_segments(
    transcript: List[Dict],
    max_clips: int,
    target_duration: int
) -> List[Dict]:
    """
    Simple fallback that creates evenly spaced segments from the transcript.
    This ensures we always return something even if AI fails.
    """
    if not transcript:
        return []
    
    video_start = transcript[0]["start"]
    video_end = transcript[-1]["end"]
    video_duration = video_end - video_start
    
    if video_duration < target_duration:
        # Video is shorter than target, return whole video
        return [{
            "start": round(video_start, 3),
            "end": round(video_end, 3),
            "reason": "Full video (shorter than requested clip length)"
        }]
    
    segments = []
    clip_spacing = video_duration / (max_clips + 1)
    
    for i in range(max_clips):
        center = video_start + (i + 1) * clip_spacing
        start = max(video_start, center - target_duration / 2)
        end = min(video_end, center + target_duration / 2)
        
        # Adjust if we hit the boundaries
        if end - start < target_duration:
            if start == video_start:
                end = min(video_end, start + target_duration)
            elif end == video_end:
                start = max(video_start, end - target_duration)
        
        if end - start >= 15:  # Minimum acceptable duration
            segments.append({
                "start": round(start, 3),
                "end": round(end, 3),
                "reason": f"Automatically selected segment {i+1} of {max_clips}"
            })
    
    return segments