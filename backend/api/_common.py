"""Shared constants and utilities for backend.api modules."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = PROJECT_ROOT / "images" / "mad_photos.db"
VECTOR_PATH = PROJECT_ROOT / "images" / "vectors.lance"
OUT_PATH = PROJECT_ROOT / "frontend" / "system" / "system.html"
MOSAIC_DIR = PROJECT_ROOT / "images" / "rendered" / "mosaics"
RENDERED_DIR = PROJECT_ROOT / "images" / "rendered"
JOURNAL_PATH = PROJECT_ROOT / "docs" / "journal.md"
GENERATED_DIR = PROJECT_ROOT / "backend" / "suggest_image_variant" / "output"


def human_bytes(n):
    # type: (int) -> str
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def pct(part, whole):
    # type: (int, int) -> float
    return round(part / whole * 100, 2) if whole else 0.0
