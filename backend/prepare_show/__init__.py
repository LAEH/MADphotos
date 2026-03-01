"""backend.prepare_show — Pre-compute everything Show needs."""
from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = PROJECT_ROOT / "images" / "mad_photos.db"
SHOW_DIR = PROJECT_ROOT / "frontend" / "show"
PUBLIC_DATA_DIR = SHOW_DIR / "public" / "data"
PHOTOS_JSON = PUBLIC_DATA_DIR / "photos.json"
DRIFT_JSON = PUBLIC_DATA_DIR / "drift_neighbors.json"
FINGERPRINT_PATH = PROJECT_ROOT / ".prepare_show_fingerprint.json"

# Output files
SCORES_JSON = PUBLIC_DATA_DIR / "show_scores.json"
INDEX_JSON = PUBLIC_DATA_DIR / "show_index.json"
BENTOS_JSON = PUBLIC_DATA_DIR / "show_bentos.json"
BOOM_JSON = PUBLIC_DATA_DIR / "show_boom.json"
PAIRS_JSON = PUBLIC_DATA_DIR / "show_pairs.json"

ALL_OUTPUTS = [SCORES_JSON, INDEX_JSON, BENTOS_JSON, BOOM_JSON, PAIRS_JSON]

# Bento unit ratio (square) — matches cropUtils.ts BENTO_UNIT_RATIO
from backend.bento import UNIT_RATIO as BENTO_UNIT_RATIO
