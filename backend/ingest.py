"""
Daily ingestion job. Designed to run unattended on a schedule (GitHub Actions
cron calls this). Idempotent: games already in ingest_log with status 'ok'
are skipped, so re-running is safe.

Looks back LOOKBACK_DAYS (default 3) rather than just "yesterday" so a single
missed/failed run doesn't permanently lose a day -- the next run picks it up.

Usage:
    python -m backend.ingest                  # last 3 days
    python -m backend.ingest --days 10         # backfill last 10 days
    python -m backend.ingest --date 2025-01-15 # one specific date
"""

import argparse
import sys
import traceback
from datetime import datetime, timedelta, timezone

from backend.models import init_db, get_session, Player, GameFPI, GameFII, FIIMatchup, IngestLog
from backend.batch import compute_game_batch
from pipeline import nhl_api
from pipeline.fii import FIIConfig


def already_ingested(session, game_id: int) -> bool:
    row = session.query(IngestLog).filter_by(game_id=game_id).first()
    return row is not None and row.status == "ok"


def upsert_player(session, player_id: int, name: str, team_abbrev: str):
    p = session.get(Player, player_id)
    if p is None:
        session.add(Player(id=player_id, name=name, team_abbrev=team_abbrev))
    else:
        p.team_abbrev = team_abbrev  # keep most recent team on file


def ingest_game(session, game_id: int, cfg: FIIConfig, player_names: dict):
    result = compute_game_batch(game_id, cfg)

    for pid, feat in result["fpi_features"].items():
        name = player_names.get(pid, f"player_{pid}")
        team = feat["venue_team"] if feat["venue_team"] else None
        upsert_player(session, pid, name, team)

        exists = session.query(GameFPI).filter_by(player_id=pid, game_id=game_id).first()
        if exists:
            continue
        session.add(GameFPI(
            player_id=pid, game_id=game_id, date=feat["date"],
            venue_team=feat["venue_team"], toi_minutes=feat["toi_minutes"],
        ))

    for pid, fii in result["fii_results"].items():
        exists = session.query(GameFII).filter_by(player_id=pid, game_id=game_id).first()
        if exists:
            continue
        row = GameFII(
            player_id=pid, game_id=game_id, date=result["date"],
            fii_per_60=fii["fii_per_60"],
            total_weighted_toll=fii["total_weighted_toll"],
            total_shared_toi_min=fii["total_shared_toi_min"],
        )
        session.add(row)
        session.flush()  # get row.id for FK
        for opp_id, detail in fii["by_opponent"].items():
            session.add(FIIMatchup(
                game_fii_id=row.id, opponent_player_id=opp_id,
                raw_toll=detail["raw_toll"], role_weight=detail["role_weight"],
                weighted_toll=detail["weighted_toll"], components_json=detail["components"],
            ))

    session.add(IngestLog(game_id=game_id, status="ok", error_message=None,
                           ingested_at=datetime.now(timezone.utc)))
    session.commit()


def collect_candidate_games(days: int, specific_date: str = None):
    if specific_date:
        dates = [specific_date]
    else:
        today = datetime.now(timezone.utc).date()
        dates = [(today - timedelta(days=i)).isoformat() for i in range(1, days + 1)]

    game_ids = []
    for d in dates:
        games = nhl_api.fetch_schedule_by_date(d)
        for g in games:
            if g.get("gameState") in ("OFF", "FINAL"):
                game_ids.append(g["id"])
    return sorted(set(game_ids))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3, help="lookback window in days")
    ap.add_argument("--date", type=str, default=None, help="process one specific YYYY-MM-DD instead")
    args = ap.parse_args()

    init_db()
    session = get_session()
    cfg = FIIConfig()

    game_ids = collect_candidate_games(args.days, args.date)
    print(f"Found {len(game_ids)} completed games in range.")

    ok, skipped, failed = 0, 0, 0
    for gid in game_ids:
        if already_ingested(session, gid):
            skipped += 1
            continue
        try:
            # player names aren't in boxscore's playerByGameStats in a
            # convenient flat form for this pass -- default to placeholder;
            # a light follow-up job can backfill names from the roster
            # endpoint. Not blocking ingestion on it keeps the pipeline
            # resilient to that endpoint's shape changing independently.
            ingest_game(session, gid, cfg, player_names={})
            ok += 1
            print(f"  game {gid}: OK")
        except Exception as exc:
            failed += 1
            err_text = f"{exc}\n{traceback.format_exc()}"
            print(f"  game {gid}: ERROR - {exc}")
            session.rollback()
            existing = session.query(IngestLog).filter_by(game_id=gid).first()
            if existing:
                existing.status, existing.error_message = "error", err_text
                existing.ingested_at = datetime.now(timezone.utc)
            else:
                session.add(IngestLog(game_id=gid, status="error", error_message=err_text,
                                       ingested_at=datetime.now(timezone.utc)))
            session.commit()

    print(f"\nDone. ok={ok} skipped={skipped} failed={failed}")
    session.close()
    if failed > 0 and ok == 0:
        sys.exit(1)  # surfaces as a failed Action run if NOTHING succeeded


if __name__ == "__main__":
    main()
