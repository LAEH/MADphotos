#!/usr/bin/env python3
"""16-line terminal monitor for Gemma analysis."""
from __future__ import annotations

import json, os, signal, sqlite3, sys, time
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DB = ROOT / "images" / "mad_photos.db"
PICKS = ROOT / "frontend" / "show" / "public" / "data" / "picks.json"

R = "\033[0m"; B = "\033[1m"; D = "\033[2m"; I = "\033[3m"
W = "\033[97m"; GN = "\033[32m"; YL = "\033[33m"; CY = "\033[36m"
TL = "\033[38;5;43m"; SK = "\033[38;5;117m"; LV = "\033[38;5;183m"
HC = "\033[?25l"; SC = "\033[?25h"; CL = "\033[2K"; HM = "\033[H"
SP = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
BG = ["\033[38;5;24m","\033[38;5;30m","\033[38;5;36m","\033[38;5;42m",
      "\033[38;5;43m","\033[38;5;49m","\033[38;5;85m","\033[38;5;121m"]

_REQ = ["visual_weight","energy_direction","archetype","color_temp",
        "cartoon_style","story_silly","story_poetic","story_surrealist",
        "story_noir","story_romantic","print_worthy",
        "setting","time_of_day","vibes","faces_count"]
_INT = {"visual_weight","print_worthy","faces_count"}

def _wd():
    return " AND ".join(
        f"{f} IS NOT NULL" if f in _INT else f"({f} IS NOT NULL AND {f} != '')"
        for f in _REQ)

def load_picks():
    try:
        d = json.loads(PICKS.read_text())
        return len(list(dict.fromkeys(
            [u for u in d["portrait"] if "_" not in u]+
            [u for u in d["landscape"] if "_" not in u])))
    except: return 0

def nd(c):
    try: return c.execute(f"SELECT COUNT(*) FROM gemma_analysis WHERE {_wd()}").fetchone()[0]
    except: return 0

def dbrate(c):
    try:
        rows = c.execute(
            f"SELECT processed_at FROM gemma_analysis WHERE {_wd()} "
            "ORDER BY processed_at DESC LIMIT 20").fetchall()
        ts = []
        for r in rows:
            if r[0]:
                try: ts.append(datetime.fromisoformat(r[0].replace("Z","+00:00")).timestamp())
                except: pass
        if len(ts)>=2:
            span = ts[0]-ts[-1]
            if span>0: return (len(ts)-1)/span
    except: pass
    return 0.0

def get_latest(c):
    try:
        r = c.execute(
            "SELECT subject, mood, description, tags, processed_at "
            "FROM gemma_analysis ORDER BY processed_at DESC LIMIT 1").fetchone()
        return r if r else None
    except: return None

def get_recent(c):
    try:
        return c.execute(
            "SELECT subject, mood, processed_at "
            "FROM gemma_analysis ORDER BY processed_at DESC LIMIT 4 OFFSET 1").fetchall()
    except: return []

def pb(pct,w):
    f=int(w*pct/100); n=len(BG)
    return "".join(
        f"{BG[int(i/max(w-1,1)*(n-1))]}━{R}" if i<f else f"\033[38;5;236m╌{R}"
        for i in range(w))

def fd(s):
    if s<=0: return "done"
    h,s=divmod(int(s),3600); m,s=divmod(s,60)
    return f"{h}h{m:02d}m" if h else (f"{m}m{s:02d}s" if m else f"{s}s")

def fa(iso):
    if not iso: return ""
    try:
        t=datetime.fromisoformat(iso.replace("Z","+00:00"))
        d=max(0,(datetime.now(timezone.utc)-t).total_seconds())
        return f"{int(d)}s" if d<60 else (f"{int(d/60)}m" if d<3600 else f"{int(d/3600)}h")
    except: return ""

def T(s,n): return s[:n-1]+"…" if len(s)>n else s

def monitor():
    total=load_picks()
    if not total: print(f"No picks at {PICKS}"); return

    conn=sqlite3.connect(str(DB))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA query_only=ON")

    hist: deque[tuple[float,int]] = deque(maxlen=120)
    sn=nd(conn); st=time.time(); tick=0

    sys.stdout.write(HC+"\033[2J"); sys.stdout.flush()

    def die(*_):
        sys.stdout.write(SC+"\n"); sys.stdout.flush()
        conn.close(); sys.exit(0)
    signal.signal(signal.SIGINT,die)
    signal.signal(signal.SIGTERM,die)

    try:
        while True:
            done=nd(conn); now=time.time(); hist.append((now,done))
            pct=done*100/total if total else 0; rem=total-done
            cols=min(os.get_terminal_size().columns-4,58) if sys.stdout.isatty() else 56

            rate=0.0
            if len(hist)>=2:
                cut=now-60
                ol=[(t,c) for t,c in hist if t<=cut]
                rt,rc=(ol[-1] if ol else hist[0])
                dt,dc=now-rt,done-rc
                if dt>5 and dc>0: rate=dc/dt
            if rate==0: rate=dbrate(conn)

            eta=rem/rate if rate>0 else 0
            pi=1/rate if rate>0 else 0
            sess=done-sn
            spin=SP[tick%len(SP)]; tick+=1
            lt=get_latest(conn); rc=get_recent(conn)
            sep=f"{CL}  {D}{'─'*cols}{R}"

            L=[]
            # 1: header
            L.append(f"{CL}  {GN}{spin}{R} {B}{W}Gemma{R}  {B}{W}{pct:5.1f}%{R}  {D}{datetime.now().strftime('%H:%M:%S')}{R}")
            # 2: bar
            L.append(f"{CL}  {pb(pct,cols)}")
            # 3: counts + rate
            if rate>0:
                ipm=rate*60; rs=f"{ipm:.1f}/min" if ipm>=1 else f"{rate*3600:.0f}/hr"
                L.append(f"{CL}  {GN}{done:,}{R}{D}/{R}{W}{total:,}{R}  {YL}{rem:,}{R}{D} left{R}  {TL}{pi:.0f}s{R}{D}/img{R}  {TL}{rs}{R}")
            else:
                L.append(f"{CL}  {GN}{done:,}{R}{D}/{R}{W}{total:,}{R}  {YL}{rem:,}{R}{D} left{R}  {D}…{R}")
            # 4: ETA
            if rate>0:
                fin=datetime.now()+timedelta(seconds=eta)
                fs=f"{fin.strftime('%H:%M')} tmrw" if fin.date()>datetime.now().date() else fin.strftime("%H:%M")
                ss=f"  {D}+{sess}{R}" if sess>0 else ""
                L.append(f"{CL}  {CY}{fd(eta)}{R}{D} left{R}  {D}done{R} {CY}{fs}{R}{ss}")
            else:
                L.append(f"{CL}  {D}estimating…{R}")
            # 5: sep
            L.append(sep)
            # 6-9: latest
            if lt:
                L.append(f"{CL}  {B}{W}{T(lt[0] or '?',cols-6)}{R}  {D}{fa(lt[4])}{R}")
                L.append(f"{CL}  {LV}{T(lt[1] or '',cols)}{R}" if lt[1] else f"{CL}")
                L.append(f"{CL}  {D}{I}{T(lt[2] or '',cols)}{R}" if lt[2] else f"{CL}")
                if lt[3]:
                    tags=[t.strip() for t in lt[3].split(",")[:6] if t.strip()]
                    L.append(f"{CL}  {f' {D}·{R} '.join(f'{SK}{t}{R}' for t in tags)}")
                else: L.append(f"{CL}")
            else:
                L.extend([f"{CL}  {D}waiting…{R}",f"{CL}",f"{CL}",f"{CL}"])
            # 10: sep
            L.append(sep)
            # 11-14: recent
            for r in rc[:4]:
                L.append(f"{CL}  {D}·{R} {W}{T(r[0] or '',30):<32}{R}{LV}{T(r[1] or '',18):<20}{R}{D}{fa(r[2]):>4}{R}")
            for _ in range(4-len(rc[:4])): L.append(f"{CL}")
            # 15: sep
            L.append(sep)
            # 16: footer
            L.append(f"{CL}  {D}ctrl+c to close{R}")

            sys.stdout.write(HM+"\n".join(L)); sys.stdout.flush()
            if rem<=0: break
            time.sleep(2)
    finally:
        sys.stdout.write(SC+"\n"); sys.stdout.flush(); conn.close()

if __name__=="__main__": monitor()
