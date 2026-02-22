#!/usr/bin/env python3
"""deploy.py — Thin shim. All logic lives in backend.update_and_deploy.

Preserves launchd plist compatibility. Forwards all args.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from update_and_deploy.run import main

if __name__ == "__main__":
    main()
