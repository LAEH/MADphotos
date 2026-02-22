"""Phase 1: Pre-flight safety checks — processes, ports, locks, auth."""
from __future__ import annotations

import subprocess
from . import (
    BLOCKING_PROCESSES, NON_BLOCKING_PROCESSES, PORT_MAP,
)


def get_processes() -> list[dict]:
    """List running MADphotos/ollama processes (reuses monitor.py pattern)."""
    try:
        out = subprocess.check_output(["ps", "aux"], text=True, timeout=5)
    except Exception:
        return []
    procs = []
    for line in out.strip().split("\n")[1:]:
        parts = line.split(None, 10)
        if len(parts) < 11:
            continue
        pid, cpu, mem, cmd = parts[1], parts[2], parts[3], parts[10]
        if "MADphotos" not in cmd and "ollama" not in cmd.lower():
            continue
        if "grep" in cmd or "preflight" in cmd:
            continue
        procs.append({"pid": pid, "cpu": cpu, "mem": mem, "cmd": cmd})
    return procs


def get_ports() -> dict[str, str]:
    """Map listening ports to process names."""
    try:
        out = subprocess.check_output(
            ["lsof", "-iTCP", "-sTCP:LISTEN", "-P", "-n"],
            text=True, timeout=5, stderr=subprocess.DEVNULL,
        )
    except Exception:
        return {}
    ports = {}
    for line in out.strip().split("\n")[1:]:
        parts = line.split()
        if len(parts) < 9:
            continue
        name, addr = parts[0], parts[8]
        port = addr.split(":")[-1] if ":" in addr else ""
        if port in PORT_MAP and port not in ports:
            ports[port] = f"{name} ({PORT_MAP[port]})"
    return ports


def classify_processes(procs: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split processes into blocking (DB writers) and non-blocking (read-only)."""
    blocking, non_blocking = [], []
    for p in procs:
        cmd_lower = p["cmd"].lower()
        if any(bp in cmd_lower for bp in BLOCKING_PROCESSES):
            blocking.append(p)
        elif any(nb in cmd_lower for nb in NON_BLOCKING_PROCESSES):
            non_blocking.append(p)
    return blocking, non_blocking


def check_gcp_auth() -> tuple[bool, str]:
    """Check GCP application-default credentials."""
    try:
        result = subprocess.run(
            ["gcloud", "auth", "application-default", "print-access-token"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            return True, "GCP auth OK"
        return False, f"GCP auth failed: {result.stderr.strip()[:100]}"
    except FileNotFoundError:
        return False, "gcloud CLI not found"
    except Exception as e:
        return False, f"GCP auth error: {e}"


def check_firebase_auth() -> tuple[bool, str]:
    """Check Firebase CLI auth."""
    try:
        result = subprocess.run(
            ["firebase", "projects:list", "--json"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            return True, "Firebase auth OK"
        return False, f"Firebase auth failed: {result.stderr.strip()[:100]}"
    except FileNotFoundError:
        return False, "firebase CLI not found"
    except Exception as e:
        return False, f"Firebase auth error: {e}"


def run(dry: bool = False) -> dict:
    """Run all pre-flight checks. Returns structured report."""
    procs = get_processes()
    blocking, non_blocking = classify_processes(procs)
    ports = get_ports()
    gcp_ok, gcp_msg = check_gcp_auth()
    fb_ok, fb_msg = check_firebase_auth()

    safe = len(blocking) == 0 and gcp_ok and fb_ok

    report = {
        "safe_to_deploy": safe,
        "blocking": blocking,
        "non_blocking": non_blocking,
        "ports": ports,
        "gcp_auth": {"ok": gcp_ok, "message": gcp_msg},
        "firebase_auth": {"ok": fb_ok, "message": fb_msg},
    }

    # Print report
    print("\n  PROCESSES")
    if blocking:
        for p in blocking:
            cmd_short = p["cmd"].split("/")[-1][:60]
            print(f"    BLOCKING  pid={p['pid']}  {cmd_short}")
    else:
        print("    No blocking processes")
    if non_blocking:
        for p in non_blocking:
            cmd_short = p["cmd"].split("/")[-1][:60]
            print(f"    ok        pid={p['pid']}  {cmd_short}")

    print("\n  PORTS")
    if ports:
        for port, desc in sorted(ports.items()):
            print(f"    :{port}  {desc}")
    else:
        print("    No MADphotos ports in use")

    print("\n  AUTH")
    print(f"    GCP:      {'OK' if gcp_ok else 'FAIL'} — {gcp_msg}")
    print(f"    Firebase: {'OK' if fb_ok else 'FAIL'} — {fb_msg}")

    print(f"\n  VERDICT: {'SAFE to deploy' if safe else 'NOT safe — resolve blockers first'}")

    return report
