"""
Static export: reads the SQLite DB (committed to the repo) and writes plain
JSON files into docs/data/, which GitHub Pages serves as-is. This is what
lets the frontend be a static site with zero backend -- it just fetches
./data/*.json.

Run after ingest.py, in the same GitHub Actions job:
    python -m backend.ingest
    python -m backend.export_static
    git commit -am "data update" && git push
"""

import json
import os
from datetime import datetime, timezone
from collections import defaultdict

from backend.models import get_session, Player, GameFPI, GameFII, FIIMatchup, IngestLog
from pipeline.fatigue import compute_fpi_series, FPIConfig

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "data")


def _ensure_out_dir():
    os.makedirs(OUT_DIR, exist_ok=True)


def export_fii_leaderboard(session, min_toi_minutes: float = 20.0, limit: int = 100):
    """Season-to-date FII leaderboard: sum weighted toll / sum shared TOI per player."""
    rows = session.query(GameFII).all()
    agg = defaultdict(lambda: {"weighted": 0.0, "toi": 0.0, "games": 0})
    for r in rows:
        a = agg[r.player_id]
        a["weighted"] += r.total_weighted_toll
        a["toi"] += r.total_shared_toi_min
        a["games"] += 1

    players = {p.id: p for p in session.query(Player).all()}
    leaderboard = []
    for pid, a in agg.items():
        if a["toi"] < min_toi_minutes:
            continue
        fii_per_60 = (a["weighted"] / a["toi"]) * 60.0 if a["toi"] > 0 else 0.0
        p = players.get(pid)
        leaderboard.append({
            "player_id": pid,
            "name": p.name if p else f"player_{pid}",
            "team": p.team_abbrev if p else None,
            "fii_per_60": round(fii_per_60, 3),
            "games": a["games"],
            "total_shared_toi_min": round(a["toi"], 1),
        })

    leaderboard.sort(key=lambda r: r["fii_per_60"], reverse=True)
    return leaderboard[:limit]


def export_fpi_leaderboard(session, halflife_days: float = 4.0, limit: int = 100):
    """Most recent FPI percentile per player, computed from their full stored
    game-log history (recomputed each export -- cheap, it's just arithmetic
    over already-fetched rows, no API calls)."""
    all_rows = session.query(GameFPI).all()
    by_player = defaultdict(list)
    for r in all_rows:
        by_player[r.player_id].append({
            "date": r.date, "venue_team": r.venue_team, "toi_minutes": r.toi_minutes,
        })

    players = {p.id: p for p in session.query(Player).all()}
    cfg = FPIConfig(halflife_days=halflife_days)
    leaderboard = []
    for pid, games in by_player.items():
        if len(games) < 2:
            continue
        try:
            from pipeline.fatigue import build_game_log_features
            enriched = build_game_log_features(games)
            series = compute_fpi_series(enriched, cfg)
        except Exception as exc:
            print(f"  WARN: FPI compute failed for player {pid}: {exc}")
            continue
        latest = series[-1]
        p = players.get(pid)
        leaderboard.append({
            "player_id": pid,
            "name": p.name if p else f"player_{pid}",
            "team": p.team_abbrev if p else None,
            "fpi_pct": latest["fpi_pct"],
            "as_of_date": latest["date"],
            "games": len(games),
        })

    leaderboard.sort(key=lambda r: r["fpi_pct"], reverse=True)
    return leaderboard[:limit]


def export_player_detail(session, player_id: int):
    fii_rows = (session.query(GameFII)
                .filter_by(player_id=player_id)
                .order_by(GameFII.date).all())

    # gather matchups + all opponent ids first, then resolve names in one query
    matchups_by_game = {}
    opponent_ids = set()
    for r in fii_rows:
        matchups = (session.query(FIIMatchup)
                    .filter_by(game_fii_id=r.id)
                    .order_by(FIIMatchup.weighted_toll.desc()).all())[:5]
        matchups_by_game[r.id] = matchups
        opponent_ids.update(m.opponent_player_id for m in matchups)

    opponent_names = {}
    if opponent_ids:
        opponent_names = {
            p.id: p.name for p in session.query(Player).filter(Player.id.in_(opponent_ids)).all()
        }

    fii_games = []
    for r in fii_rows:
        matchups = matchups_by_game[r.id]
        fii_games.append({
            "game_id": r.game_id, "date": r.date, "fii_per_60": r.fii_per_60,
            "total_weighted_toll": r.total_weighted_toll,
            "total_shared_toi_min": r.total_shared_toi_min,
            "top_matchups": [
                {
                    "opponent_player_id": m.opponent_player_id,
                    "opponent_name": opponent_names.get(m.opponent_player_id, f"player_{m.opponent_player_id}"),
                    "weighted_toll": m.weighted_toll,
                    "role_weight": m.role_weight, "components": m.components_json,
                }
                for m in matchups
            ],
        })
    return {"player_id": player_id, "fii_games": fii_games}


def export_ingest_status(session, recent_n: int = 30):
    rows = (session.query(IngestLog).order_by(IngestLog.ingested_at.desc()).limit(recent_n).all())
    return {
        "last_run_utc": datetime.now(timezone.utc).isoformat(),
        "recent": [
            {"game_id": r.game_id, "status": r.status, "ingested_at": r.ingested_at.isoformat(),
             "error": (r.error_message or "")[:300] if r.status == "error" else None}
            for r in rows
        ],
        "error_count_recent": sum(1 for r in rows if r.status == "error"),
    }


def run():
    _ensure_out_dir()
    session = get_session()

    fii_board = export_fii_leaderboard(session)
    fpi_board = export_fpi_leaderboard(session)
    status = export_ingest_status(session)

    with open(os.path.join(OUT_DIR, "leaderboard_fii.json"), "w") as f:
        json.dump(fii_board, f, indent=2)
    with open(os.path.join(OUT_DIR, "leaderboard_fpi.json"), "w") as f:
        json.dump(fpi_board, f, indent=2)
    with open(os.path.join(OUT_DIR, "status.json"), "w") as f:
        json.dump(status, f, indent=2)

    players_dir = os.path.join(OUT_DIR, "players")
    os.makedirs(players_dir, exist_ok=True)
    all_player_ids = {r["player_id"] for r in fii_board} | {r["player_id"] for r in fpi_board}
    for pid in all_player_ids:
        detail = export_player_detail(session, pid)
        with open(os.path.join(players_dir, f"{pid}.json"), "w") as f:
            json.dump(detail, f, indent=2)

    session.close()
    print(f"Exported {len(fii_board)} FII rows, {len(fpi_board)} FPI rows, "
          f"{len(all_player_ids)} player detail files to {OUT_DIR}")


if __name__ == "__main__":
    run()
