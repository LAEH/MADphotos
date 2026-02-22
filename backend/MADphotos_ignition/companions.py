"""Phase 4: Companions — terminal monitor, native See app, Ollama report."""
from __future__ import annotations

import json
import subprocess
import urllib.request
from pathlib import Path

from . import OLLAMA_URL, PROJECT_ROOT, SEE_DIR


# ── ANSI ──────────────────────────────────────────────────────────────────────

R = "\033[0m"
B = "\033[1m"
GN = "\033[32m"
YL = "\033[33m"
RD = "\033[31m"
DM = "\033[38;5;245m"


def ok(msg: str) -> None:
    print(f"  {GN}✓{R} {msg}")


def warn(msg: str) -> None:
    print(f"  {YL}⚠{R} {msg}")


def fail(msg: str) -> None:
    print(f"  {RD}✗{R} {msg}")


# ── Terminal monitor ──────────────────────────────────────────────────────────

def start_monitor(dry: bool = False) -> dict:
    """Open monitor.py in a new Terminal.app window via osascript."""
    monitor_path = PROJECT_ROOT / "backend" / "monitor.py"
    if not monitor_path.exists():
        warn("monitor.py not found — skipping")
        return {"ok": False, "error": "not found"}

    script = f"""#!/bin/bash
cd {PROJECT_ROOT}
.venv-gen/bin/python3 -u backend/monitor.py
"""
    if dry:
        print("  (dry) Would open monitor.py in new Terminal window")
        return {"ok": True}

    script_path = Path("/tmp/madphotos_ignition_monitor.sh")
    script_path.write_text(script)
    script_path.chmod(0o755)

    try:
        subprocess.Popen([
            "osascript",
            "-e", 'tell app "Terminal" to activate',
            "-e", f'tell app "Terminal" to do script "bash {script_path}"',
        ])
        ok("Monitor opened in new Terminal window")
        return {"ok": True}
    except Exception as e:
        fail(f"Failed to open monitor: {e}")
        return {"ok": False, "error": str(e)}


# ── Native See app ────────────────────────────────────────────────────────────

def start_see(dry: bool = False) -> dict:
    """Build and launch the native SwiftUI See app."""
    if not SEE_DIR.exists():
        warn(f"See app not found at {SEE_DIR}")
        return {"ok": False, "error": "not found"}

    if dry:
        print(f"  (dry) Would build and launch See app from {SEE_DIR}")
        return {"ok": True}

    print("  Building See app (swift build -c release)...")
    try:
        result = subprocess.run(
            ["swift", "build", "-c", "release", "--package-path", str(SEE_DIR)],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            fail(f"See app build failed (code {result.returncode})")
            # Show last few lines of stderr
            for line in result.stderr.strip().split("\n")[-3:]:
                print(f"    {line}")
            return {"ok": False, "error": "build failed"}

        # Find the built binary
        binary = SEE_DIR / ".build" / "release" / "See"
        if not binary.exists():
            # Try to find it
            try:
                find_result = subprocess.check_output(
                    ["find", str(SEE_DIR / ".build" / "release"), "-name", "See", "-type", "f"],
                    text=True, timeout=10,
                ).strip()
                if find_result:
                    binary = Path(find_result.split("\n")[0])
            except Exception:
                pass

        if binary.exists():
            subprocess.Popen(["open", str(binary)])
            ok(f"See app launched — {binary.name}")
            return {"ok": True}
        else:
            warn("See app built but binary not found")
            return {"ok": False, "error": "binary not found"}

    except subprocess.TimeoutExpired:
        fail("See app build timed out (120s)")
        return {"ok": False, "error": "timeout"}
    except Exception as e:
        fail(f"See app error: {e}")
        return {"ok": False, "error": str(e)}


# ── Ollama report ─────────────────────────────────────────────────────────────

def report_ollama(dry: bool = False) -> dict:
    """Report Ollama loaded models and VRAM usage."""
    if dry:
        print("  (dry) Would report Ollama status")
        return {"running": False}

    try:
        req = urllib.request.Request(OLLAMA_URL, method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            models = data.get("models", [])
            if models:
                for m in models:
                    name = m.get("name", "?")
                    size = m.get("size", 0)
                    size_gb = size / (1024 ** 3) if size else 0
                    vram = m.get("size_vram", 0)
                    vram_gb = vram / (1024 ** 3) if vram else 0
                    ok(f"{name} — {size_gb:.1f}GB total, {vram_gb:.1f}GB VRAM")
            else:
                ok("Ollama running — no models loaded")
            return {"running": True, "models": models}
    except Exception:
        warn("Ollama not available")
        return {"running": False}
