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
        self.send_error(404)

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
            _sys.path.insert(0, str(Path(__file__).resolve().parent))
            from dashboard import tag_location

        result = tag_location(uuid, location)
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
            _sys.path.insert(0, str(Path(__file__).resolve().parent))
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
            _sys.path.insert(0, str(Path(__file__).resolve().parent))
            from dashboard import do_pick

        result = do_pick(uuids)
        self._json_response(result)

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
                                   get_location_tagger_data)
        except ImportError:
            import sys
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from dashboard import (get_stats, get_journal_html,
                                   get_instructions_html, get_mosaics_data,
                                   get_cartoon_data, get_gemma_cartoon_data,
                                   get_all_cartoon_data, review_cartoon,
                                   similarity_search, drift_search,
                                   get_gemma_data, get_gemma_progress,
                                   get_unpicked_data,
                                   get_signal_inspector_picks_data,
                                   get_location_tagger_data)

        if self.path == "/api/locations":
            self._json_response(get_location_tagger_data())
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
