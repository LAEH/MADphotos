"""backend.bento — Finite-ratio bento layout system.

Square units with exactly 7 allowed aspect ratios:
1/2, 2/3, 3/4, 1, 4/3, 3/2, 2/1.
"""
from __future__ import annotations

# Square units — each grid cell is 1:1 on screen (approximately).
UNIT_RATIO = 1

# The 7 allowed cell aspect ratios (width / height).
ALLOWED_RATIOS = frozenset([1/2, 2/3, 3/4, 1, 4/3, 3/2, 2/1])

# Map (rs, cs) → aspect ratio.  Only these spans are valid.
ALLOWED_SPANS: dict[tuple[int, int], float] = {
    (2, 1): 1/2,
    (3, 2): 2/3,
    (4, 3): 3/4,
    (1, 1): 1,
    (2, 2): 1,
    (3, 3): 1,
    (3, 4): 4/3,
    (2, 3): 3/2,
    (1, 2): 2,
}

# Map ratio → Gemma crop key for smart cropping.
CROP_KEY_MAP: dict[float, str] = {
    1/2: '2:3',
    2/3: '2:3',
    3/4: '2:3',
    1: '1:1',
    4/3: '3:2',
    3/2: '3:2',
    2/1: '16:9',
}
