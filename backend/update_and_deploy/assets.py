"""Phase 7 (skippable): GCS asset verification — spot-check picks have all tiers."""
from __future__ import annotations

import json
import random
import subprocess
from . import SHOW_DATA_DIR

GCS_BUCKET = "gs://myproject-public-assets/art/MADphotos/v"
TIERS = ["thumb", "display"]
SAMPLE_SIZE = 10


def load_pick_uuids() -> list[str]:
    """Load pick UUIDs from picks.json."""
    picks_path = SHOW_DATA_DIR / "picks.json"
    if not picks_path.exists():
        return []
    try:
        data = json.loads(picks_path.read_text())
        uuids = list(set(data.get("portrait", []) + data.get("landscape", [])))
        return [u for u in uuids if "_" not in u]  # skip variant IDs
    except Exception:
        return []


def check_gcs_object(path: str) -> bool:
    """Check if a GCS object exists."""
    try:
        result = subprocess.run(
            ["gsutil", "stat", path],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def run(dry: bool = False) -> dict:
    """Spot-check a sample of picks for GCS tier completeness."""
    uuids = load_pick_uuids()
    if not uuids:
        print("  No picks found — skipping asset check")
        return {"checked": 0, "missing": []}

    sample = random.sample(uuids, min(SAMPLE_SIZE, len(uuids)))

    if dry:
        print(f"  Would check {len(sample)} picks across {len(TIERS)} tiers in GCS")
        return {"checked": 0, "missing": [], "dry": True}

    print(f"  Checking {len(sample)} picks across {len(TIERS)} tiers...")
    missing = []
    checked = 0

    for uuid in sample:
        for tier in TIERS:
            path = f"{GCS_BUCKET}/{tier}/jpeg/{uuid}.jpg"
            checked += 1
            if not check_gcs_object(path):
                missing.append({"uuid": uuid, "tier": tier})
                print(f"    MISSING  {tier}/{uuid}.jpg")

    if not missing:
        print(f"    All {checked} checks passed")
    else:
        print(f"    {len(missing)} missing out of {checked} checks")

    return {"checked": checked, "missing": missing}
