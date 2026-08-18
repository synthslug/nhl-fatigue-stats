# NHL Fatigue Metrics

Two original stats, computed daily from public NHL play-by-play and shift
data, with zero infrastructure beyond GitHub itself:

- **FII (Fatigue Induction Index)** — a player's rate of forcing fatigue onto
  matched-up opponents (hits, extended shifts, forced turnovers, imposed zone
  time, rush sequences), weighted by how important that opponent is.
- **FPI (Fatigue Pressure Index)** — a player's own accumulated fatigue load
  right now, percentile-ranked against their own season.

## How it runs itself

```
GitHub Actions (daily cron, 10:00 UTC)
  -> backend/ingest.py       pulls new completed games from the NHL API,
                              computes FII/FPI, writes to data/nhl_fatigue.db
  -> backend/export_static.py  reads the DB, writes docs/data/*.json
  -> git commit + push        both the DB and the JSON go back into the repo
  -> GitHub Pages             serves docs/ (dashboard + JSON) as a static site
```

No server to keep running, no database to pay for, no separate account
besides GitHub. The dashboard reads pre-computed JSON files, not a live API.

## One-time setup (~10 minutes)

1. **Push this repo to GitHub** (if it isn't already there).

2. **Turn on write access for Actions.**
   Repo → Settings → Actions → General → Workflow permissions →
   select **"Read and write permissions"** → Save.
   (Without this, the daily job can compute the data but can't commit it back.)

3. **Turn on GitHub Pages.**
   Repo → Settings → Pages → Source: **Deploy from a branch** → Branch:
   `main`, folder: **`/docs`** → Save.
   Your dashboard will be live at `https://<username>.github.io/<repo>/`
   within a minute or two.

4. **Seed it with data** (don't wait for tomorrow's cron):
   Repo → Actions tab → "Daily fatigue-stats update" → **Run workflow**.
   Watch it go green, then reload the Pages URL.

That's it. From here it updates itself daily, forever, for free.

## Checking on it without babysitting it

The dashboard's footer shows pipeline health (last update time, any recent
ingestion errors) — that's the honest signal of whether it's still working.
If it ever goes stale, check the Actions tab for the failing run's logs
before touching any code; the error message in a failed step usually points
straight at what changed (most likely: NHL shifted a field name in their
API response — see the caveats in `pipeline/pbp.py` and `pipeline/nhl_api.py`).

## Local development / backfilling history

```bash
pip install -r requirements.txt

# backfill the last 30 days instead of the default 3-day lookback:
python -m backend.ingest --days 30
python -m backend.export_static

# open docs/index.html directly, or serve it:
cd docs && python -m http.server 8000
```

## Tuning the metrics

Both indexes are fully reweightable without re-fetching any data, because the
DB stores raw per-game features, not just the final score:

- `pipeline/fii.py` → `FIIConfig` — weights for physical/shift-forced/
  pursuit/zone-time/rush tolls, and the opponent role-weight floor.
- `pipeline/fatigue.py` → `FPIConfig` — decay halflife, back-to-back and
  travel penalties, recovery rate.

Change a weight, re-run `python -m backend.export_static` (no need to
re-ingest), and the leaderboards reflect it.

## Known limitations, honestly

- The NHL API used here (`api-web.nhle.com`, `api.nhle.com/stats`) is
  unofficial and undocumented. Field names in `pipeline/pbp.py` and
  `pipeline/nhl_api.py` are best-effort and may need adjustment if NHL
  changes their response shape.
- `pursuit_toll`, `zone_time_toll`, and `rush_toll` in `pipeline/tolls.py`
  are inferred from event sequencing and coordinates, not explicitly tagged
  by the NHL feed — see the docstring in that file for exactly what each
  proxy assumes.
- Player display names aren't backfilled automatically yet (ingestion
  stores player IDs; the export currently falls back to `player_<id>` if a
  name was never captured). A small follow-up job hitting the roster
  endpoint would fix this — flagged in `backend/ingest.py`.
- SQLite-in-git is the simplest possible storage for getting started. If the
  repo size or commit frequency ever becomes annoying, swapping
  `DATABASE_URL` to a real Postgres instance (Railway, Supabase, etc.) is a
  one-line config change — the code already handles both.
