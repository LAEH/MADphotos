"""Photo-specific prompt builder using Gemma analysis data."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from .config import COLOR_DIRECTIVE, STYLES


def _parse_gemma_json(raw: Optional[str]) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def build_prompt(style_key: str, photo: Dict) -> str:
    """Build a photo-specific prompt that combines style technique with strict color palette.

    Uses the style's composition/technique but overrides all color guidance
    with the global COLOR_DIRECTIVE (black, white, vibrant saturated accents).
    """
    style = STYLES[style_key]
    base = style["prompt"]
    gemma = _parse_gemma_json(photo.get("gemma_json"))

    parts = [base]

    # Mood preservation (keep atmosphere, not colors)
    mood = photo.get("gemma_mood") or gemma.get("mood")
    if mood:
        parts.append(f"Preserve the {mood} atmosphere.")

    # Lighting guidance (structure, not warmth)
    lighting = gemma.get("lighting")
    if lighting and isinstance(lighting, str) and len(lighting) > 5:
        parts.append(f"Maintain the lighting structure: {lighting}.")

    # Subject/composition awareness
    description = photo.get("gemma_description")
    if description and len(description) > 10:
        first_sentence = description.split(".")[0].strip()
        if len(first_sentence) > 10:
            parts.append(f"Subject: {first_sentence}.")

    # Color override — always last to take priority
    parts.append(COLOR_DIRECTIVE)

    return " ".join(parts)


def build_full_prompt(style_key: str, photo: Dict) -> str:
    """Wrap the personalized prompt in the Imagen 3 framing."""
    inner = build_prompt(style_key, photo)
    return (
        f"Transform this photograph into the following artistic style, "
        f"preserving the exact composition, subjects, and layout. "
        f"No text or lettering. Style: {inner}"
    )
