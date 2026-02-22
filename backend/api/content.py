"""Content endpoints: journal, instructions, mosaics."""
from __future__ import annotations

import json
import re

from ._common import JOURNAL_PATH, MOSAIC_DIR


def get_journal_html():
    """Return just the journal content HTML (styles + body) without page shell."""
    if not JOURNAL_PATH.exists():
        return "<p>No journal found.</p>"
    # Import render_journal from pages to avoid circular dep at module level
    from .pages import render_journal
    full_html = render_journal()
    m = re.search(r'<div class="main-content">(.*?)<footer', full_html, re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(r'</nav>\s*<div class="main-content">(.*?)</div>\s*<script', full_html, re.DOTALL)
    if m:
        return m.group(1).strip()
    return "<p>Could not parse journal content.</p>"


def get_instructions_html():
    """Return just the instructions content HTML without page shell."""
    from .pages import render_instructions
    full_html = render_instructions()
    m = re.search(r'<div class="main-content">(.*?)<footer', full_html, re.DOTALL)
    if m:
        return m.group(1).strip()
    return "<p>Could not parse instructions content.</p>"


def get_mosaics_data():
    """Return mosaics catalog as a list of dicts."""
    meta_path = MOSAIC_DIR / "mosaics.json"
    if meta_path.exists():
        mosaics = json.loads(meta_path.read_text())
        return [{"title": m["title"], "description": m["desc"],
                 "filename": m["file"], "count": m["count"]} for m in mosaics]
    return []
