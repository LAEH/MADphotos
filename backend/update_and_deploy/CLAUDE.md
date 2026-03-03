# update_and_deploy — Deploy Agent

## Mission

Get the project safely from working tree to production. Every deploy should be verified before, during, and after. No more deploying stale data, forgetting to rebuild System, or pushing while Gemma is writing to the DB.

## Lifecycle

```
Preflight → Inspect → Docs → Sync → Export → Data → Build → Deploy → Verify → Postflight
```

1. **Preflight** — Check running processes (blocking vs non-blocking), verify GCP + Firebase auth, report port usage. Won't proceed if DB-writing processes are active. (`preflight.py`)
2. **Inspect** — Show git changes since last deploy commit, unstaged files, current branch. (`inspect.py`)
3. **Docs** — Check journal freshness, CLAUDE.md presence across agent folders, README health. (`docs.py`)
4. **Sync** — Pull latest Firestore vote collections into SQLite, regenerate picks.json + voted.json. (`deploy.py` → `firestore_sync`)
5. **Export** — Fingerprint-gated gallery export — only regenerates photos.json if DB counts changed. (`build.py` → `export_gallery`)
6. **Data** — Regenerate all System static JSON files (10 files: stats, journal, instructions, mosaics, cartoon, gemma, gemma_cartoon, cartoons, signal_inspector_picks, qwen). (`data.py`)
7. **Build** — Vite build Show + System, copy System dist into Show dist. (`build.py`)
8. **Deploy** — `firebase deploy --only hosting:madphotos`. (`deploy.py`)
9. **Verify** — HTTP HEAD checks on live URLs (madphotos.laeh.ai, /system, /data/photos.json). (`deploy.py`)
10. **Postflight** — Set yellow Finder tags on agent folders, detect running dev servers, git commit + push. (`postflight.py`)

## Key Files

| File | Purpose |
|------|---------|
| `__init__.py` | Constants: paths, process classification lists, port map, agent folders, live URLs |
| `run.py` | CLI orchestrator — 10 phases, per-phase flags, `--dry`/`--wait`/`--force`/`--no-git`/`--full` |
| `preflight.py` | Process detection, port scanning, GCP/Firebase auth checks |
| `inspect.py` | Git diff since last deploy, unstaged changes, branch info |
| `docs.py` | Journal freshness, CLAUDE.md presence, README health |
| `data.py` | Regenerate 9 System static JSON files (absorbs `scripts/generate_static.py`) |
| `assets.py` | GCS spot-check — verify picks have thumb + display tiers in bucket |
| `build.py` | Gallery fingerprint + export, Vite builds for Show + System |
| `deploy.py` | Firestore sync, Firebase deploy, HTTP verification |
| `postflight.py` | Finder tags (yellow label), dev server detection, git commit + push |

## CLI

```bash
# Full pipeline
python3 -m backend.update_and_deploy.run

# Individual phases
python3 -m backend.update_and_deploy.run --preflight   # safety check
python3 -m backend.update_and_deploy.run --inspect     # git changes
python3 -m backend.update_and_deploy.run --docs        # doc health
python3 -m backend.update_and_deploy.run --data        # regen System JSON
python3 -m backend.update_and_deploy.run --assets      # GCS check
python3 -m backend.update_and_deploy.run --build       # Vite builds
python3 -m backend.update_and_deploy.run --deploy      # Firebase deploy + verify
python3 -m backend.update_and_deploy.run --verify      # live URL checks
python3 -m backend.update_and_deploy.run --tags        # Finder labels

# Modifiers
python3 -m backend.update_and_deploy.run --dry         # print without executing
python3 -m backend.update_and_deploy.run --wait        # poll until blockers clear
python3 -m backend.update_and_deploy.run --force       # deploy despite blockers
python3 -m backend.update_and_deploy.run --no-git      # skip git commit/push
python3 -m backend.update_and_deploy.run --full        # force gallery re-export
```

## Process Classification

**Blocking** (write to DB — unsafe to deploy alongside):
`run_gemma_analysis`, `run_gemma_forever`, `gemma_monitor`, `signals*.py`, `render.py`, `enhance*`, `imagen.py`, `pipeline.py`, `vectors*.py`, `firestore_sync`, `export_gallery`

**Non-blocking** (read-only — safe):
`serve_show`, `dashboard.py`, `server.py`, `vite`, `monitor.py`

## Gallery Fingerprint

The export phase uses a fingerprint file (`.gallery_fingerprint.json`) containing DB counts (images, gemini analyses, faces, votes). Export only runs if counts have changed since last export, unless `--full` is passed.

## Finder Tags

Yellow label (index 3) applied to all 5 agent folders via AppleScript:
- `backend/update_and_deploy/`
- `backend/suggest_image_variant/`
- `backend/suggest_image_enhancement/`
- `backend/image_signals/`
- `backend/MADphotos_ignition/`

Run standalone with `--tags` or automatically at end of every full deploy.

## Backward Compatibility

`scripts/deploy.py` is a thin shim that calls `backend.update_and_deploy.run.main()`. Existing launchd plists continue to work.
