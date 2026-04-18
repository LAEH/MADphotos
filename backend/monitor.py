#!/usr/bin/env python3
"""MADphotos — compact two-column terminal monitor."""
from __future__ import annotations

import json, os, signal, sqlite3, subprocess, sys, time, urllib.request
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "images" / "mad_photos.db"
PICKS = ROOT / "frontend" / "show" / "public" / "data" / "picks.json"

R  = "\033[0m"; B  = "\033[1m"; W  = "\033[97m"
GN = "\033[32m"; YL = "\033[33m"; CY = "\033[36m"
RD = "\033[31m"; MG = "\033[35m"; BL = "\033[34m"
DM = "\033[38;5;245m"
TL = "\033[38;5;43m"; SK = "\033[38;5;117m"; LV = "\033[38;5;183m"
OR = "\033[38;5;208m"
HC = "\033[?25l"; SC = "\033[?25h"; CL = "\033[2K"; HM = "\033[H"
SP = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
BG = ["\033[38;5;24m","\033[38;5;30m","\033[38;5;36m","\033[38;5;42m",
      "\033[38;5;43m","\033[38;5;49m","\033[38;5;85m","\033[38;5;121m"]

_REQ = ["visual_weight","energy_direction","archetype","color_temp",
        "cartoon_style","story_silly","story_poetic","story_surrealist",
        "story_noir","story_romantic","print_worthy",
        "setting","time_of_day","vibes","faces_count"]
_INT = {"visual_weight","print_worthy","faces_count"}

HALF = 52  # each column width


def _wd():
    return " AND ".join(
        f"{f} IS NOT NULL" if f in _INT else f"({f} IS NOT NULL AND {f} != '')"
        for f in _REQ)

def T(s, n): return s[:n-1] + "…" if len(s) > n else s

def pb(pct, w):
    f = int(w * pct / 100); n = len(BG)
    return "".join(
        f"{BG[int(i/max(w-1,1)*(n-1))]}━{R}" if i < f else f"\033[38;5;236m╌{R}"
        for i in range(w))

def fd(s):
    if s <= 0: return "done"
    h, s = divmod(int(s), 3600); m, s = divmod(s, 60)
    return f"{h}h{m:02d}m" if h else (f"{m}m{s:02d}s" if m else f"{s}s")

def slen(s):
    """Visible length of string (strip ANSI)."""
    import re
    return len(re.sub(r'\033\[[^m]*m', '', s))

def pad(s, w):
    """Pad string to visible width w."""
    return s + " " * max(0, w - slen(s))


# ── Data fetchers ─────────────────────────────────────────────────────────

def get_processes():
    try:
        out = subprocess.check_output(["ps", "aux"], text=True, timeout=5)
    except Exception:
        return []
    procs = []
    for line in out.strip().split("\n")[1:]:
        parts = line.split(None, 10)
        if len(parts) < 11: continue
        pid, cpu, mem, cmd = parts[1], parts[2], parts[3], parts[10]
        if "MADphotos" not in cmd and "ollama" not in cmd.lower(): continue
        if "grep" in cmd or "monitor.py" in cmd: continue
        procs.append({"pid": pid, "cpu": cpu, "mem": mem, "cmd": cmd})
    return procs

def cat_proc(cmd):
    cl = cmd.lower()
    if "run_gemma_forever" in cl:   return "Gemma forever", TL
    if "run_gemma_analysis" in cl:  return "Gemma analysis", TL
    if "gemma_monitor" in cl:       return "Gemma monitor", DM
    if "serve_show" in cl:          return "Show server", BL
    if "dashboard.py" in cl:        return "Dashboard", BL
    if "imagen.py" in cl:           return "Imagen", MG
    if "firestore_sync" in cl:      return "Firestore sync", CY
    if "export_gallery" in cl:      return "Export", CY
    if "signals" in cl or "pipeline" in cl: return "Signals", YL
    if "render.py" in cl or "enhance" in cl: return "Render", OR
    if "vite" in cl and "system" in cl:  return "System vite", SK
    if "vite" in cl and "show" in cl:    return "Show vite", SK
    if "vite" in cl:                return "Vite", SK
    if "ollama" in cl and "runner" in cl:   return "Ollama runner", GN
    if "ollama" in cl and "serve" in cl:    return "Ollama serve", GN
    if "server.py" in cl:           return "System srv", BL
    return "Process", DM

def get_ports():
    try:
        out = subprocess.check_output(
            ["lsof", "-iTCP", "-sTCP:LISTEN", "-P", "-n"],
            text=True, timeout=5, stderr=subprocess.DEVNULL)
    except Exception:
        return {}
    ports = {}
    for line in out.strip().split("\n")[1:]:
        parts = line.split()
        if len(parts) < 9: continue
        name, addr = parts[0], parts[8]
        port = addr.split(":")[-1] if ":" in addr else ""
        if port in ports: continue
        if name == "ollama":            ports[port] = ("Ollama", GN)
        elif name in ("Python","python3"):
            if port == "3000":          ports[port] = ("Show srv", BL)
            elif port == "8080":        ports[port] = ("Dashboard", BL)
        elif name == "node":
            if port == "5173":          ports[port] = ("System vite", SK)
            elif port == "5174":        ports[port] = ("Show vite", SK)
    return ports

def get_ollama():
    try:
        resp = urllib.request.urlopen(
            urllib.request.Request("http://localhost:11434/api/ps"), timeout=3)
        return json.loads(resp.read()).get("models", [])
    except Exception:
        return None

def load_picks():
    try:
        d = json.loads(PICKS.read_text())
        return len(list(dict.fromkeys(
            [u for u in d["portrait"] if "_" not in u] +
            [u for u in d["landscape"] if "_" not in u])))
    except Exception: return 0

def gemma_done(c):
    try: return c.execute(f"SELECT COUNT(*) FROM gemma_analysis WHERE {_wd()}").fetchone()[0]
    except Exception: return 0

def gemma_rate(c):
    try:
        rows = c.execute(
            f"SELECT processed_at FROM gemma_analysis WHERE {_wd()} "
            "ORDER BY processed_at DESC LIMIT 20").fetchall()
        ts = []
        for r in rows:
            if r[0]:
                try: ts.append(datetime.fromisoformat(r[0].replace("Z","+00:00")).timestamp())
                except Exception: pass
        if len(ts) >= 2:
            span = ts[0] - ts[-1]
            if span > 0: return (len(ts)-1) / span
    except Exception: pass
    return 0.0

def gemma_latest(c):
    try: return c.execute("SELECT subject, mood FROM gemma_analysis ORDER BY processed_at DESC LIMIT 1").fetchone()
    except Exception: return None

def db_stats(c):
    s = {}
    for t, k in [("images","imgs"),("gemma_analysis","gemma"),("gemini_analysis","gemini")]:
        try: s[k] = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except Exception: s[k] = 0
    try: s["vars"] = c.execute("SELECT COUNT(*) FROM ai_variants WHERE generation_status='success'").fetchone()[0]
    except Exception: s["vars"] = 0
    return s


# ── Main ──────────────────────────────────────────────────────────────────

def monitor():
    total = load_picks()
    try:
        conn = sqlite3.connect(str(DB), timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA query_only=ON")
    except Exception: conn = None

    hist = deque(maxlen=120)
    s0 = gemma_done(conn) if conn else 0
    tick = 0

    sys.stdout.write(HC + "\033[2J"); sys.stdout.flush()

    def die(*_):
        sys.stdout.write(SC + "\n"); sys.stdout.flush()
        if conn: conn.close()
        sys.exit(0)
    signal.signal(signal.SIGINT, die)
    signal.signal(signal.SIGTERM, die)

    full = HALF * 2 + 3  # total width with separator

    try:
        while True:
            now = time.time()
            spin = SP[tick % len(SP)]; tick += 1
            sep_full = f"{CL} {DM}{'─' * full}{R}"
            sep_h = DM + "─" * HALF + R
            L = []

            # ── Header ─────────────────────────────────────────────
            ts = datetime.now().strftime("%H:%M:%S")
            L.append(f"{CL}")
            L.append(f"{CL}  {GN}{spin}{R} {B}{W}MADphotos{R}  {DM}{ts}{R}")
            L.append(sep_full)

            # ── Two columns: Left = Servers + Ollama, Right = Processes ──
            # Build left column lines
            left = []
            ports = get_ports()
            mp = {p: v for p, v in ports.items() if p in ("3000","5173","5174","8080","11434")}
            if mp:
                for port in sorted(mp):
                    lbl, color = mp[port]
                    left.append(f" {color}●{R} {DM}:{port:<6}{R}{W}{lbl}{R}")
            else:
                left.append(f" {DM}no servers{R}")

            # Ollama in left col
            oll = get_ollama()
            if oll is not None:
                if oll:
                    for m in oll:
                        gb = m.get("size_vram", 0) / 1e9
                        left.append(f" {GN}●{R} {W}{T(m.get('name','?'), 20)}{R} {DM}{gb:.0f}GB{R}")
                else:
                    left.append(f" {YL}●{R} {W}Ollama{R} {YL}idle{R}")
            else:
                left.append(f" {RD}●{R} {W}Ollama{R} {RD}down{R}")

            # Build right column lines
            right = []
            procs = get_processes()
            for p in procs:
                lbl, color = cat_proc(p["cmd"])
                if lbl in ("Ollama serve", "Gemma monitor", "Node"): continue
                cpu = float(p["cpu"]); mem = float(p["mem"])
                cs = f"{cpu:.0f}%" if cpu >= 0.5 else "–"
                ms = f"{mem:.1f}%" if mem >= 0.1 else "–"
                right.append(f" {color}●{R} {W}{lbl:<18}{R} {DM}{cs:>4} {ms:>5}{R}")
            if not right:
                right.append(f" {DM}no processes{R}")

            # Merge columns side by side
            maxrows = max(len(left), len(right))
            for i in range(maxrows):
                lc = left[i] if i < len(left) else ""
                rc = right[i] if i < len(right) else ""
                L.append(f"{CL}{pad(lc, HALF)} {DM}│{R} {rc}")

            L.append(sep_full)

            # ── Gemma progress (full width) ────────────────────────
            if conn and total:
                done = gemma_done(conn)
                hist.append((now, done))
                pct = done * 100 / total; rem = total - done

                rate = 0.0
                if len(hist) >= 2:
                    cut = now - 60
                    ol = [(t, c) for t, c in hist if t <= cut]
                    rt, rc = (ol[-1] if ol else hist[0])
                    dt, dc = now - rt, done - rc
                    if dt > 5 and dc > 0: rate = dc / dt
                if rate == 0: rate = gemma_rate(conn)

                eta = rem / rate if rate > 0 else 0
                pi = 1 / rate if rate > 0 else 0
                sess = done - s0

                bar_w = min(full - 2, 100)
                L.append(
                    f"{CL}  {B}{W}Gemma{R} {B}{W}{pct:5.1f}%{R}"
                    f"  {GN}{done:,}{R} {DM}/{R} {W}{total:,}{R}"
                    f"  {pb(pct, bar_w - 30)}"
                )

                if rate > 0:
                    ipm = rate * 60
                    rs = f"{ipm:.1f}/min" if ipm >= 1 else f"{rate*3600:.0f}/hr"
                    fin = datetime.now() + timedelta(seconds=eta)
                    fs = f"{fin.strftime('%H:%M')} tmrw" if fin.date() > datetime.now().date() else fin.strftime("%H:%M")
                    ss = f"  {DM}+{sess}{R}" if sess > 0 else ""
                    L.append(
                        f"{CL}  {YL}{rem:,}{R} {DM}left{R}"
                        f"  {TL}{pi:.0f}s{R}{DM}/img{R}"
                        f"  {TL}{rs}{R}"
                        f"  {CY}{fd(eta)}{R} {DM}→{R} {CY}{fs}{R}{ss}"
                    )
                    lat = gemma_latest(conn)
                    if lat:
                        L.append(f"{CL}  {DM}{T(lat[0] or '', 40)}{R}  {LV}{T(lat[1] or '', 24)}{R}")
                elif done >= total:
                    L.append(f"{CL}  {GN}{B}Complete!{R}")
                else:
                    L.append(f"{CL}  {YL}{rem:,}{R} {DM}left — estimating…{R}")

            L.append(sep_full)

            # ── DB stats (compact single line) ─────────────────────
            if conn:
                s = db_stats(conn)
                L.append(
                    f"{CL}  {DM}DB{R}"
                    f"  {W}{s['imgs']:,}{R} {DM}imgs{R}"
                    f"  {W}{s['gemma']:,}{R} {DM}gemma{R}"
                    f"  {W}{s['gemini']:,}{R} {DM}gemini{R}"
                    f"  {W}{s['vars']}{R} {DM}variants{R}"
                    f"  {DM}│  ctrl+c to close{R}"
                )
            L.append(f"{CL}")

            sys.stdout.write(HM + "\n".join(L)); sys.stdout.flush()
            time.sleep(3)
    finally:
        sys.stdout.write(SC + "\n"); sys.stdout.flush()
        if conn: conn.close()


if __name__ == "__main__":
    monitor()
