# MADphotos — Agent Team

Six agents form the pipeline: extract intelligence, curate material, prepare experiences, and ship to screens.

---

## image_signals — The Intelligence Layer

Extract 24+ signals from every image using local models + cloud APIs.

```bash
python3 -m backend.image_signals.completions              # run full pipeline
python3 -m backend.image_signals.completions --check      # check coverage gaps
```

**Key modules:** `signals_advanced.py` (v1), `signals_v2.py` (v2), `gemini.py` (cloud), `run_gemma_analysis.py` (Ollama 27B)

---

## suggest_image_enhancement — The Improver

Propose non-destructive exposure/color corrections. Human votes accept or reject.

```bash
python3 -m backend.suggest_image_enhancement.propose       # propose enhancements
```

---

## suggest_image_variant — The Artist

Generate AI art variants (neural style transfer, Imagen 3, mflux) with learned style selection.

```bash
python3 -m backend.suggest_image_variant.run               # generate variants
```

**Styles:** Van Gogh, Klimt, Seurat, Monet, Munch + Imagen 3 cartoons

---

## prepare_show — The Curator

Pre-compute everything Show needs: bento compositions, boom sets, game pairs, scores, and lookup indices.

```bash
python3 -m backend.prepare_show.run                        # full pipeline
python3 -m backend.prepare_show.run --audit                # signal coverage report
python3 -m backend.prepare_show.run --score                # visual scores only
python3 -m backend.prepare_show.run --curate               # compositions + pairs only
python3 -m backend.prepare_show.run --dry                  # preview without writing
python3 -m backend.prepare_show.run --force                # regenerate even if fresh
```

**Outputs:** `show_scores.json`, `show_index.json`, `show_bentos.json`, `show_boom.json`, `show_pairs.json`

---

## update_and_deploy — The Shipper

10-phase verified deployment: preflight, inspect, docs, sync, export, data, build, deploy, verify, postflight.

```bash
python3 -m backend.update_and_deploy.run                   # full pipeline
python3 -m backend.update_and_deploy.run --dry             # dry run
python3 -m backend.update_and_deploy.run --preflight       # safety check only
python3 -m backend.update_and_deploy.run --build           # Vite builds only
python3 -m backend.update_and_deploy.run --deploy          # Firebase deploy only
```

**Modifiers:** `--wait`, `--force`, `--no-git`, `--full`

---

## MADphotos_ignition — The Launcher

Dev environment startup: pre-checks, server launch, health verification, ready URLs.

```bash
python3 -m backend.MADphotos_ignition.run                  # full startup
python3 -m backend.MADphotos_ignition.run --shutdown       # stop all servers
python3 -m backend.MADphotos_ignition.run --status         # health check
python3 -m backend.MADphotos_ignition.run --prechecks      # pre-checks only
```

**Flags:** `--health`, `--monitor`, `--see`, `--dry`, `--force`, `--tags`
