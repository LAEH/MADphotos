#!/usr/bin/env python3
"""
serve_show.py — Unified local dev server for MADphotos.

Serves Show web files, System React SPA, rendered images, AI variants,
generated images, and all API endpoints.

Usage:
    python3 backend/serve_show.py          # http://localhost:3000
    python3 backend/serve_show.py --port 8080
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import subprocess
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = PROJECT_ROOT / "frontend" / "show"
STATE_DIR = PROJECT_ROOT / "frontend" / "system"
STATE_DIST = STATE_DIR / "dist"
RENDERED_DIR = PROJECT_ROOT / "images" / "rendered"
AI_VARIANTS_DIR = PROJECT_ROOT / "images" / "ai_variants"
GENERATED_DIR = PROJECT_ROOT / "backend" / "suggest_image_variant" / "output"

# Ensure backend is importable
import sys as _sys
_sys.path.insert(0, str(PROJECT_ROOT))
_sys.path.insert(0, str(PROJECT_ROOT / "backend"))


def _import_dashboard():
    """Lazy import all dashboard functions."""
    from dashboard import (
        get_stats, get_journal_html, get_instructions_html, get_mosaics_data,
        get_cartoon_data, get_gemma_cartoon_data, get_all_cartoon_data,
        review_cartoon, similarity_search, drift_search, _get_lance,
        get_gemma_data, get_gemma_progress,
        get_generated_data, review_generated, get_variant_review_data, batch_reject_variants,
        get_unpicked_data, get_signal_inspector_picks_data,
        get_location_tagger_data,
        do_pick, tag_location, untag_location, register_location,
    )
    return locals()


class GalleryHandler(SimpleHTTPRequestHandler):
    _dashboard = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    @classmethod
    def _db(cls):
        if cls._dashboard is None:
            cls._dashboard = _import_dashboard()
        return cls._dashboard

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

    def _read_json_body(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(length)) if length else {}
        except (json.JSONDecodeError, ValueError):
            return None

    # ── OPTIONS (CORS) ──

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ── POST ──

    def do_POST(self):
        if self.path == "/api/generated/review":
            self._post_generated_review()
        elif self.path == "/api/generated/generate":
            self._post_generated_generate()
        elif self.path == "/api/generated/export":
            self._post_generated_export()
        elif self.path == "/api/variant-review/reject":
            self._post_variant_batch_reject()
        elif self.path == "/api/cartoon/review":
            self._post_cartoon_review()
        elif self.path == "/api/pick":
            self._post_pick()
        elif self.path == "/api/location/tag":
            self._post_location_tag()
        elif self.path == "/api/location/untag":
            self._post_location_untag()
        elif self.path == "/api/location/create":
            self._post_location_create()
        elif self.path == "/api/enhance/vote":
            self._post_enhance_vote()
        elif self.path == "/api/enhance/deploy":
            self._post_enhance_deploy()
        elif self.path == "/api/enhance/generate":
            self._post_enhance_generate()
        elif self.path == "/api/bento/render":
            self._post_bento_render()
        elif self.path == "/api/border-crops/apply":
            self._post_border_crops_apply()
        else:
            self.send_error(404)

    # ── GET ──

    def do_GET(self):
        if self.path.startswith("/api/"):
            self._handle_api()
            return

        if self.path.startswith("/rendered/"):
            self._serve_static(RENDERED_DIR, self.path[len("/rendered/"):])
            return

        if self.path.startswith("/ai_variants/"):
            self._serve_static(AI_VARIANTS_DIR, self.path[len("/ai_variants/"):])
            return

        if self.path.startswith("/generated/"):
            self._serve_static(GENERATED_DIR, self.path[len("/generated/"):])
            return

        if self.path.startswith("/system"):
            self._serve_system()
            return

        super().do_GET()

    # ── API GET routes ──

    def _handle_api(self):
        fn = self._db()
        path = self.path.split("?")[0]  # strip query string
        from urllib.parse import urlparse, parse_qs

        if path == "/api/stats":
            self._json_response(fn["get_stats"]())
        elif path == "/api/journal":
            self._json_response({"html": fn["get_journal_html"]()})
        elif path == "/api/instructions":
            self._json_response({"html": fn["get_instructions_html"]()})
        elif path == "/api/mosaics":
            self._json_response({"mosaics": fn["get_mosaics_data"]()})
        elif path == "/api/cartoon":
            self._json_response({"pairs": fn["get_cartoon_data"]()})
        elif path == "/api/gemma-cartoon":
            self._json_response({"pairs": fn["get_gemma_cartoon_data"]()})
        elif path == "/api/cartoons":
            self._json_response(fn["get_all_cartoon_data"]())
        elif path == "/api/gemma/progress":
            self._json_response(fn["get_gemma_progress"]())
        elif path == "/api/gemma":
            self._json_response(fn["get_gemma_data"]())
        elif path == "/api/generated":
            self._json_response(fn["get_generated_data"]())
        elif path == "/api/generated/progress":
            self._handle_generated_progress()
        elif path == "/api/variant-review":
            self._json_response(fn["get_variant_review_data"]())
        elif path == "/api/signal-inspector":
            self._json_response(fn["get_signal_inspector_picks_data"]())
        elif path == "/api/unpicked":
            self._json_response(fn["get_unpicked_data"]())
        elif self.path.startswith("/api/locations"):
            qs = parse_qs(urlparse(self.path).query)
            camera = qs.get("camera", [None])[0]
            obj = qs.get("obj", [None])[0]
            self._json_response(fn["get_location_tagger_data"](camera=camera, obj=obj))
        elif path == "/api/bento/loved":
            self._handle_bento_loved()
        elif path == "/api/border-crops":
            self._handle_border_crops()
        elif path == "/api/enhance/batch":
            self._handle_enhance_batch()
        elif path == "/api/enhance/stats":
            self._handle_enhance_stats()
        elif path == "/api/enhance/accepted":
            self._handle_enhance_accepted()
        elif self.path.startswith("/api/similarity/"):
            uuid_part = self.path[16:]
            self._handle_vector_search(uuid_part, fn["similarity_search"], fn["_get_lance"])
        elif self.path.startswith("/api/drift/"):
            uuid_part = self.path[11:]
            self._handle_vector_search(uuid_part, fn["drift_search"], fn["_get_lance"])
        else:
            self.send_error(404)

    def _handle_vector_search(self, uuid_part, search_fn, get_lance_fn):
        if uuid_part == "random":
            import random
            try:
                tbl, df = get_lance_fn()
                if tbl is not None:
                    self._json_response({"uuid": random.choice(df["uuid"].tolist())})
                else:
                    self._json_response({"error": "no vectors"})
            except Exception:
                self._json_response({"error": "no vectors"})
        else:
            result = search_fn(uuid_part)
            self._json_response(result or {"error": "not found"})

    # ── POST handlers ──

    def _post_generated_review(self):
        body = self._read_json_body()
        if body is None:
            return self._error_response(400, "Invalid JSON")
        variant_id = body.get("variant_id")
        status = body.get("status")
        if not variant_id or status not in ("accepted", "rejected", ""):
            return self._error_response(400, "variant_id and status required")
        comment = body.get("comment")
        self._json_response(self._db()["review_generated"](variant_id, status or None, comment))

    def _post_variant_batch_reject(self):
        body = self._read_json_body()
        if body is None:
            return self._error_response(400, "Invalid JSON")
        ids = body.get("variant_ids", [])
        if not isinstance(ids, list):
            return self._error_response(400, "variant_ids must be a list")
        self._json_response(self._db()["batch_reject_variants"](ids))

    def _post_generated_generate(self):
        count = 20
        try:
            body = self._read_json_body() or {}
            count = max(1, min(int(body.get("count", 20)), 200))
        except Exception:
            pass

        Path("/tmp/generated-expected-count").write_text(str(count))
        Path("/tmp/generated-start-time").write_text(str(int(time.time())))
        script = f"""#!/bin/bash
cd {PROJECT_ROOT}
echo "=== Style Transfer — Generate {count} ==="
echo ""
if ! gcloud auth application-default print-access-token &>/dev/null; then
    echo "Re-authenticating with Google Cloud..."
    gcloud auth application-default login 2>&1
    echo ""
fi
.venv-gen/bin/python3 -u -m backend.suggest_image_variant.run --count {count}
echo ""
echo "=== Generation complete ==="
echo "Done."
"""
        script_path = Path("/tmp/generated-generate.sh")
        script_path.write_text(script)
        script_path.chmod(0o755)
        subprocess.Popen([
            "osascript", "-e", 'tell app "Terminal" to activate',
            "-e", f'tell app "Terminal" to do script "bash {script_path}"',
        ])
        self._json_response({"ok": True, "count": count})

    def _post_generated_export(self):
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
            return self._error_response(400, "No new accepted variants to export")
        script = f"""#!/bin/bash
cd {PROJECT_ROOT}
echo "=== Style Transfer — Export {count} accepted variants ==="
echo ""
echo "Step 1/4 — Extract colors"
.venv-gen/bin/python3 -u backend/extract_variant_colors.py
echo ""
echo "Step 2/4 — Deploy variants (render tiers + GCS upload)"
.venv-gen/bin/python3 -u -m backend.suggest_image_variant.deploy
echo ""
echo "Step 3/4 — Regenerate photos.json"
python3 -u backend/export_gallery.py
echo ""
echo "Step 4/4 — Regenerate System data"
python3 -u backend/dashboard.py
echo ""
echo "=== Export complete ==="
echo "Done."
"""
        script_path = Path("/tmp/generated-export.sh")
        script_path.write_text(script)
        script_path.chmod(0o755)
        subprocess.Popen([
            "osascript", "-e", 'tell app "Terminal" to activate',
            "-e", f'tell app "Terminal" to do script "bash {script_path}"',
        ])
        self._json_response({"ok": True, "count": count})

    def _post_cartoon_review(self):
        body = self._read_json_body()
        if body is None:
            return self._error_response(400, "Invalid JSON")
        variant_id = body.get("variant_id")
        status = body.get("status")
        if not variant_id or status not in ("accepted", "rejected", ""):
            return self._error_response(400, "variant_id and status required")
        self._json_response(self._db()["review_cartoon"](variant_id, status or None))

    def _post_pick(self):
        body = self._read_json_body()
        if body is None:
            return self._error_response(400, "Invalid JSON")
        uuids = body.get("uuids", [])
        if not uuids or not isinstance(uuids, list):
            return self._error_response(400, "uuids must be a non-empty array")
        self._json_response(self._db()["do_pick"](uuids))

    def _post_location_tag(self):
        body = self._read_json_body()
        if body is None:
            return self._error_response(400, "Invalid JSON")
        uuid = body.get("uuid")
        location = body.get("location")
        if not uuid or not location:
            return self._error_response(400, "uuid and location required")
        self._json_response(self._db()["tag_location"](uuid, location))

    def _post_location_untag(self):
        body = self._read_json_body()
        if body is None:
            return self._error_response(400, "Invalid JSON")
        uuid = body.get("uuid")
        if not uuid:
            return self._error_response(400, "uuid required")
        self._json_response(self._db()["untag_location"](uuid))

    def _post_location_create(self):
        body = self._read_json_body()
        if body is None:
            return self._error_response(400, "Invalid JSON")
        name = (body.get("name") or "").strip()
        if not name:
            return self._error_response(400, "name required")
        self._json_response(self._db()["register_location"](name))

    def _post_enhance_vote(self):
        body = self._read_json_body()
        if body is None:
            return self._error_response(400, "Invalid JSON")
        proposal_id = body.get("proposal_id")
        status = body.get("status")
        feedback = body.get("feedback")
        if not proposal_id or status not in ("accepted", "rejected", "feedback"):
            return self._error_response(400, "proposal_id and status required")
        from backend.suggest_image_enhancement.db import (
            get_connection, ensure_tables, update_proposal,
            complete_batch, get_accepted_undeployed,
        )
        conn = get_connection()
        ensure_tables(conn)
        ok = update_proposal(conn, int(proposal_id), status, feedback=feedback)
        batch_id = body.get("batch_id")
        batch_completed = False
        if batch_id:
            complete_batch(conn, int(batch_id))
            pending = conn.execute(
                "SELECT count(*) FROM enhance_proposals WHERE batch_id = ? "
                "AND status IN ('pending', 'feedback')", (int(batch_id),)
            ).fetchone()[0]
            batch_completed = pending == 0
        deploy_count = 0
        if batch_completed:
            undeployed = get_accepted_undeployed(conn)
            if undeployed:
                deploy_count = len(undeployed)
                conn.close()
                self._launch_deploy(deploy_count)
                return self._json_response({"ok": ok, "batch_completed": True, "auto_deploy": deploy_count})
        conn.close()
        self._json_response({"ok": ok, "batch_completed": batch_completed})

    def _post_enhance_deploy(self):
        from backend.suggest_image_enhancement.db import get_connection, ensure_tables, get_accepted_undeployed
        conn = get_connection()
        ensure_tables(conn)
        pending = get_accepted_undeployed(conn)
        conn.close()
        if not pending:
            return self._error_response(400, "No accepted proposals to deploy")
        self._launch_deploy(len(pending))
        self._json_response({"ok": True, "count": len(pending)})

    def _post_enhance_generate(self):
        from backend.suggest_image_enhancement.propose import generate_batch
        result = generate_batch()
        self._json_response({"ok": True, **result})

    # ── Bento render/loved ──

    def _post_bento_render(self):
        body = self._read_json_body()
        if body is None:
            return self._error_response(400, "Invalid JSON")
        cols = body.get("cols")
        rows = body.get("rows")
        cells = body.get("cells")
        photo_ids = body.get("photos")
        if not all([cols, rows, cells, photo_ids]):
            return self._error_response(400, "cols, rows, cells, photos required")
        from backend.render_bento import render_bento_png
        result = render_bento_png(
            cols=cols, rows=rows, cells=cells, photo_ids=photo_ids,
            layout_id=body.get("layoutId", ""),
            curator=body.get("curator", ""),
        )
        if result:
            self._json_response(result)
        else:
            self._error_response(500, "Failed to render bento")

    def _handle_bento_loved(self):
        bentos_dir = RENDERED_DIR / "bentos"
        if not bentos_dir.exists():
            return self._json_response({"bentos": []})
        items = []
        for meta_file in sorted(bentos_dir.glob("*_meta.json"), reverse=True):
            try:
                meta = json.loads(meta_file.read_text())
                items.append({
                    "id": meta_file.stem.replace("_meta", ""),
                    "timestamp": meta.get("timestamp", 0),
                    "layout_id": meta.get("layout_id", ""),
                    "cols": meta.get("cols"),
                    "rows": meta.get("rows"),
                    "photo_count": meta.get("placed", 0),
                    "width": meta.get("output_width"),
                    "height": meta.get("output_height"),
                    "preview_url": f"/rendered/bentos/{meta.get('preview', '')}",
                    "png_url": f"/rendered/bentos/{meta.get('png', '')}",
                    "curator": meta.get("curator", ""),
                })
            except Exception:
                continue
        self._json_response({"bentos": items})

    # ── Border crop helpers ──

    def _handle_border_crops(self):
        crops_file = Path("/tmp/variant_border_crops.json")
        if not crops_file.exists():
            return self._json_response({"crops": []})
        try:
            data = json.loads(crops_file.read_text())
            return self._json_response({"crops": data})
        except Exception as e:
            return self._error_response(500, str(e))

    def _post_border_crops_apply(self):
        body = self._read_json_body()
        if body is None:
            return self._error_response(400, "Invalid JSON")
        crops = body.get("crops", [])
        if not isinstance(crops, list) or not crops:
            return self._error_response(400, "crops must be a non-empty array")

        from PIL import Image
        import sqlite3

        variants_dir = RENDERED_DIR / "variants"
        tiers = ["display", "thumb", "micro", "mobile"]
        formats = ["jpeg", "webp"]
        results = []
        errors = []

        for crop in crops:
            uuid = crop.get("uuid")
            left = crop.get("left", 0)
            right = crop.get("right", 0)
            top = crop.get("top", 0)
            bottom = crop.get("bottom", 0)
            if not uuid:
                continue

            cropped_files = 0
            for tier in tiers:
                for fmt in formats:
                    ext = "jpg" if fmt == "jpeg" else "webp"
                    file_path = variants_dir / tier / fmt / f"{uuid}.{ext}"
                    if not file_path.exists():
                        continue
                    try:
                        img = Image.open(file_path)
                        w, h = img.size
                        # Scale crop values proportionally from display tier to this tier
                        # The crop JSON has values for the display tier dimensions
                        display_path = variants_dir / "display" / "jpeg" / f"{uuid}.jpg"
                        if display_path.exists() and tier != "display":
                            disp = Image.open(display_path)
                            dw, dh = disp.size
                            disp.close()
                            sx = w / dw if dw else 1
                            sy = h / dh if dh else 1
                        elif tier != "display":
                            # Fallback: use raw crop JSON w/h
                            dw = crop.get("w", w)
                            dh = crop.get("h", h)
                            sx = w / dw if dw else 1
                            sy = h / dh if dh else 1
                        else:
                            sx, sy = 1.0, 1.0

                        cl = int(round(left * sx))
                        cr = int(round(right * sx))
                        ct = int(round(top * sy))
                        cb = int(round(bottom * sy))

                        new_left = cl
                        new_top = ct
                        new_right = w - cr
                        new_bottom = h - cb

                        if new_right <= new_left or new_bottom <= new_top:
                            continue

                        cropped = img.crop((new_left, new_top, new_right, new_bottom))
                        if fmt == "jpeg":
                            cropped.save(str(file_path), "JPEG", quality=92)
                        else:
                            cropped.save(str(file_path), "WEBP", quality=88)
                        img.close()
                        cropped.close()
                        cropped_files += 1
                    except Exception as e:
                        errors.append(f"{uuid}/{tier}/{fmt}: {e}")

            results.append({"uuid": uuid, "files_cropped": cropped_files})

        # Update DB
        db_path = PROJECT_ROOT / "images" / "mad_photos.db"
        try:
            conn = sqlite3.connect(str(db_path))
            for crop in crops:
                uuid = crop.get("uuid")
                if not uuid:
                    continue
                conn.execute(
                    "UPDATE ai_variants SET border_left=?, border_right=?, "
                    "border_top=?, border_bottom=?, trimmed=1 WHERE variant_id=?",
                    (crop.get("left", 0), crop.get("right", 0),
                     crop.get("top", 0), crop.get("bottom", 0), uuid),
                )
            conn.commit()
            conn.close()
        except Exception as e:
            errors.append(f"DB update: {e}")

        self._json_response({
            "ok": True,
            "results": results,
            "errors": errors,
            "total_cropped": sum(r["files_cropped"] for r in results),
        })

    # ── Enhance GET helpers ──

    def _handle_enhance_batch(self):
        from backend.suggest_image_enhancement.db import (
            get_connection, ensure_tables, get_batch_proposals,
            get_stats as enhance_stats, get_learning_stats,
        )
        conn = get_connection()
        ensure_tables(conn)
        row = conn.execute(
            "SELECT id FROM enhance_batches WHERE status = 'active' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        batch_id = row["id"] if row else None
        proposals = get_batch_proposals(conn, batch_id) if batch_id else []
        learning = {t: {"rate": s["rate"], "accepted": s["accepted"], "rejected": s["rejected"]}
                    for t, s in get_learning_stats(conn).items()}
        stats = enhance_stats(conn)
        conn.close()
        items = [{
            "id": p["id"], "uuid": p["image_uuid"], "type": p["type"],
            "params": json.loads(p["params_json"]),
            "original_url": f"/rendered/display/jpeg/{p['image_uuid']}.jpg",
            "preview_url": f"/{p.get('preview_path', '')}" if p.get("preview_path") else None,
            "feedback": p.get("feedback"),
        } for p in proposals]
        self._json_response({"batch_id": batch_id, "proposals": items, "stats": stats["totals"], "learning": learning})

    def _handle_enhance_stats(self):
        from backend.suggest_image_enhancement.db import get_connection, ensure_tables, get_stats as enhance_stats
        conn = get_connection()
        ensure_tables(conn)
        stats = enhance_stats(conn)
        conn.close()
        self._json_response(stats)

    def _handle_enhance_accepted(self):
        from backend.suggest_image_enhancement.db import get_connection, ensure_tables
        conn = get_connection()
        ensure_tables(conn)
        rows = conn.execute(
            "SELECT image_uuid, type, params_json, preview_path, deployed_at "
            "FROM enhance_proposals WHERE status = 'accepted' ORDER BY reviewed_at DESC"
        ).fetchall()
        conn.close()
        self._json_response({"accepted": [{
            "uuid": r["image_uuid"], "type": r["type"],
            "params": json.loads(r["params_json"]),
            "preview_url": f"/{r['preview_path']}" if r["preview_path"] else None,
            "original_url": f"/rendered/display/jpeg/{r['image_uuid']}.jpg",
            "deployed": r["deployed_at"] is not None,
        } for r in rows]})

    # ── Generated progress ──

    def _handle_generated_progress(self):
        expected = 20
        try:
            p = Path("/tmp/generated-expected-count")
            if p.exists():
                expected = int(p.read_text().strip())
        except Exception:
            pass
        latest = None
        if GENERATED_DIR.exists():
            dirs = sorted([d for d in GENERATED_DIR.iterdir() if d.is_dir()], reverse=True)
            if dirs:
                latest = dirs[0]
        if not latest:
            # Still respect grace period (process may be authenticating before creating output dir)
            start_time = 0
            try:
                st = Path("/tmp/generated-start-time")
                if st.exists():
                    start_time = int(st.read_text().strip())
            except Exception:
                pass
            in_grace = (time.time() - start_time) < 30 if start_time else False
            return self._json_response({"completed": 0, "expected": expected, "done": not in_grace})
        completed = sum(1 for d in latest.iterdir()
                        if d.is_dir() and not d.name.startswith(".")
                        and any(d.glob("imagen_smart_*.jpg")))
        # Check only the Python generation process (not the bash wrapper which idles at "press any key")
        py_proc = subprocess.run(["pgrep", "-f", "suggest_image_variant.run"], capture_output=True)
        process_running = py_proc.returncode == 0
        # Grace period: don't report done within 30s of launch (auth may be in progress)
        start_time = 0
        try:
            st = Path("/tmp/generated-start-time")
            if st.exists():
                start_time = int(st.read_text().strip())
        except Exception:
            pass
        in_grace = (time.time() - start_time) < 30 if start_time else False
        done = not process_running and not in_grace
        self._json_response({
            "completed": completed, "expected": expected,
            "done": done, "run_dir": latest.name,
        })

    # ── Deploy helper ──

    def _launch_deploy(self, count):
        script = f"""#!/bin/bash
cd {PROJECT_ROOT}
echo "=== Auto-Deploy ({count} accepted) ==="
echo ""
echo "Step 1/3 — Deploy proposals"
python3 -u -m backend.suggest_image_enhancement.deploy
echo ""
echo "Step 2/3 — Regenerate photos.json"
python3 -u backend/export_gallery.py
echo ""
echo "Step 3/3 — Regenerate System data"
python3 -u backend/dashboard.py
echo ""
echo "=== Deploy complete ==="
echo "Done."
"""
        script_path = Path("/tmp/enhance-auto-deploy.sh")
        script_path.write_text(script)
        script_path.chmod(0o755)
        subprocess.Popen([
            "osascript", "-e", 'tell app "Terminal" to activate',
            "-e", f'tell app "Terminal" to do script "bash {script_path}"',
        ])

    # ── File serving ──

    def _serve_static(self, base_dir, rel):
        file_path = base_dir / rel
        if file_path.is_file():
            self._serve_file(file_path)
        else:
            self.send_error(404)

    def _serve_system(self):
        path = self.path
        if path == "/system":
            path = "/system/"
        rel = path[len("/system/"):] or "index.html"
        for base_dir in [STATE_DIST, STATE_DIR]:
            if (base_dir / rel).is_file():
                return self._serve_file(base_dir / rel)
        for base_dir in [STATE_DIST, STATE_DIR]:
            if (base_dir / "index.html").is_file():
                return self._serve_file(base_dir / "index.html")
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
            self.send_header("Cache-Control", "no-cache" if "enhance_previews" in str(file_path)
                             else "public, max-age=3600")
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
    parser = argparse.ArgumentParser(description="MADphotos dev server")
    parser.add_argument("--port", type=int, default=3000)
    args = parser.parse_args()

    server = HTTPServer(("0.0.0.0", args.port), GalleryHandler)
    print(f"MADphotos — http://localhost:{args.port}")
    print(f"  Show:    http://localhost:{args.port}")
    print(f"  System:  http://localhost:{args.port}/system")
    print(f"  APIs:    http://localhost:{args.port}/api/*")
    print()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
