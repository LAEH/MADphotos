#!/usr/bin/env python3
"""
serve_gallery.py — Local dev server for the MADphotos web gallery.

Serves web/ files and proxies /rendered/ to local rendered images.

Usage:
    python3 serve_gallery.py          # http://localhost:3000
    python3 serve_gallery.py --port 8080
"""
from __future__ import annotations

import argparse
import mimetypes
import os
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = PROJECT_ROOT / "frontend" / "show"
RENDERED_DIR = PROJECT_ROOT / "images" / "rendered"


class GalleryHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def do_GET(self):
        # Serve rendered images
        if self.path.startswith("/rendered/"):
            rel = self.path[len("/rendered/"):]
            file_path = RENDERED_DIR / rel
            if file_path.is_file():
                self._serve_file(file_path)
                return
            self.send_error(404)
            return

        # Default: serve from web/
        super().do_GET()

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
