#!/usr/bin/env python3
"""
mad_completions.py — The master orchestrator.

Checks every pipeline stage (rendering, signals, models, vectors, variants,
uploads). If anything is missing, starts the process. Regenerates the State
dashboard after each check so it always reflects reality.

Usage:
    python3 mad_completions.py              # Check + fix + update State
    python3 mad_completions.py --status     # Just show status
    python3 mad_completions.py --watch      # Loop every 60s until 100%
    python3 mad_completions.py --watch 30   # Loop every 30s
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

BACKEND = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND.parent
DB_PATH = PROJECT_ROOT / "images" / "mad_photos.db"
LANCE_DIR = PROJECT_ROOT / "images" / "vectors.lance"

# ---------------------------------------------------------------------------
# Stage definitions — every pipeline step
# ---------------------------------------------------------------------------

class Stage:
    def __init__(
        self,
        name: str,
        check_fn: str,          # method name on Checker
        fix_cmd: Optional[List[str]],
        group: str = "signal",  # signal | model | infra
        heavy: bool = False,
        is_api: bool = False,
    ):
        self.name = name
        self.check_fn = check_fn
        self.fix_cmd = fix_cmd
        self.group = group
        self.heavy = heavy
        self.is_api = is_api


PY = sys.executable
ADV = str(BACKEND / "signals_advanced.py")

STAGES = [
    # --- Infrastructure ---
    Stage("Rendered Tiers",     "check_tiers",         [PY, str(BACKEND / "render.py")],   group="infra"),
    Stage("Pixel Analysis",     "check_table_all",     [PY, str(BACKEND / "render.py")],   group="infra"),
    Stage("EXIF Metadata",      "check_table_all",     [PY, str(BACKEND / "render.py")],   group="infra"),
    Stage("Dominant Colors",    "check_table_all",     None,                                group="infra"),
    Stage("Image Hashes",       "check_table_all",     None,                                group="infra"),

    # --- Local CV models ---
    Stage("Aesthetic Scoring",  "check_table_all",     [PY, ADV, "--phase", "aesthetic"],  group="model", heavy=True),
    Stage("Depth Estimation",   "check_table_all",     [PY, ADV, "--phase", "depth"],      group="model", heavy=True),
    Stage("Scene Classification","check_table_all",    [PY, ADV, "--phase", "scene"],      group="model", heavy=True),
    Stage("Style Classification","check_table_all",    [PY, ADV, "--phase", "style"],      group="model"),
    Stage("OCR / Text Detection","check_ocr",          [PY, ADV, "--phase", "ocr"],        group="model", heavy=True),
    Stage("Image Captions",     "check_table_all",     [PY, ADV, "--phase", "captions"],   group="model", heavy=True),
    Stage("Face Detections",    "check_table_all",     None,                                group="model"),
    Stage("Object Detections",  "check_objects",       None,                                group="model"),
    Stage("Facial Emotions",    "check_table_faces",   [PY, ADV, "--phase", "emotions"],   group="model", heavy=True),

    # --- Vector embeddings ---
    Stage("Vector Embeddings",  "check_vectors",       None,                                group="model"),

    # --- API models ---
    Stage("Gemini Analysis",    "check_gemini",        [PY, str(BACKEND / "gemini.py"), "--concurrent", "5"], group="model", is_api=True),

    # --- Enhancement ---
    Stage("Enhancement Plans",  "check_table_all",     [PY, str(BACKEND / "enhance.py")],  group="signal"),
    Stage("Enhancement v2",     "check_table_all",     None,                                group="signal"),

    # --- AI Variants ---
    Stage("AI Variants",        "check_variants",      [PY, str(BACKEND / "imagen.py")],   group="infra", is_api=True),

    # --- GCS ---
    Stage("GCS Uploads",        "check_gcs",           [PY, str(BACKEND / "upload.py")],   group="infra"),
]

# Map stage names to DB tables for the generic check_table_all
TABLE_MAP = {
    "Pixel Analysis":       ("image_analysis",      "image_uuid"),
    "EXIF Metadata":        ("exif_metadata",       "image_uuid"),
    "Dominant Colors":      ("dominant_colors",      "image_uuid"),
    "Image Hashes":         ("image_hashes",         "image_uuid"),
    "Aesthetic Scoring":    ("aesthetic_scores",      "image_uuid"),
    "Depth Estimation":     ("depth_estimation",     "image_uuid"),
    "Scene Classification": ("scene_classification", "image_uuid"),
    "Style Classification": ("style_classification", "image_uuid"),
    "Image Captions":       ("image_captions",       "image_uuid"),
    "Face Detections":      ("face_detections",      "image_uuid"),
    "Enhancement Plans":    ("enhancement_plans",    "image_uuid"),
    "Enhancement v2":       ("enhancement_plans_v2", "image_uuid"),
}


# ---------------------------------------------------------------------------
# Checker — evaluates each stage
# ---------------------------------------------------------------------------

class Checker:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._total = None
        self._face_count = None

    @property
    def total(self) -> int:
        if self._total is None:
            self._total = self.conn.execute("SELECT COUNT(*) FROM images").fetchone()[0]
        return self._total

    @property
    def face_count(self) -> int:
        if self._face_count is None:
            self._face_count = self.conn.execute(
                "SELECT COUNT(DISTINCT image_uuid) FROM face_detections"
            ).fetchone()[0]
        return self._face_count

    def _result(self, done: int, total: int, note: str = "") -> Dict[str, Any]:
        missing = max(0, total - done)
        pct = (done * 100 / total) if total > 0 else 100
        return {"done": done, "total": total, "missing": missing, "pct": pct,
                "complete": missing == 0, "note": note}

    # --- Generic checks ---

    def check_table_all(self, stage: Stage) -> Dict[str, Any]:
        """Check a table where every image should have at least one row."""
        tbl, col = TABLE_MAP[stage.name]
        try:
            done = self.conn.execute(f"SELECT COUNT(DISTINCT {col}) FROM {tbl}").fetchone()[0]
        except sqlite3.OperationalError:
            done = 0
        return self._result(done, self.total)

    def check_table_faces(self, stage: Stage) -> Dict[str, Any]:
        """Check a table where only face-having images need rows."""
        done = 0
        try:
            done = self.conn.execute(
                "SELECT COUNT(DISTINCT image_uuid) FROM facial_emotions"
            ).fetchone()[0]
        except sqlite3.OperationalError:
            pass
        return self._result(done, self.face_count, f"{self.face_count} images have faces")

    # --- Specialized checks ---

    def check_tiers(self, stage: Stage) -> Dict[str, Any]:
        """Rendered tiers: each image should have ~10-11 tier files."""
        images_with_tiers = self.conn.execute(
            "SELECT COUNT(DISTINCT image_uuid) FROM tiers"
        ).fetchone()[0]
        total_tier_rows = self.conn.execute("SELECT COUNT(*) FROM tiers").fetchone()[0]
        avg = total_tier_rows / images_with_tiers if images_with_tiers else 0
        return self._result(images_with_tiers, self.total,
                            f"{total_tier_rows:,} tier files, ~{avg:.0f}/image")

    def check_ocr(self, stage: Stage) -> Dict[str, Any]:
        """OCR only stores rows for images that HAVE text. Can't compare to total.
        We check if the process has been run to completion by looking at the
        advanced_signals script's internal tracking."""
        detected = self.conn.execute(
            "SELECT COUNT(DISTINCT image_uuid) FROM ocr_detections"
        ).fetchone()[0]
        # OCR doesn't store "no text found" — so we can't know completion
        # from the DB alone. If less than ~50% of images have text, likely still running.
        # Heuristic: re-run the phase and let it skip already-processed images.
        # For status display, show what we have.
        return self._result(detected, self.total,
                            f"{detected} images with text (sparse — not all images have text)")

    def check_objects(self, stage: Stage) -> Dict[str, Any]:
        """Object detections — not every image will have objects."""
        detected = self.conn.execute(
            "SELECT COUNT(DISTINCT image_uuid) FROM object_detections"
        ).fetchone()[0]
        return self._result(detected, self.total,
                            f"{detected} images with objects (sparse)")

    def check_gemini(self, stage: Stage) -> Dict[str, Any]:
        done = self.conn.execute(
            "SELECT COUNT(*) FROM gemini_analysis "
            "WHERE raw_json IS NOT NULL AND raw_json != '' AND error IS NULL"
        ).fetchone()[0]
        errored = self.conn.execute(
            "SELECT COUNT(*) FROM gemini_analysis WHERE error IS NOT NULL"
        ).fetchone()[0]
        note = f"{errored} errors" if errored else ""
        return self._result(done, self.total, note)

    def check_vectors(self, stage: Stage) -> Dict[str, Any]:
        """Check lancedb vector count."""
        try:
            import lancedb
            db = lancedb.connect(str(LANCE_DIR))
            tables = db.table_names() if hasattr(db, 'table_names') else list(db.list_tables())
            total_vectors = 0
            notes = []
            for name in tables:
                tbl = db.open_table(name)
                count = len(tbl)
                total_vectors += count
                notes.append(f"{name}={count}")
            # Each image should have 1 row in the vectors table
            done = total_vectors // max(len(tables), 1)  # avg per table
            return self._result(done, self.total, ", ".join(notes))
        except Exception as e:
            return self._result(0, self.total, f"Error: {e}")

    def check_variants(self, stage: Stage) -> Dict[str, Any]:
        """AI variants — 4 types per image ideally, but this is in progress."""
        count = self.conn.execute("SELECT COUNT(*) FROM ai_variants").fetchone()[0]
        # 4 variant types × total images
        target = self.total * 4
        return self._result(count, target, f"{count} variants of {target} target")

    def check_gcs(self, stage: Stage) -> Dict[str, Any]:
        """GCS uploads — check tiers with gcs_url populated."""
        uploaded = self.conn.execute(
            "SELECT COUNT(*) FROM tiers WHERE gcs_url IS NOT NULL AND gcs_url != ''"
        ).fetchone()[0]
        total_tiers = self.conn.execute("SELECT COUNT(*) FROM tiers").fetchone()[0]
        return self._result(uploaded, total_tiers,
                            f"{uploaded:,}/{total_tiers:,} tier files uploaded")


# ---------------------------------------------------------------------------
# Status display
# ---------------------------------------------------------------------------

def get_status(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    checker = Checker(conn)
    results = []
    for stage in STAGES:
        method = getattr(checker, stage.check_fn)
        status = method(stage)
        status["stage"] = stage
        results.append(status)
    return results


def print_status(statuses: List[Dict[str, Any]]) -> None:
    now = datetime.now().strftime("%H:%M:%S")
    print(f"\n{'='*72}")
    print(f"  MADphotos Completions — {now}")
    print(f"{'='*72}")

    current_group = None
    for s in statuses:
        stage = s["stage"]
        if stage.group != current_group:
            current_group = stage.group
            labels = {"infra": "Infrastructure", "model": "Models & Signals", "signal": "Enhancement"}
            print(f"\n  {labels.get(current_group, current_group).upper()}")
            print(f"  {'-'*66}")

        bar_w = 16
        filled = int(bar_w * s["pct"] / 100)
        bar = "█" * filled + "░" * (bar_w - filled)

        if s["complete"]:
            mark = "✓"
        elif s["pct"] >= 90:
            mark = "~"
        else:
            mark = " "

        pct_str = f"{s['pct']:.0f}%"
        line = f"  {mark} {stage.name:<24} [{bar}] {s['done']:>6}/{s['total']:<6} {pct_str:>4}"
        if s.get("note"):
            line += f"  ({s['note']})"
        print(line)

    done_count = sum(1 for s in statuses if s["complete"])
    print(f"\n  {done_count}/{len(statuses)} stages complete")
    print()


# ---------------------------------------------------------------------------
# Process management
# ---------------------------------------------------------------------------

def is_process_running(cmd_fragment: str) -> Optional[int]:
    """Check if a process matching cmd_fragment is running. Returns PID or None."""
    try:
        result = subprocess.run(["pgrep", "-f", cmd_fragment],
                                capture_output=True, text=True)
        if result.returncode == 0:
            my_pid = str(os.getpid())
            parent_pid = str(os.getppid())
            for line in result.stdout.strip().split("\n"):
                pid = line.strip()
                if pid and pid != my_pid and pid != parent_pid:
                    return int(pid)
    except Exception:
        pass
    return None


def start_process(stage: Stage) -> Optional[int]:
    log_name = stage.name.lower().replace(" ", "_").replace("/", "_")
    log_path = f"/tmp/mad_{log_name}.log"

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    with open(log_path, "w") as f:
        proc = subprocess.Popen(stage.fix_cmd, stdout=f, stderr=subprocess.STDOUT,
                                env=env, cwd=str(BACKEND))

    print(f"    Started: {stage.name} (PID {proc.pid}) → {log_path}")
    return proc.pid


def fix_gaps(statuses: List[Dict[str, Any]]) -> int:
    started = 0
    heavy_running = False
    api_running = False

    for s in statuses:
        if s["complete"]:
            continue

        stage = s["stage"]
        if stage.fix_cmd is None:
            continue  # no auto-fix available

        # Build search fragment from command
        script_name = Path(stage.fix_cmd[1]).name if len(stage.fix_cmd) > 1 else ""
        phase_arg = ""
        if "--phase" in stage.fix_cmd:
            idx = stage.fix_cmd.index("--phase")
            phase_arg = stage.fix_cmd[idx + 1] if idx + 1 < len(stage.fix_cmd) else ""
        search = f"{script_name} --phase {phase_arg}" if phase_arg else script_name

        pid = is_process_running(search) if search else None
        if pid:
            print(f"    Running: {stage.name} (PID {pid})")
            if stage.heavy:
                heavy_running = True
            if stage.is_api:
                api_running = True
            continue

        if stage.heavy and heavy_running:
            print(f"    Queued:  {stage.name} (GPU busy)")
            continue
        if stage.is_api and api_running:
            print(f"    Queued:  {stage.name} (API slot busy)")
            continue

        start_process(stage)
        started += 1
        if stage.heavy:
            heavy_running = True
        if stage.is_api:
            api_running = True

    return started


# ---------------------------------------------------------------------------
# State page regeneration
# ---------------------------------------------------------------------------

def regenerate_state() -> bool:
    """Regenerate the static State dashboard."""
    script = str(BACKEND / "dashboard.py")
    try:
        result = subprocess.run(
            [sys.executable, script],
            capture_output=True, text=True, cwd=str(BACKEND), timeout=120
        )
        if result.returncode == 0:
            print("  State dashboard regenerated.")
            return True
        else:
            print(f"  State regeneration failed: {result.stderr[:200]}")
            return False
    except Exception as e:
        print(f"  State regeneration error: {e}")
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Master orchestrator — check all pipeline stages, fix gaps, update State"
    )
    parser.add_argument("--status", action="store_true",
                        help="Show status only, don't fix or regenerate")
    parser.add_argument("--watch", nargs="?", const=60, type=int, metavar="SECS",
                        help="Re-check every N seconds (default: 60)")
    parser.add_argument("--no-state", action="store_true",
                        help="Skip State dashboard regeneration")
    args = parser.parse_args()

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    def run_cycle() -> bool:
        """Run one check cycle. Returns True if everything is complete."""
        statuses = get_status(conn)
        print_status(statuses)

        all_done = all(s["complete"] for s in statuses)

        if not args.status:
            incomplete = [s for s in statuses if not s["complete"] and s["stage"].fix_cmd]
            if incomplete:
                print("  Fixing gaps...")
                started = fix_gaps(statuses)
                if started:
                    print(f"\n  Started {started} process(es).")

            if not args.no_state:
                regenerate_state()

        return all_done

    if args.watch:
        print(f"Watching every {args.watch}s. Ctrl+C to stop.\n")
        try:
            while True:
                done = run_cycle()
                if done:
                    print("  All stages complete!")
                    break
                time.sleep(args.watch)
        except KeyboardInterrupt:
            print("\nStopped.")
    else:
        done = run_cycle()
        if done and not args.status:
            print("  Everything is complete!")
        elif not args.status:
            print("\n  Run with --watch to monitor ongoing processes.")

    conn.close()


if __name__ == "__main__":
    main()
