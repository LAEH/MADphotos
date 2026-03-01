"""All bento layout definitions — SINGLE SOURCE OF TRUTH.

Desktop: 5×3 grid (15 units).  Unit cells ≈ square on 16:9 screens.
Mobile:  3×6 grid (18 units).  Unit cells ≈ square on 9:16 screens.

Every cell must use spans from ALLOWED_SPANS — no other shapes permitted.
"""
from __future__ import annotations

import json
from typing import Any

from . import ALLOWED_SPANS
from .ratios import orient_for_cell


# ── Cell constructors ──

def _cell(r: int, c: int, rs: int, cs: int) -> dict:
    """Create a cell dict with auto-computed orient."""
    return {"r": r, "c": c, "rs": rs, "cs": cs, "orient": orient_for_cell(rs, cs)}


def P(r: int, c: int, rs: int, cs: int) -> dict:
    """Portrait cell (ratio < 1)."""
    return _cell(r, c, rs, cs)


def L(r: int, c: int, rs: int, cs: int) -> dict:
    """Landscape/square cell (ratio >= 1)."""
    return _cell(r, c, rs, cs)


# ═══════════════════════════════════════════════════════════════════════════════
# Desktop layouts — 5×3 grid (15 units)
# ═══════════════════════════════════════════════════════════════════════════════

DESKTOP_LAYOUTS: list[dict[str, Any]] = [
    # D1 (8 tiles) — Hero: big 3:2 top-left, portrait, strip bottom
    {
        "id": "D1", "cols": 5, "rows": 3, "count": 8, "device": "desktop",
        "cells": [
            L(1, 1, 2, 3),  # 3/2
            P(1, 4, 2, 1),  # 1/2
            L(1, 5, 1, 1),  # 1
            L(2, 5, 1, 1),  # 1
            L(3, 1, 1, 1),  # 1
            L(3, 2, 1, 2),  # 2
            L(3, 4, 1, 1),  # 1
            L(3, 5, 1, 1),  # 1
        ],
    },
    # D2 (6 tiles) — Balanced: two squares + portrait top, wide+square+wide bottom
    {
        "id": "D2", "cols": 5, "rows": 3, "count": 6, "device": "desktop",
        "cells": [
            L(1, 1, 2, 2),  # 1
            P(1, 3, 2, 1),  # 1/2
            L(1, 4, 2, 2),  # 1
            L(3, 1, 1, 2),  # 2
            L(3, 3, 1, 1),  # 1
            L(3, 4, 1, 2),  # 2
        ],
    },
    # D3 (9 tiles) — Gallery: portrait anchor left, mixed right
    {
        "id": "D3", "cols": 5, "rows": 3, "count": 9, "device": "desktop",
        "cells": [
            P(1, 1, 2, 1),  # 1/2
            L(1, 2, 2, 2),  # 1
            L(1, 4, 1, 2),  # 2
            P(2, 4, 2, 1),  # 1/2
            L(2, 5, 1, 1),  # 1
            L(3, 1, 1, 1),  # 1
            L(3, 2, 1, 1),  # 1
            L(3, 3, 1, 1),  # 1
            L(3, 5, 1, 1),  # 1
        ],
    },
    # D4 (5 tiles) — Bold: two big blocks top, wide strip bottom
    {
        "id": "D4", "cols": 5, "rows": 3, "count": 5, "device": "desktop",
        "cells": [
            L(1, 1, 2, 3),  # 3/2
            L(1, 4, 2, 2),  # 1
            L(3, 1, 1, 2),  # 2
            L(3, 3, 1, 2),  # 2
            L(3, 5, 1, 1),  # 1
        ],
    },
    # D5 (10 tiles) — Portrait wall: alternating portraits + squares
    {
        "id": "D5", "cols": 5, "rows": 3, "count": 10, "device": "desktop",
        "cells": [
            P(1, 1, 2, 1),  # 1/2
            L(1, 2, 1, 1),  # 1
            P(1, 3, 2, 1),  # 1/2
            L(1, 4, 1, 1),  # 1
            P(1, 5, 2, 1),  # 1/2
            L(2, 2, 1, 1),  # 1
            L(2, 4, 1, 1),  # 1
            L(3, 1, 1, 2),  # 2
            L(3, 3, 1, 1),  # 1
            L(3, 4, 1, 2),  # 2
        ],
    },
    # D6 (6 tiles) — Showcase: square + wide 3:2 top, strip bottom
    {
        "id": "D6", "cols": 5, "rows": 3, "count": 6, "device": "desktop",
        "cells": [
            L(1, 1, 2, 2),  # 1
            L(1, 3, 2, 3),  # 3/2
            L(3, 1, 1, 1),  # 1
            L(3, 2, 1, 1),  # 1
            L(3, 3, 1, 2),  # 2
            L(3, 5, 1, 1),  # 1
        ],
    },
    # D7 (11 tiles) — Mosaic: many small tiles, visual complexity
    {
        "id": "D7", "cols": 5, "rows": 3, "count": 11, "device": "desktop",
        "cells": [
            L(1, 1, 1, 2),  # 2
            P(1, 3, 2, 1),  # 1/2
            L(1, 4, 1, 1),  # 1
            L(1, 5, 1, 1),  # 1
            L(2, 1, 1, 1),  # 1
            L(2, 2, 1, 1),  # 1
            L(2, 4, 1, 2),  # 2
            L(3, 1, 1, 1),  # 1
            L(3, 2, 1, 1),  # 1
            L(3, 3, 1, 1),  # 1
            L(3, 4, 1, 2),  # 2
        ],
    },
    # D8 (5 tiles) — Cinema: massive 3×3 square hero
    {
        "id": "D8", "cols": 5, "rows": 3, "count": 5, "device": "desktop",
        "cells": [
            L(1, 1, 3, 3),  # 1 (large)
            P(1, 4, 2, 1),  # 1/2
            L(1, 5, 1, 1),  # 1
            L(2, 5, 1, 1),  # 1
            L(3, 4, 1, 2),  # 2
        ],
    },
    # D9 (7 tiles) — Asymmetric: 3:2 hero + portrait + varied bottom
    {
        "id": "D9", "cols": 5, "rows": 3, "count": 7, "device": "desktop",
        "cells": [
            L(1, 1, 2, 3),  # 3/2
            P(1, 4, 2, 1),  # 1/2
            L(1, 5, 1, 1),  # 1
            L(2, 5, 1, 1),  # 1
            L(3, 1, 1, 2),  # 2
            L(3, 3, 1, 1),  # 1
            L(3, 4, 1, 2),  # 2
        ],
    },
    # D10 (3 tiles) — Widescreen: massive 4:3 hero + side column
    {
        "id": "D10", "cols": 5, "rows": 3, "count": 3, "device": "desktop",
        "cells": [
            L(1, 1, 3, 4),  # 4/3
            P(1, 5, 2, 1),  # 1/2
            L(3, 5, 1, 1),  # 1
        ],
    },
]

# ── Desktop small layouts (for low counts) ──

DESKTOP_SMALL_LAYOUTS: list[dict[str, Any]] = [
    {"id": "DS1", "cols": 1, "rows": 1, "count": 1, "device": "desktop",
     "cells": [L(1, 1, 1, 1)]},
    {"id": "DS2", "cols": 2, "rows": 1, "count": 2, "device": "desktop",
     "cells": [L(1, 1, 1, 1), L(1, 2, 1, 1)]},
    {"id": "DS3", "cols": 3, "rows": 1, "count": 3, "device": "desktop",
     "cells": [L(1, 1, 1, 1), L(1, 2, 1, 1), L(1, 3, 1, 1)]},
    {"id": "DS4", "cols": 2, "rows": 2, "count": 4, "device": "desktop",
     "cells": [L(1, 1, 1, 1), L(1, 2, 1, 1), L(2, 1, 1, 1), L(2, 2, 1, 1)]},
    {"id": "DS6", "cols": 3, "rows": 2, "count": 6, "device": "desktop",
     "cells": [L(1, 1, 1, 1), L(1, 2, 1, 1), L(1, 3, 1, 1),
               L(2, 1, 1, 1), L(2, 2, 1, 1), L(2, 3, 1, 1)]},
    {"id": "DS6p", "cols": 3, "rows": 2, "count": 4, "device": "desktop",
     "cells": [P(1, 1, 2, 1), L(1, 2, 1, 1), P(1, 3, 2, 1), L(2, 2, 1, 1)]},
]


# ═══════════════════════════════════════════════════════════════════════════════
# Mobile layouts — 3×6 grid (18 units)
# ═══════════════════════════════════════════════════════════════════════════════

MOBILE_LAYOUTS: list[dict[str, Any]] = [
    # M1 (6 tiles) — Blocks: alternating sq+portrait rows
    {
        "id": "M1", "cols": 3, "rows": 6, "count": 6, "device": "mobile",
        "cells": [
            L(1, 1, 2, 2),  # 1
            P(1, 3, 2, 1),  # 1/2
            P(3, 1, 2, 1),  # 1/2
            L(3, 2, 2, 2),  # 1
            L(5, 1, 2, 2),  # 1
            P(5, 3, 2, 1),  # 1/2
        ],
    },
    # M2 (6 tiles) — Zigzag: portrait+sq alternating
    {
        "id": "M2", "cols": 3, "rows": 6, "count": 6, "device": "mobile",
        "cells": [
            P(1, 1, 2, 1),  # 1/2
            L(1, 2, 2, 2),  # 1
            L(3, 1, 2, 2),  # 1
            P(3, 3, 2, 1),  # 1/2
            P(5, 1, 2, 1),  # 1/2
            L(5, 2, 2, 2),  # 1
        ],
    },
    # M3 (7 tiles) — Mixed: sq+p, 3 portraits, p+sq
    {
        "id": "M3", "cols": 3, "rows": 6, "count": 7, "device": "mobile",
        "cells": [
            L(1, 1, 2, 2),  # 1
            P(1, 3, 2, 1),  # 1/2
            P(3, 1, 2, 1),  # 1/2
            P(3, 2, 2, 1),  # 1/2
            P(3, 3, 2, 1),  # 1/2
            P(5, 1, 2, 1),  # 1/2
            L(5, 2, 2, 2),  # 1
        ],
    },
    # M4 (8 tiles) — Rhythm: sq+p, p+singles+p, sq+p
    {
        "id": "M4", "cols": 3, "rows": 6, "count": 8, "device": "mobile",
        "cells": [
            L(1, 1, 2, 2),  # 1
            P(1, 3, 2, 1),  # 1/2
            P(3, 1, 2, 1),  # 1/2
            L(3, 2, 1, 1),  # 1
            P(3, 3, 2, 1),  # 1/2
            L(4, 2, 1, 1),  # 1
            L(5, 1, 2, 2),  # 1
            P(5, 3, 2, 1),  # 1/2
        ],
    },
    # M5 (5 tiles) — Drama: full-width 3:2 top, blocks below
    {
        "id": "M5", "cols": 3, "rows": 6, "count": 5, "device": "mobile",
        "cells": [
            L(1, 1, 2, 3),  # 3/2
            P(3, 1, 2, 1),  # 1/2
            L(3, 2, 2, 2),  # 1
            L(5, 1, 2, 2),  # 1
            P(5, 3, 2, 1),  # 1/2
        ],
    },
    # M6 (7 tiles) — Feature: tall 2:3 portrait left, stack right, landscape bottom
    {
        "id": "M6", "cols": 3, "rows": 6, "count": 7, "device": "mobile",
        "cells": [
            P(1, 1, 3, 2),  # 2/3
            P(1, 3, 2, 1),  # 1/2
            L(3, 3, 1, 1),  # 1
            L(4, 1, 2, 2),  # 1
            P(4, 3, 2, 1),  # 1/2
            L(6, 1, 1, 2),  # 2
            L(6, 3, 1, 1),  # 1
        ],
    },
    # M7 (7 tiles) — Portrait trio + sq+p, sq+p
    {
        "id": "M7", "cols": 3, "rows": 6, "count": 7, "device": "mobile",
        "cells": [
            P(1, 1, 2, 1),  # 1/2
            P(1, 2, 2, 1),  # 1/2
            P(1, 3, 2, 1),  # 1/2
            L(3, 1, 2, 2),  # 1
            P(3, 3, 2, 1),  # 1/2
            P(5, 1, 2, 1),  # 1/2
            L(5, 2, 2, 2),  # 1
        ],
    },
]

# ── Mobile small layouts ──

MOBILE_SMALL_LAYOUTS: list[dict[str, Any]] = [
    {"id": "MS1", "cols": 1, "rows": 1, "count": 1, "device": "mobile",
     "cells": [L(1, 1, 1, 1)]},
    {"id": "MS2", "cols": 1, "rows": 2, "count": 2, "device": "mobile",
     "cells": [L(1, 1, 1, 1), L(2, 1, 1, 1)]},
    {"id": "MS3", "cols": 1, "rows": 3, "count": 3, "device": "mobile",
     "cells": [L(1, 1, 1, 1), L(2, 1, 1, 1), L(3, 1, 1, 1)]},
    {"id": "MS4", "cols": 2, "rows": 2, "count": 4, "device": "mobile",
     "cells": [L(1, 1, 1, 1), L(1, 2, 1, 1), L(2, 1, 1, 1), L(2, 2, 1, 1)]},
    {"id": "MS6", "cols": 2, "rows": 3, "count": 6, "device": "mobile",
     "cells": [L(1, 1, 1, 1), L(1, 2, 1, 1), L(2, 1, 1, 1),
               L(2, 2, 1, 1), L(3, 1, 1, 1), L(3, 2, 1, 1)]},
]


# ═══════════════════════════════════════════════════════════════════════════════
# Starter layouts — big splittable tiles for tap-to-split interaction
# ═══════════════════════════════════════════════════════════════════════════════

DESKTOP_STARTER_LAYOUTS: list[dict[str, Any]] = [
    # DST1 (5 tiles): sq + wide 3:2, strip bottom
    {
        "id": "DST1", "cols": 5, "rows": 3, "count": 5, "device": "desktop",
        "cells": [
            L(1, 1, 2, 2),  # 1
            L(1, 3, 2, 3),  # 3/2
            L(3, 1, 1, 2),  # 2
            L(3, 3, 1, 2),  # 2
            L(3, 5, 1, 1),  # 1
        ],
    },
    # DST2 (5 tiles): wide 3:2 + sq, strip bottom
    {
        "id": "DST2", "cols": 5, "rows": 3, "count": 5, "device": "desktop",
        "cells": [
            L(1, 1, 2, 3),  # 3/2
            L(1, 4, 2, 2),  # 1
            L(3, 1, 1, 2),  # 2
            L(3, 3, 1, 2),  # 2
            L(3, 5, 1, 1),  # 1
        ],
    },
    # DST3 (5 tiles): massive 3×3 square hero, side column
    {
        "id": "DST3", "cols": 5, "rows": 3, "count": 5, "device": "desktop",
        "cells": [
            L(1, 1, 3, 3),  # 1 (large)
            P(1, 4, 2, 1),  # 1/2
            L(1, 5, 1, 1),  # 1
            L(2, 5, 1, 1),  # 1
            L(3, 4, 1, 2),  # 2
        ],
    },
    # DST4 (6 tiles): sq + portrait + sq, strip bottom
    {
        "id": "DST4", "cols": 5, "rows": 3, "count": 6, "device": "desktop",
        "cells": [
            L(1, 1, 2, 2),  # 1
            P(1, 3, 2, 1),  # 1/2
            L(1, 4, 2, 2),  # 1
            L(3, 1, 1, 2),  # 2
            L(3, 3, 1, 2),  # 2
            L(3, 5, 1, 1),  # 1
        ],
    },
    # DST5 (3 tiles): 4:3 hero + side portrait + square
    {
        "id": "DST5", "cols": 5, "rows": 3, "count": 3, "device": "desktop",
        "cells": [
            L(1, 1, 3, 4),  # 4/3
            P(1, 5, 2, 1),  # 1/2
            L(3, 5, 1, 1),  # 1
        ],
    },
    # DST6 placeholder — replaced below with complete layout
    {
        "id": "DST6", "cols": 5, "rows": 3, "count": 8, "device": "desktop",
        "cells": [
            P(1, 1, 2, 1), L(1, 2, 2, 2), P(1, 4, 2, 1),
            L(1, 5, 1, 1), L(2, 5, 1, 1),
            L(3, 1, 1, 2), L(3, 3, 1, 2), L(3, 5, 1, 1),
        ],
    },
]

# Fix DST6 — fill row 3
MOBILE_STARTER_LAYOUTS: list[dict[str, Any]] = [
    # MST1 (4 tiles): landscape top, blocks below
    {
        "id": "MST1", "cols": 3, "rows": 6, "count": 4, "device": "mobile",
        "cells": [
            L(1, 1, 2, 3),  # 3/2
            P(3, 1, 2, 1),  # 1/2
            L(3, 2, 2, 2),  # 1
            L(5, 1, 2, 3),  # 3/2
        ],
    },
    # MST2 (5 tiles): sq+p, p+sq, sq+p
    {
        "id": "MST2", "cols": 3, "rows": 6, "count": 5, "device": "mobile",
        "cells": [
            L(1, 1, 2, 2),  # 1
            P(1, 3, 2, 1),  # 1/2
            L(3, 1, 2, 3),  # 3/2
            L(5, 1, 2, 2),  # 1
            P(5, 3, 2, 1),  # 1/2
        ],
    },
    # MST3 (6 tiles): tall 2:3 portrait + side, landscape bottom
    {
        "id": "MST3", "cols": 3, "rows": 6, "count": 6, "device": "mobile",
        "cells": [
            P(1, 1, 3, 2),  # 2/3
            P(1, 3, 2, 1),  # 1/2
            L(3, 3, 1, 1),  # 1
            L(4, 1, 2, 3),  # 3/2
            L(6, 1, 1, 2),  # 2
            L(6, 3, 1, 1),  # 1
        ],
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# All layouts combined
# ═══════════════════════════════════════════════════════════════════════════════

ALL_DESKTOP = DESKTOP_LAYOUTS + DESKTOP_SMALL_LAYOUTS
ALL_MOBILE = MOBILE_LAYOUTS + MOBILE_SMALL_LAYOUTS
ALL_LAYOUTS = ALL_DESKTOP + ALL_MOBILE + DESKTOP_STARTER_LAYOUTS + MOBILE_STARTER_LAYOUTS


def to_json() -> str:
    """Export all layouts as JSON for frontend consumption."""
    return json.dumps({
        "desktop": [_layout_to_dict(l) for l in ALL_DESKTOP],
        "mobile": [_layout_to_dict(l) for l in ALL_MOBILE],
        "desktop_starters": [_layout_to_dict(l) for l in DESKTOP_STARTER_LAYOUTS],
        "mobile_starters": [_layout_to_dict(l) for l in MOBILE_STARTER_LAYOUTS],
    }, indent=2)


def _layout_to_dict(layout: dict) -> dict:
    """Ensure layout is a clean serializable dict."""
    return {
        "id": layout["id"],
        "cols": layout["cols"],
        "rows": layout["rows"],
        "count": layout["count"],
        "device": layout["device"],
        "cells": layout["cells"],
    }
