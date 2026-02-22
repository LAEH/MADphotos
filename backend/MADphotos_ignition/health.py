"""Phase 3: Health checks — HTTP GET each server with retries."""
from __future__ import annotations

import time
import urllib.request

from . import CORE_SERVERS


# ── ANSI ──────────────────────────────────────────────────────────────────────

R = "\033[0m"
B = "\033[1m"
GN = "\033[32m"
YL = "\033[33m"
RD = "\033[31m"
CY = "\033[36m"


def ok(msg: str) -> None:
    print(f"  {GN}✓{R} {msg}")


def fail(msg: str) -> None:
    print(f"  {RD}✗{R} {msg}")


# ── Health check ──────────────────────────────────────────────────────────────

def check_url(url: str, retries: int = 10, delay: float = 1.5) -> dict:
    """HTTP GET with retry. Returns {ok, status, attempts, elapsed_s}."""
    start = time.time()
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                elapsed = time.time() - start
                return {
                    "ok": True,
                    "status": resp.status,
                    "attempts": attempt,
                    "elapsed_s": round(elapsed, 1),
                }
        except Exception as e:
            last_error = str(e)
            if attempt < retries:
                time.sleep(delay)

    elapsed = time.time() - start
    return {
        "ok": False,
        "error": last_error,
        "attempts": retries,
        "elapsed_s": round(elapsed, 1),
    }


# ── Orchestrator ──────────────────────────────────────────────────────────────

def run(dry: bool = False) -> dict:
    """Check all core server health URLs. Returns results dict."""
    if dry:
        for server in CORE_SERVERS:
            print(f"  (dry) Would check {server['health_url']}")
        return {"ok": True, "results": {}}

    results = {}
    all_ok = True

    for server in CORE_SERVERS:
        url = server["health_url"]
        result = check_url(url)
        results[server["name"]] = result

        if result["ok"]:
            ok(f"{server['label']} — {result['status']} ({result['attempts']} "
               f"attempt{'s' if result['attempts'] != 1 else ''}, "
               f"{result['elapsed_s']}s)")
        else:
            fail(f"{server['label']} — {result['error']} "
                 f"(after {result['attempts']} attempts, {result['elapsed_s']}s)")
            all_ok = False

    # Summary with ready URLs
    if all_ok:
        print(f"\n  {B}Ready:{R}")
        print(f"  {CY}Show:{R}    http://localhost:5173")
        print(f"  {CY}System:{R}  http://localhost:5174")
        print(f"  {CY}API:{R}     http://localhost:3000/system")

    return {"ok": all_ok, "results": results}
