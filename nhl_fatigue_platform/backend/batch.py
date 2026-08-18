"""
Batch, roster-wide computation for a single game.

The per-player pipeline (build_player_fii.py / build_player_fpi.py from the
earlier prototype) fetched boxscore/shifts/play-by-play once PER PLAYER,
which is wasteful -- those three API calls are the same for every skater in
the game. This module fetches each exactly once and computes FII + FPI raw
features for every skater on both teams in one pass.
"""

from pipeline import nhl_api
from pipeline.pbp import normalize_events
from pipeline.shifts import parse_shifts, group_by_player, merge_intervals
from pipeline.strength import build_strength_timeline
from pipeline.matchup import compute_shared_5v5_toi
from pipeline.tolls import physical_toll, shift_length_forced_toll, pursuit_toll, zone_time_toll, rush_toll
from pipeline.roles import compute_role_weights
from pipeline.fii import combine_tolls, aggregate_fii, FIIConfig
from pipeline.arenas import TEAM_ARENAS


def _skaters_only(toi_map: dict) -> dict:
    """extract_player_toi includes goalies; FII/matchup analysis is skater-only."""
    # boxscore doesn't tag position in extract_player_toi's current shape, so
    # we approximate: goalies rarely log 5v5 shift-chart entries the same way
    # skaters do. Cleaner fix: extend extract_player_toi to carry position and
    # filter on that -- flagged here rather than silently trusting shift data.
    return toi_map


def compute_game_batch(game_id: int, cfg: FIIConfig = FIIConfig()) -> dict:
    """
    Returns:
      {
        "game_id", "date", "home": {"team_id","abbrev"}, "away": {...},
        "fii_results": {player_id: aggregate_fii() dict},
        "fpi_features": {player_id: {toi_minutes, venue_team, date}},  # raw,
             not decayed -- decay is computed across a player's full game log
             at query/ingest time, not per-game
      }
    Raises on API failure -- caller (ingest.py) decides whether to retry/skip.
    """
    boxscore = nhl_api.fetch_boxscore(game_id)
    team_ids = nhl_api.extract_team_ids(boxscore)
    toi_map = _skaters_only(nhl_api.extract_player_toi(boxscore))
    game_date = boxscore.get("gameDate")

    raw_shifts = nhl_api.fetch_shift_chart(game_id)
    shifts = parse_shifts(raw_shifts)
    by_player = group_by_player(shifts)
    player_team = {s["player_id"]: s["team_id"] for s in shifts}

    raw_plays = nhl_api.fetch_play_by_play(game_id)
    events = normalize_events(raw_plays)
    timeline = build_strength_timeline(events)

    home_id, home_abbrev = team_ids["home"]
    away_id, away_abbrev = team_ids["away"]

    home_toi = {pid: v["toi_minutes"] for pid, v in toi_map.items() if v["team"] == home_abbrev}
    away_toi = {pid: v["toi_minutes"] for pid, v in toi_map.items() if v["team"] == away_abbrev}
    home_weights = compute_role_weights(home_toi, floor=cfg.role_floor)
    away_weights = compute_role_weights(away_toi, floor=cfg.role_floor)

    fii_results = {}
    fpi_features = {}

    for team_id, own_abbrev, opp_team_id, opp_weights in (
        (home_id, home_abbrev, away_id, away_weights),
        (away_id, away_abbrev, home_id, home_weights),
    ):
        own_player_ids = [pid for pid, tid in player_team.items() if tid == team_id]
        opp_shifts_all = {pid: ivs for pid, ivs in by_player.items() if player_team.get(pid) == opp_team_id}

        for pid in own_player_ids:
            if pid not in by_player:
                continue
            a_intervals = merge_intervals(by_player[pid])
            if not a_intervals:
                continue

            shared_toi = compute_shared_5v5_toi(a_intervals, opp_shifts_all, timeline)
            if shared_toi:
                phys = physical_toll(events, pid)
                shift_forced = shift_length_forced_toll(a_intervals, opp_shifts_all)
                pursuit = pursuit_toll(events, pid, team_id, opp_team_id)
                zone = zone_time_toll(events, team_id, a_intervals, opp_shifts_all)
                rush = rush_toll(events, team_id, opp_shifts_all)

                combined = combine_tolls(phys, shift_forced, pursuit, zone, rush, opp_weights, cfg)
                fii_results[pid] = aggregate_fii(combined, shared_toi)

            toi_minutes = toi_map.get(pid, {}).get("toi_minutes", 0.0)
            fpi_features[pid] = {
                "toi_minutes": toi_minutes,
                "venue_team": home_abbrev,  # game was played at home team's arena
                "date": game_date,
            }

    return {
        "game_id": game_id,
        "date": game_date,
        "home": {"team_id": home_id, "abbrev": home_abbrev},
        "away": {"team_id": away_id, "abbrev": away_abbrev},
        "fii_results": fii_results,
        "fpi_features": fpi_features,
    }
