#!/usr/bin/env python3
"""Local web viewer for Gemma picks analysis progress.

Shows each processed photo alongside its Gemma 3 analysis.
Auto-refreshes while processing is running.

Usage:
  python3 backend/gemma_viewer.py              # http://localhost:8787
  python3 backend/gemma_viewer.py --port 9000  # custom port
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import sqlite3
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "images" / "mad_photos.db"
PICKS_JSON = PROJECT_ROOT / "frontend" / "show" / "data" / "picks.json"

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Gemma Picks</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg: #0a0a0a;
    --surface: #141414;
    --border: #222;
    --text: #e0e0e0;
    --text-dim: #777;
    --accent: #4f8cff;
    --accent-dim: rgba(79, 140, 255, 0.15);
    --green: #34d399;
    --green-dim: rgba(52, 211, 153, 0.15);
  }

  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
  }

  /* ── Header ── */
  header {
    position: sticky;
    top: 0;
    z-index: 100;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 16px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 20px;
    backdrop-filter: blur(12px);
  }

  .title {
    font-size: 15px;
    font-weight: 600;
    letter-spacing: 0.02em;
    white-space: nowrap;
  }

  .progress-wrap {
    flex: 1;
    max-width: 400px;
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .progress-bar {
    flex: 1;
    height: 4px;
    background: var(--border);
    border-radius: 2px;
    overflow: hidden;
  }

  .progress-fill {
    height: 100%;
    background: var(--accent);
    border-radius: 2px;
    transition: width 0.6s ease;
  }

  .progress-fill.done { background: var(--green); }

  .stats {
    font-size: 13px;
    color: var(--text-dim);
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
  }

  .stats strong { color: var(--text); font-weight: 600; }

  .live-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--green);
    animation: pulse 2s infinite;
    flex-shrink: 0;
  }

  .live-dot.idle { background: var(--text-dim); animation: none; }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
  }

  /* ── Cards ── */
  main {
    max-width: 1200px;
    margin: 0 auto;
    padding: 24px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .card {
    display: grid;
    grid-template-columns: 280px 1fr;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
    transition: border-color 0.2s;
  }

  .card:hover { border-color: #333; }

  .card-img {
    position: relative;
    background: #000;
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 280px;
  }

  .card-img img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }

  .card-img .uuid {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    padding: 4px 8px;
    font-size: 10px;
    font-family: 'SF Mono', 'Fira Code', monospace;
    color: rgba(255,255,255,0.5);
    background: rgba(0,0,0,0.6);
    text-align: center;
    letter-spacing: 0.03em;
  }

  .card-body {
    padding: 20px 24px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    overflow: hidden;
  }

  .description {
    font-size: 15px;
    line-height: 1.6;
    color: var(--text);
  }

  .fields {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px 20px;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .field-label {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-dim);
    font-weight: 500;
  }

  .field-value {
    font-size: 13px;
    color: var(--text);
    line-height: 1.4;
  }

  .tags {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-top: 4px;
  }

  .tag {
    padding: 2px 8px;
    font-size: 11px;
    background: var(--accent-dim);
    color: var(--accent);
    border-radius: 4px;
    white-space: nowrap;
  }

  .badge-print {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 500;
    border-radius: 4px;
    width: fit-content;
  }

  .badge-print.yes { background: var(--green-dim); color: var(--green); }
  .badge-print.no { background: rgba(255,255,255,0.05); color: var(--text-dim); }

  .empty {
    text-align: center;
    padding: 80px 20px;
    color: var(--text-dim);
    font-size: 14px;
  }

  /* ── Responsive ── */
  @media (max-width: 700px) {
    .card {
      grid-template-columns: 1fr;
    }
    .card-img { min-height: 200px; max-height: 260px; }
    .fields { grid-template-columns: 1fr; }
    header { flex-wrap: wrap; }
  }
</style>
</head>
<body>
  <header>
    <div class="title">Gemma Picks</div>
    <div class="progress-wrap">
      <div class="progress-bar"><div class="progress-fill" id="pbar"></div></div>
      <span class="stats" id="stats">loading...</span>
    </div>
    <div class="live-dot" id="dot"></div>
  </header>
  <main id="cards"></main>

<script>
const POLL_MS = 3000;
let lastCount = 0;
let idleStreak = 0;

async function poll() {
  try {
    const res = await fetch('/api/status');
    const d = await res.json();

    // Progress
    const pct = d.total > 0 ? (d.processed / d.total * 100) : 0;
    const bar = document.getElementById('pbar');
    bar.style.width = pct.toFixed(1) + '%';

    const done = d.processed === d.total && d.total > 0;
    bar.classList.toggle('done', done);

    document.getElementById('stats').innerHTML =
      `<strong>${d.processed}</strong> / ${d.total}` +
      (d.errors > 0 ? ` · ${d.errors} err` : '');

    // Live indicator
    const dot = document.getElementById('dot');
    if (d.processed !== lastCount) {
      idleStreak = 0;
      lastCount = d.processed;
    } else {
      idleStreak++;
    }
    dot.classList.toggle('idle', idleStreak > 3 || done);

    // Cards — fetch full results
    if (d.processed > 0) {
      const rr = await fetch('/api/results');
      const results = await rr.json();
      renderCards(results);
    } else {
      document.getElementById('cards').innerHTML =
        '<div class="empty">Waiting for Gemma to process images...</div>';
    }
  } catch (e) {
    console.error('Poll error:', e);
  }
}

function renderCards(results) {
  const main = document.getElementById('cards');
  // Newest first
  const items = results.sort((a, b) => b.processed_at.localeCompare(a.processed_at));
  main.innerHTML = items.map(r => {
    const g = r.gemma;
    const tags = (g.tags || []).map(t => `<span class="tag">${esc(t)}</span>`).join('');
    const pw = g.print_worthy;
    const pwClass = pw === true ? 'yes' : 'no';
    const pwLabel = pw === true ? 'Print-worthy' : 'Not print-worthy';

    return `
    <div class="card">
      <div class="card-img">
        <img src="/images/${r.uuid}" loading="lazy" alt="">
        <div class="uuid">${r.uuid}</div>
      </div>
      <div class="card-body">
        <div class="description">${esc(g.description || g.raw || '')}</div>
        <div class="fields">
          ${field('Subject', g.subject)}
          ${field('Mood', g.mood)}
          ${field('Story', g.story)}
          ${field('Lighting', g.lighting)}
          ${field('Composition', g.composition)}
          ${field('Colors', g.colors)}
          ${field('Texture', g.texture)}
          ${field('Technical', g.technical)}
          ${field('Strength', g.strength)}
        </div>
        ${tags ? `<div class="tags">${tags}</div>` : ''}
        <div class="badge-print ${pwClass}">${pwLabel}</div>
      </div>
    </div>`;
  }).join('');
}

function field(label, val) {
  if (!val) return '';
  return `<div class="field"><span class="field-label">${label}</span><span class="field-value">${esc(val)}</span></div>`;
}

function esc(s) {
  if (!s) return '';
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

poll();
setInterval(poll, POLL_MS);
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "":
            self._html()
        elif path == "/api/status":
            self._status()
        elif path == "/api/results":
            self._results()
        elif path.startswith("/images/"):
            self._image(path)
        else:
            self._404()

    def _html(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML.encode())

    def _json_response(self, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _status(self):
        conn = sqlite3.connect(str(DB_PATH))
        # Total picks
        try:
            picks = json.loads(PICKS_JSON.read_text())
            total = len(set(picks.get("portrait", []) + picks.get("landscape", [])))
        except Exception:
            total = 0

        # Processed
        try:
            processed = conn.execute("SELECT COUNT(*) FROM gemma_picks").fetchone()[0]
        except sqlite3.OperationalError:
            processed = 0

        # Errors: we don't track these in DB, so just report 0
        conn.close()
        self._json_response({"total": total, "processed": processed, "errors": 0})

    def _results(self):
        conn = sqlite3.connect(str(DB_PATH))
        try:
            rows = conn.execute(
                "SELECT uuid, gemma_json, processed_at FROM gemma_picks ORDER BY processed_at DESC"
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
        conn.close()

        results = []
        for uuid, gemma_json, processed_at in rows:
            try:
                gemma = json.loads(gemma_json)
            except (json.JSONDecodeError, TypeError):
                gemma = {"raw": gemma_json}
            results.append({"uuid": uuid, "gemma": gemma, "processed_at": processed_at or ""})

        self._json_response(results)

    def _image(self, path):
        uuid = path.split("/images/", 1)[-1].strip("/")
        if not uuid or "/" in uuid:
            self._404()
            return

        conn = sqlite3.connect(str(DB_PATH))
        row = conn.execute(
            "SELECT local_path FROM tiers WHERE image_uuid = ? AND tier_name = 'mobile' AND format = 'jpeg' LIMIT 1",
            (uuid,),
        ).fetchone()
        conn.close()

        if not row:
            self._404()
            return

        img_path = Path(row[0])
        if not img_path.exists():
            self._404()
            return

        mime = mimetypes.guess_type(str(img_path))[0] or "image/jpeg"
        data = img_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        self.wfile.write(data)

    def _404(self):
        self.send_response(404)
        self.end_headers()

    def log_message(self, fmt, *args):
        # Suppress noisy per-request logs
        pass


def main():
    parser = argparse.ArgumentParser(description="Gemma picks viewer")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()

    server = HTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Gemma viewer → http://localhost:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    main()
