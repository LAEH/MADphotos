#!/usr/bin/env python3
"""Thin shim — all logic lives in backend.api.* modules.

Usage:
    python dashboard.py              # Generate static HTML files
    python dashboard.py --serve      # Live dashboard at localhost:8080
    python dashboard.py --serve 9000 # Custom port
"""
import sys
from api import *  # noqa: F401,F403 — re-export everything for existing consumers

if __name__ == "__main__":
    if "--serve" in sys.argv:
        idx = sys.argv.index("--serve")
        port = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) and sys.argv[idx + 1].isdigit() else 8080
        serve(port)
    else:
        generate_static()
