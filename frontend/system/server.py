#!/usr/bin/env python3
"""
server.py — API server for the MADphotos System dashboard.

Serves API endpoints (/api/*), rendered images, and AI variants
that the System Vite dev server proxies to.

Usage:
    python3 server.py              # http://localhost:3000
    python3 server.py --port 8080
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RENDERED_DIR = PROJECT_ROOT / "images" / "rendered"
AI_VARIANTS_DIR = PROJECT_ROOT / "images" / "ai_variants"
GENERATED_DIR = PROJECT_ROOT / "backend" / "genimages" / "output"
PREVIEW_DIR = RENDERED_DIR / "enhance_previews"

# Ensure backend is importable
import sys as _sys
_sys.path.insert(0, str(PROJECT_ROOT / "backend"))


class APIHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PROJECT_ROOT), **kwargs)

    def _json_response(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error_response(self, code, message):
        body = json.dumps({"error": message}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        if self.path == "/api/pick":
            self._handle_pick()
            return
        if self.path == "/api/cartoon/review":
            self._handle_cartoon_review()
            return
        if self.path == "/api/location/tag":
            self._handle_location_tag()
            return
        if self.path == "/api/location/untag":
            self._handle_location_untag()
            return
        if self.path == "/api/location/create":
            self._handle_location_create()
            return
        if self.path == "/api/generated/review":
            self._handle_generated_review()
            return
        if self.path == "/api/generated/generate":
            self._handle_generated_generate()
            return
        if self.path == "/api/generated/export":
            self._handle_generated_export()
            return
        if self.path == "/api/enhance/deploy":
            self._handle_enhance_deploy()
            return
        if self.path == "/api/enhance/vote":
            self._handle_enhance_vote()
            return
        if self.path == "/api/enhance/generate":
            self._handle_enhance_generate()
            return
        self.send_error(404)

    def _handle_generated_review(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
        except (json.JSONDecodeError, ValueError):
            self._error_response(400, "Invalid JSON")
            return

        variant_id = body.get("variant_id")
        status = body.get("status")
        if not variant_id or status not in ("accepted", "rejected", ""):
            self._error_response(400, "variant_id and status required")
            return
        if status == "":
            status = None

        try:
            from dashboard import review_generated
        except ImportError:
            import sys as _sys
            _sys.path.insert(0, str(PROJECT_ROOT / "backend"))
            from dashboard import review_generated

        result = review_generated(variant_id, status)
        self._json_response(result)

    def _handle_generated_progress(self):
        """Check generation progress by counting files in the latest run dir."""
        # Read expected count from file (set by generate endpoint)
        expected = 20
        count_path = Path("/tmp/generated-expected-count")
        try:
            if count_path.exists():
                expected = int(count_path.read_text().strip())
        except Exception:
            pass

        latest = None
        if GENERATED_DIR.exists():
            dirs = sorted([d for d in GENERATED_DIR.iterdir() if d.is_dir()], reverse=True)
            if dirs:
                latest = dirs[0]

        if not latest:
            self._json_response({"completed": 0, "expected": expected, "done": True})
            return

        # Count photos (UUID dirs) that have at least one variant
        completed = 0
        for uuid_dir in latest.iterdir():
            if not uuid_dir.is_dir() or uuid_dir.name.startswith("."):
                continue
            if any(uuid_dir.glob("imagen_smart_*.jpg")):
                completed += 1

        # Check if the generation script is still running
        import subprocess as _sp
        result = _sp.run(["pgrep", "-f", "genimages.run"], capture_output=True)
        running = result.returncode == 0

        self._json_response({
            "completed": completed,
            "expected": expected,
            "done": not running,
            "run_dir": latest.name,
        })

    def _handle_generated_generate(self):
        """Launch genimages pipeline in a Terminal window with configurable count."""
        import subprocess as _sp

        # Read count from POST body (default 20)
        count = 20
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            count = int(body.get("count", 20))
            count = max(1, min(count, 200))  # clamp 1-200
        except Exception:
            pass

        # Store expected count for progress endpoint
        count_path = Path("/tmp/generated-expected-count")
        count_path.write_text(str(count))

        script = f"""#!/bin/bash
cd {PROJECT_ROOT}
echo "=== Style Transfer — Generate {count} ==="
echo ""

# Ensure GCP auth is valid
if ! gcloud auth application-default print-access-token &>/dev/null; then
    echo "Re-authenticating with Google Cloud..."
    gcloud auth application-default login 2>&1
    echo ""
fi

.venv-gen/bin/python3 -u -m backend.genimages.run --count {count}
echo ""
echo "=== Generation complete ==="
echo "Press any key to close..."
read -n 1
"""
        script_path = Path("/tmp/generated-generate.sh")
        script_path.write_text(script)
        script_path.chmod(0o755)

        _sp.Popen([
            "osascript", "-e", 'tell app "Terminal" to activate',
            "-e", f'tell app "Terminal" to do script "bash {script_path}"',
        ])

        self._json_response({"ok": True, "count": count})

    def _handle_generated_export(self):
        """Launch full variant deploy pipeline in a Terminal window."""
        import subprocess as _sp
        import sqlite3

        db_path = PROJECT_ROOT / "images" / "mad_photos.db"
        try:
            conn = sqlite3.connect(str(db_path))
            count = conn.execute(
                "SELECT COUNT(*) FROM ai_variants WHERE variant_type = 'smart_style'"
                " AND review_status = 'accepted' AND exported_at IS NULL"
                " AND generation_status = 'success'"
            ).fetchone()[0]
            conn.close()
        except Exception:
            count = 0

        if count == 0:
            self._error_response(400, "No new accepted variants to export")
            return

        script = f"""#!/bin/bash
cd {PROJECT_ROOT}
echo "=== Style Transfer — Export {count} accepted variants ==="
echo ""
echo "Step 1/4 — Extract colors"
.venv-gen/bin/python3 -u backend/extract_variant_colors.py
echo ""
echo "Step 2/4 — Deploy variants (render tiers + GCS upload)"
.venv-gen/bin/python3 -u -m backend.genimages.deploy
echo ""
echo "Step 3/4 — Regenerate photos.json"
python3 -u backend/export_gallery.py
echo ""
echo "Step 4/4 — Regenerate System data"
python3 -u backend/dashboard.py
echo ""
echo "=== Export complete ==="
echo "Press any key to close..."
read -n 1
"""
        script_path = Path("/tmp/generated-export.sh")
        script_path.write_text(script)
        script_path.chmod(0o755)

        _sp.Popen([
            "osascript", "-e", 'tell app "Terminal" to activate',
            "-e", f'tell app "Terminal" to do script "bash {script_path}"',
        ])

        self._json_response({"ok": True, "count": count})

    def _handle_enhance_deploy(self):
        """Launch the full enhancement pipeline in a background Terminal window."""
        import subprocess as _sp

        from backend.suggest_image_enhancement.db import get_connection, ensure_tables, get_accepted_undeployed
        conn = get_connection()
        ensure_tables(conn)
        pending = get_accepted_undeployed(conn)
        conn.close()

        if not pending:
            self._error_response(400, "No accepted proposals to deploy")
            return

        count = len(pending)

        # Write a temp script that runs the full pipeline
        script = f"""#!/bin/bash
cd {PROJECT_ROOT}
echo "=== Enhancement Deploy Pipeline ==="
echo ""
echo "Step 1/2 — Deploy {count} accepted proposals (render tiers + GCS upload)"
python3 -u -m backend.suggest_image_enhancement.deploy
echo ""
echo "Step 2/2 — Regenerate photos.json"
python3 -u backend/export_gallery.py
echo ""
echo "=== Pipeline complete ==="
echo "Press any key to close..."
read -n 1
"""
        script_path = Path("/tmp/enhance-pipeline.sh")
        script_path.write_text(script)
        script_path.chmod(0o755)

        _sp.Popen([
            "osascript", "-e", 'tell app "Terminal" to activate',
            "-e", f'tell app "Terminal" to do script "bash {script_path}"',
        ])

        self._json_response({"ok": True, "count": count})

    def _handle_enhance_vote(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
        except (json.JSONDecodeError, ValueError):
            self._error_response(400, "Invalid JSON")
            return

        proposal_id = body.get("proposal_id")
        status = body.get("status")
        feedback = body.get("feedback")
        if not proposal_id or status not in ("accepted", "rejected", "feedback"):
            self._error_response(400, "proposal_id and status required")
            return

        from backend.suggest_image_enhancement.db import (
            get_connection, ensure_tables, update_proposal,
            complete_batch, get_accepted_undeployed,
        )
        conn = get_connection()
        ensure_tables(conn)
        ok = update_proposal(conn, int(proposal_id), status, feedback=feedback)

        # Check if batch should be completed
        batch_completed = False
        batch_id = body.get("batch_id")
        if batch_id:
            complete_batch(conn, int(batch_id))
            # Check if batch just completed (no pending left)
            pending = conn.execute(
                "SELECT count(*) FROM enhance_proposals WHERE batch_id = ? AND status IN ('pending', 'feedback')",
                (int(batch_id),),
            ).fetchone()[0]
            batch_completed = pending == 0

        # Auto-deploy when batch completes
        deploy_count = 0
        if batch_completed:
            undeployed = get_accepted_undeployed(conn)
            if undeployed:
                deploy_count = len(undeployed)
                conn.close()
                self._auto_deploy(deploy_count)
                self._json_response({"ok": ok, "batch_completed": True, "auto_deploy": deploy_count})
                return

        conn.close()
        self._json_response({"ok": ok, "batch_completed": batch_completed})

    def _auto_deploy(self, count: int):
        """Launch deploy pipeline in background when batch review completes."""
        import subprocess as _sp

        script = f"""#!/bin/bash
cd {PROJECT_ROOT}
echo "=== Auto-Deploy ({count} accepted) ==="
echo ""
echo "Step 1/3 — Deploy proposals (render tiers + GCS upload)"
python3 -u -m backend.suggest_image_enhancement.deploy
echo ""
echo "Step 2/3 — Regenerate photos.json"
python3 -u backend/export_gallery.py
echo ""
echo "Step 3/3 — Regenerate System data"
python3 -u backend/dashboard.py
echo ""
echo "=== Auto-deploy complete ==="
echo "Press any key to close..."
read -n 1
"""
        script_path = Path("/tmp/enhance-auto-deploy.sh")
        script_path.write_text(script)
        script_path.chmod(0o755)

        _sp.Popen([
            "osascript", "-e", 'tell app "Terminal" to activate',
            "-e", f'tell app "Terminal" to do script "bash {script_path}"',
        ])

    def _handle_enhance_generate(self):
        """Generate a fresh batch of ~30 proposals using iterative learning."""
        from backend.suggest_image_enhancement.propose import generate_batch

        result = generate_batch()
        self._json_response({"ok": True, **result})

    def _handle_location_tag(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
        except (json.JSONDecodeError, ValueError):
            self._error_response(400, "Invalid JSON")
            return

        uuid = body.get("uuid")
        location = body.get("location")
        if not uuid or not location:
            self._error_response(400, "uuid and location required")
            return

        try:
            from dashboard import tag_location
        except ImportError:
            import sys as _sys
            _sys.path.insert(0, str(PROJECT_ROOT / "backend"))
            from dashboard import tag_location

        result = tag_location(uuid, location)
        self._json_response(result)

    def _handle_location_untag(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
        except (json.JSONDecodeError, ValueError):
            self._error_response(400, "Invalid JSON")
            return

        uuid = body.get("uuid")
        if not uuid:
            self._error_response(400, "uuid required")
            return

        try:
            from dashboard import untag_location
        except ImportError:
            import sys as _sys
            _sys.path.insert(0, str(PROJECT_ROOT / "backend"))
            from dashboard import untag_location

        result = untag_location(uuid)
        self._json_response(result)

    def _handle_location_create(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
        except (json.JSONDecodeError, ValueError):
            self._error_response(400, "Invalid JSON")
            return

        name = (body.get("name") or "").strip()
        if not name:
            self._error_response(400, "name required")
            return

        try:
            from dashboard import register_location
        except ImportError:
            import sys as _sys
            _sys.path.insert(0, str(PROJECT_ROOT / "backend"))
            from dashboard import register_location

        result = register_location(name)
        self._json_response(result)

    def _handle_cartoon_review(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
        except (json.JSONDecodeError, ValueError):
            self._error_response(400, "Invalid JSON")
            return

        variant_id = body.get("variant_id")
        status = body.get("status")
        if not variant_id or status not in ("accepted", "rejected", ""):
            self._error_response(400, "variant_id and status (accepted/rejected/'') required")
            return
        if status == "":
            status = None

        try:
            from dashboard import review_cartoon
        except ImportError:
            import sys as _sys
            _sys.path.insert(0, str(PROJECT_ROOT / "backend"))
            from dashboard import review_cartoon

        result = review_cartoon(variant_id, status)
        self._json_response(result)

    def _handle_pick(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
        except (json.JSONDecodeError, ValueError):
            self._error_response(400, "Invalid JSON")
            return

        uuids = body.get("uuids", [])
        if not uuids or not isinstance(uuids, list):
            self._error_response(400, "uuids must be a non-empty array")
            return

        try:
            from dashboard import do_pick
        except ImportError:
            import sys as _sys
            _sys.path.insert(0, str(PROJECT_ROOT / "backend"))
            from dashboard import do_pick

        result = do_pick(uuids)
        self._json_response(result)

    def _handle_enhance_batch_get(self):
        """Return current active batch (if any). Never auto-generates."""
        from backend.suggest_image_enhancement.db import (get_connection, ensure_tables,
                                         get_or_create_batch, get_batch_proposals,
                                         get_stats as enhance_stats,
                                         get_learning_stats)
        conn = get_connection()
        ensure_tables(conn)

        # Find active batch — don't create one if none exists
        row = conn.execute(
            "SELECT id FROM enhance_batches WHERE status = 'active' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        batch_id = row["id"] if row else None

        proposals = []
        if batch_id:
            proposals = get_batch_proposals(conn, batch_id)

        learning = {t: {"rate": s["rate"], "accepted": s["accepted"], "rejected": s["rejected"]}
                    for t, s in get_learning_stats(conn).items()}
        stats = enhance_stats(conn)
        conn.close()

        items = []
        for p in proposals:
            preview_rel = p.get("preview_path", "")
            items.append({
                "id": p["id"],
                "uuid": p["image_uuid"],
                "type": p["type"],
                "params": json.loads(p["params_json"]),
                "original_url": f"/rendered/display/jpeg/{p['image_uuid']}.jpg",
                "preview_url": f"/{preview_rel}" if preview_rel else None,
                "feedback": p.get("feedback"),
            })

        self._json_response({
            "batch_id": batch_id,
            "proposals": items,
            "stats": stats["totals"],
            "learning": learning,
        })

    def _handle_enhance_stats_get(self):
        from backend.suggest_image_enhancement.db import get_connection, ensure_tables, get_stats as enhance_stats
        conn = get_connection()
        ensure_tables(conn)
        stats = enhance_stats(conn)
        conn.close()
        self._json_response(stats)

    def _handle_enhance_accepted_get(self):
        from backend.suggest_image_enhancement.db import get_connection, ensure_tables
        conn = get_connection()
        ensure_tables(conn)
        rows = conn.execute("""
            SELECT image_uuid, type, params_json, preview_path, deployed_at
            FROM enhance_proposals
            WHERE status = 'accepted'
            ORDER BY reviewed_at DESC
        """).fetchall()
        conn.close()
        items = []
        for r in rows:
            preview_rel = r["preview_path"] or ""
            items.append({
                "uuid": r["image_uuid"],
                "type": r["type"],
                "params": json.loads(r["params_json"]),
                "preview_url": f"/{preview_rel}" if preview_rel else None,
                "original_url": f"/rendered/display/jpeg/{r['image_uuid']}.jpg",
                "deployed": r["deployed_at"] is not None,
            })
        self._json_response({"accepted": items})

    def do_GET(self):
        # ── API routes ──
        if self.path.startswith("/api/"):
            self._handle_api()
            return

        # Serve rendered images
        if self.path.startswith("/rendered/"):
            rel = self.path[len("/rendered/"):]
            file_path = RENDERED_DIR / rel
            if file_path.is_file():
                self._serve_file(file_path)
                return
            self.send_error(404)
            return

        # Serve generated images
        if self.path.startswith("/generated/"):
            rel = self.path[len("/generated/"):]
            file_path = GENERATED_DIR / rel
            if file_path.is_file():
                self._serve_file(file_path)
                return
            self.send_error(404)
            return

        # Serve AI variant images
        if self.path.startswith("/ai_variants/"):
            rel = self.path[len("/ai_variants/"):]
            file_path = AI_VARIANTS_DIR / rel
            if file_path.is_file():
                self._serve_file(file_path)
                return
            self.send_error(404)
            return

        self.send_error(404)

    def _handle_api(self):
        """Delegate API requests to dashboard.py logic."""
        try:
            from dashboard import (get_stats, get_journal_html,
                                   get_instructions_html, get_mosaics_data,
                                   get_cartoon_data, get_gemma_cartoon_data,
                                   get_all_cartoon_data, review_cartoon,
                                   similarity_search, drift_search,
                                   get_gemma_data, get_gemma_progress,
                                   get_unpicked_data,
                                   get_signal_inspector_picks_data,
                                   get_location_tagger_data,
                                   get_generated_data)
        except ImportError:
            import sys
            sys.path.insert(0, str(PROJECT_ROOT / "backend"))
            from dashboard import (get_stats, get_journal_html,
                                   get_instructions_html, get_mosaics_data,
                                   get_cartoon_data, get_gemma_cartoon_data,
                                   get_all_cartoon_data, review_cartoon,
                                   similarity_search, drift_search,
                                   get_gemma_data, get_gemma_progress,
                                   get_unpicked_data,
                                   get_signal_inspector_picks_data,
                                   get_location_tagger_data,
                                   get_generated_data)

        if self.path == "/api/enhance/batch":
            self._handle_enhance_batch_get()
            return
        if self.path == "/api/enhance/stats":
            self._handle_enhance_stats_get()
            return
        if self.path == "/api/enhance/accepted":
            self._handle_enhance_accepted_get()
            return

        if self.path.startswith("/api/locations"):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            camera = qs.get("camera", [None])[0]
            obj = qs.get("obj", [None])[0]
            self._json_response(get_location_tagger_data(camera=camera, obj=obj))
        elif self.path == "/api/generated/progress":
            self._handle_generated_progress()
            return
        elif self.path == "/api/generated":
            self._json_response(get_generated_data())
        elif self.path == "/api/cartoons":
            self._json_response(get_all_cartoon_data())
        elif self.path == "/api/signal-inspector":
            self._json_response(get_signal_inspector_picks_data())
        elif self.path == "/api/unpicked":
            self._json_response(get_unpicked_data())
        elif self.path == "/api/stats":
            self._json_response(get_stats())
        elif self.path == "/api/journal":
            self._json_response({"html": get_journal_html()})
        elif self.path == "/api/instructions":
            self._json_response({"html": get_instructions_html()})
        elif self.path == "/api/mosaics":
            self._json_response({"mosaics": get_mosaics_data()})
        elif self.path == "/api/cartoon":
            self._json_response({"pairs": get_cartoon_data()})
        elif self.path == "/api/gemma-cartoon":
            self._json_response({"pairs": get_gemma_cartoon_data()})
        elif self.path == "/api/gemma/progress":
            self._json_response(get_gemma_progress())
        elif self.path == "/api/gemma":
            self._json_response(get_gemma_data())
        elif self.path.startswith("/api/similarity/"):
            uuid_part = self.path[16:]
            if uuid_part == "random":
                import random
                try:
                    from dashboard import _get_lance
                    tbl, df = _get_lance()
                    if tbl is not None:
                        self._json_response({"uuid": random.choice(df["uuid"].tolist())})
                    else:
                        self._json_response({"error": "no vectors"})
                except Exception:
                    self._json_response({"error": "no vectors"})
            else:
                result = similarity_search(uuid_part)
                self._json_response(result or {"error": "not found"})
        elif self.path.startswith("/api/drift/"):
            uuid_part = self.path[11:]
            if uuid_part == "random":
                import random
                try:
                    from dashboard import _get_lance
                    tbl, df = _get_lance()
                    if tbl is not None:
                        self._json_response({"uuid": random.choice(df["uuid"].tolist())})
                    else:
                        self._json_response({"error": "no vectors"})
                except Exception:
                    self._json_response({"error": "no vectors"})
            else:
                result = drift_search(uuid_part)
                self._json_response(result or {"error": "not found"})
        else:
            self.send_error(404)

    def _serve_file(self, file_path: Path):
        mime, _ = mimetypes.guess_type(str(file_path))
        if not mime:
            mime = "application/octet-stream"
        try:
            data = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            if "enhance_previews" in str(file_path):
                self.send_header("Cache-Control", "no-cache")
            else:
                self.send_header("Cache-Control", "public, max-age=3600")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            self.send_error(500)

    def log_message(self, format, *args):
        if len(args) >= 2 and args[1] == "200" and ("/rendered/" in args[0] or "/data/" in args[0]):
            return
        super().log_message(format, *args)


def main():
    parser = argparse.ArgumentParser(description="MADphotos System API server")
    parser.add_argument("--port", type=int, default=3000)
    args = parser.parse_args()

    server = HTTPServer(("0.0.0.0", args.port), APIHandler)
    print(f"MADphotos API — http://localhost:{args.port}")
    print(f"  Rendered: {RENDERED_DIR}")
    print()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
