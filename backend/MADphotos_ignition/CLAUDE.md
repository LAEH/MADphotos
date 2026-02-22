# MADphotos Ignition Agent

Startup agent for the MADphotos dev environment. Automates the full startup sequence: pre-checks, server launch, health verification, and optional companions.

## Trigger

When the user says **"MADphotos ignition"**, run:
```bash
python3 -m backend.MADphotos_ignition.run
```

## 4-Phase Pipeline

| Phase | Module | What it does |
|-------|--------|-------------|
| 1. PRECHECKS | `prechecks.py` | Git state, port scan (3000/5173/5174), node_modules, DB, Ollama |
| 2. SERVERS | `servers.py` | Start serve_show (:3000), Show vite (:5173), System vite (:5174) |
| 3. HEALTH | `health.py` | HTTP GET each server with retries, print ready URLs |
| 4. COMPANIONS | `companions.py` | Optional: monitor.py in new Terminal, See app, Ollama details |

## CLI

```bash
python3 -m backend.MADphotos_ignition.run              # full startup (phases 1-3)
python3 -m backend.MADphotos_ignition.run --prechecks   # checks only
python3 -m backend.MADphotos_ignition.run --health      # health check running servers
python3 -m backend.MADphotos_ignition.run --status      # prechecks + health (no startup)
python3 -m backend.MADphotos_ignition.run --shutdown     # graceful kill all
python3 -m backend.MADphotos_ignition.run --monitor      # full startup + terminal monitor
python3 -m backend.MADphotos_ignition.run --see          # full startup + native See app
python3 -m backend.MADphotos_ignition.run --dry          # print without executing
python3 -m backend.MADphotos_ignition.run --force        # start even with port conflicts
python3 -m backend.MADphotos_ignition.run --tags         # set Finder yellow labels
```

## Idempotent Startup

- If a port is occupied by a MADphotos process → skip that server, verify in health phase
- If a port is occupied by something else → error (unless `--force`)
- Running ignition twice is safe: second run skips all servers, just verifies health

## Server Definitions

| Server | Port | Command | CWD |
|--------|------|---------|-----|
| serve_show | 3000 | `python3 backend/serve_show.py` | PROJECT_ROOT |
| vite_show | 5173 | `npm run dev` | frontend/show |
| vite_system | 5174 | `npm run dev -- --port 5174` | frontend/system |

## Logs

Server stdout/stderr goes to `/tmp/madphotos_ignition_{name}.log`.

## Shutdown

`--shutdown` finds all MADphotos processes via `ps aux`, sends SIGTERM, waits 3s, then SIGKILL if still alive.
