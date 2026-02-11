# MADphotos

Photo curation and exploration project with two main components:

## Architecture

**Show** — Public-facing photo experience
- Path: `frontend/show/` (vanilla JS, no framework)
- URL: https://madphotos.laeh.ai
- 9 interactive views for exploring 9K+ curated photos
- Deployed to Firebase hosting `laeh-madphotos`

**System** — Internal dashboard and monitoring
- Path: `frontend/system/` (React + TypeScript)
- URL: https://madphotos.laeh.ai/system (static snapshot at deploy time)
- Project info, pipeline status, experiments, database overview
- Built to `frontend/show/system/` and deployed alongside Show
- Local dev with live data: `python3 backend/serve_show.py` → http://localhost:3000/system

## Key paths
- DB: `images/mad_photos.db`
- Show app: `frontend/show/`
- System app: `frontend/system/` (source) → `frontend/show/system/` (built)
- Static data: `frontend/show/data/` (picks.json, stats.json, etc.)
- Firebase project: `laeh380to760`

## Development

**Local dev with live data:**
```bash
python3 backend/serve_show.py
# Show: http://localhost:3000
# System (live): http://localhost:3000/system
```

**System only (Vite dev server):**
```bash
cd frontend/system && npm run dev
# http://localhost:5173 (live data via /api/* endpoints)
```

## Deploy

**Full sync + deploy:**
```bash
python3 backend/firestore_sync.py
```

What it does:
1. Pulls 5 Firestore collections → local SQLite (tinder-votes, couple-likes, couple-approves, couple-rejects, picks-votes)
2. Regenerates `picks.json` (tinder accepts minus picks rejects)
3. Regenerates static data for System dashboard
4. Builds System app (React) → `frontend/show/system/`
5. Deploys both Show + System to Firebase

**Manual deploy (if no data changes):**
```bash
firebase deploy --only hosting:laeh-madphotos
```

Dry run (no writes, just show counts):
```
python3 backend/firestore_sync.py --dry
```

## Quick stats
```sql
-- Vote counts by device
SELECT device, vote, COUNT(*) FROM firestore_tinder_votes GROUP BY device, vote;
-- Picks re-curation votes
SELECT vote, COUNT(*) FROM firestore_picks_votes GROUP BY vote;
```

## Frontend versioning
Bump `v=` param in `index.html` **and** `sw.js` when changing JS/CSS. Current: v=41, SW madphotos-v27.
