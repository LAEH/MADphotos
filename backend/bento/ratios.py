"""Ratio math helpers for the bento layout system."""
from __future__ import annotations

from . import UNIT_RATIO, ALLOWED_SPANS, CROP_KEY_MAP


def cell_ratio(rs: int, cs: int) -> float:
    """Compute the aspect ratio (w/h) of a cell from its row/col spans."""
    if rs <= 0:
        raise ValueError(f"rs must be positive, got {rs}")
    return (cs * UNIT_RATIO) / rs


def ratio_to_crop_key(ratio: float) -> str:
    """Map a cell aspect ratio to the closest Gemma crop key.

    Uses exact matching against the 7 allowed ratios with a small epsilon,
    then falls back to threshold-based matching for dynamic grids.
    """
    # Exact match (within float tolerance)
    for allowed_ratio, key in CROP_KEY_MAP.items():
        if abs(ratio - allowed_ratio) < 1e-6:
            return key
    # Fallback for dynamic grids that may produce non-standard ratios
    if ratio >= 1.6:
        return '16:9'
    if ratio >= 1.1:
        return '3:2'
    if ratio <= 0.85:
        return '2:3'
    return '1:1'


def is_valid_cell(rs: int, cs: int) -> bool:
    """Check if a (rs, cs) span produces an allowed ratio."""
    return (rs, cs) in ALLOWED_SPANS


def orient_for_cell(rs: int, cs: int) -> str:
    """Return 'P' (portrait) if ratio < 1, else 'L' (landscape/square)."""
    return 'P' if cell_ratio(rs, cs) < 1 else 'L'
