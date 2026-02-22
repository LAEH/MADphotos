"""backend.MADphotos_ignition — Startup agent for MADphotos dev environment."""
from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = PROJECT_ROOT / "images" / "mad_photos.db"
BACKEND = PROJECT_ROOT / "backend"
SHOW_DIR = PROJECT_ROOT / "frontend" / "show"
SYSTEM_DIR = PROJECT_ROOT / "frontend" / "system"
SEE_DIR = PROJECT_ROOT / "frontend" / "MADphotos_local_monitoring"

# ── Server definitions ────────────────────────────────────────────────────────

CORE_SERVERS = [
    {
        "name": "serve_show",
        "cmd": ["python3", "backend/serve_show.py"],
        "cwd": PROJECT_ROOT,
        "port": 3000,
        "health_url": "http://localhost:3000/system",
        "label": "Python server (Show + System API)",
    },
    {
        "name": "vite_show",
        "cmd": ["npm", "run", "dev"],
        "cwd": SHOW_DIR,
        "port": 5173,
        "health_url": "http://localhost:5173",
        "label": "Vite dev (Show)",
    },
    {
        "name": "vite_system",
        "cmd": ["npm", "run", "dev", "--", "--port", "5174"],
        "cwd": SYSTEM_DIR,
        "port": 5174,
        "health_url": "http://localhost:5174",
        "label": "Vite dev (System)",
    },
]

# Process signatures for identifying MADphotos processes
PROCESS_SIGNATURES = [
    "serve_show", "backend/serve_show",
    "vite", "frontend/show", "frontend/system",
    "monitor.py", "backend/monitor",
]

# Ollama API
OLLAMA_URL = "http://localhost:11434/api/ps"

# Log directory
LOG_DIR = Path("/tmp")
