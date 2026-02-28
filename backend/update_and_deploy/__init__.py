"""backend.update_and_deploy — Unified deploy pipeline for MADphotos."""
from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = PROJECT_ROOT / "images" / "mad_photos.db"
BACKEND = PROJECT_ROOT / "backend"
SHOW_DIR = PROJECT_ROOT / "frontend" / "show"
SYSTEM_DIR = PROJECT_ROOT / "frontend" / "system"
SHOW_DATA_DIR = SHOW_DIR / "data"
SYSTEM_DATA_DIR = SYSTEM_DIR / "public" / "data"
FINGERPRINT_PATH = PROJECT_ROOT / ".gallery_fingerprint.json"

# Agent folders that get yellow Finder labels
AGENT_FOLDERS = [
    BACKEND / "update_and_deploy",
    BACKEND / "suggest_image_variant",
    BACKEND / "suggest_image_enhancement",
    BACKEND / "image_signals",
    BACKEND / "prepare_show",
    BACKEND / "MADphotos_ignition",
]

# Processes that write to the DB — unsafe to deploy alongside
BLOCKING_PROCESSES = [
    "run_gemma_analysis", "run_gemma_forever", "gemma_monitor",
    "signals.py", "signals_advanced.py", "signals_v2.py",
    "render.py", "enhance", "imagen.py", "pipeline.py",
    "vectors.py", "vectors_v2.py", "firestore_sync",
    "export_gallery",
]

# Read-only processes — safe to deploy alongside
NON_BLOCKING_PROCESSES = [
    "serve_show", "dashboard.py", "server.py", "vite", "monitor.py",
]

# Port map for health checks
PORT_MAP = {
    "3000": "Show server (serve_show.py)",
    "5173": "Vite dev (Show or System)",
    "5174": "Vite dev (secondary)",
    "8080": "Dashboard API",
    "11434": "Ollama",
}

# Live URLs for post-deploy verification
LIVE_URLS = [
    "https://madphotos.laeh.ai",
    "https://madphotos.laeh.ai/system",
    "https://madphotos.laeh.ai/data/photos.json",
]

FIREBASE_PROJECT = "laeh380to760"
FIREBASE_HOSTING = "laeh-madphotos"
