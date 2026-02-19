"""backend.enhance — Universal image enhancement proposal and review system."""
from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = PROJECT_ROOT / "images" / "mad_photos.db"
RENDERED_DIR = PROJECT_ROOT / "images" / "rendered"
DISPLAY_JPEG_DIR = RENDERED_DIR / "display" / "jpeg"
ENHANCED_EXPOSURE_DIR = RENDERED_DIR / "enhanced_exposure" / "jpeg"
ENHANCED_DIR = RENDERED_DIR / "enhanced"
PREVIEW_DIR = RENDERED_DIR / "enhance_previews"

TYPES = ("border_crop", "exposure", "gemma_crop", "rotation")
BATCH_SIZE = 30
