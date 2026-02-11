#!/usr/bin/env python3
"""
serve_gallery.py — Local dev server for the MADphotos web gallery.

Serves web/ files, rendered images, AI variants, State dashboard (React SPA),
and API endpoints.

Usage:
    python3 serve_gallery.py          # http://localhost:3000
    python3 serve_gallery.py --port 8080
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = PROJECT_ROOT / "frontend" / "show"
STATE_DIR = PROJECT_ROOT / "frontend" / "system"
STATE_DIST = STATE_DIR / "dist"  # Vite build output
RENDERED_DIR = PROJECT_ROOT / "images" / "rendered"
AI_VARIANTS_DIR = PROJECT_ROOT / "images" / "ai_variants"


class GalleryHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def _json_response(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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

        # Serve System React SPA (Vite build)
        if self.path.startswith("/system"):
            self._serve_system()
            return

        # Default: serve from web/ (Show app)
        super().do_GET()

    def _handle_api(self):
        """Delegate API requests to dashboard.py logic."""
        try:
            from dashboard import (get_stats, get_journal_html,
                                   get_instructions_html, get_mosaics_data,
                                   get_cartoon_data, similarity_search, drift_search,
                                   get_gemma_data)
        except ImportError:
            # Try relative import path
            import sys
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from dashboard import (get_stats, get_journal_html,
                                   get_instructions_html, get_mosaics_data,
                                   get_cartoon_data, similarity_search, drift_search,
                                   get_gemma_data)

        if self.path == "/api/stats":
            self._json_response(get_stats())
        elif self.path == "/api/journal":
            self._json_response({"html": get_journal_html()})
        elif self.path == "/api/instructions":
            self._json_response({"html": get_instructions_html()})
        elif self.path == "/api/mosaics":
            self._json_response({"mosaics": get_mosaics_data()})
        elif self.path == "/api/cartoon":
            self._json_response({"pairs": get_cartoon_data()})
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

    def _serve_system(self):
        """Serve System React SPA with fallback to index.html for client-side routing."""
        # Strip /system prefix and optional trailing content
        path = self.path
        if path == "/system":
            path = "/system/"

        rel = path[len("/system/"):]
        if not rel:
            rel = "index.html"

        # Try Vite dist first, then raw state dir
        for base_dir in [STATE_DIST, STATE_DIR]:
            file_path = base_dir / rel
            if file_path.is_file():
                self._serve_file(file_path)
                return

        # SPA fallback: serve index.html for any unmatched /system/* route
        for base_dir in [STATE_DIST, STATE_DIR]:
            index = base_dir / "index.html"
            if index.is_file():
                self._serve_file(index)
                return

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
        # Quieter logging: skip successful image loads
        if len(args) >= 2 and args[1] == "200" and ("/rendered/" in args[0] or "/data/" in args[0]):
            return
        super().log_message(format, *args)


def main():
    parser = argparse.ArgumentParser(description="MADphotos gallery dev server")
    parser.add_argument("--port", type=int, default=3000)
    args = parser.parse_args()

    server = HTTPServer(("0.0.0.0", args.port), GalleryHandler)
    print(f"MADphotos Gallery — http://localhost:{args.port}")
    print(f"  Web root: {WEB_DIR}")
    print(f"  Rendered: {RENDERED_DIR}")
    print()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
