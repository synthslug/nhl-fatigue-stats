"""
Fatigue Pressure Index (FPI) -- player level.

Design:
  1. For every game a player plays, compute a raw "load" contributed by that
     game: ice time, back-to-back status, travel distance, and timezone-shift
     jet lag (with an east-travel penalty, since eastward travel disrupts
     circadian rhythm more than westward -- this is a real finding in sports
     science, not just a hockey guess).
  2. Roll those per-game loads forward with exponential decay (halflife in
     days) so recent games dominate but nothing drops off a cliff.
  3. Subtract a recovery term for rest days since the player's last game.
  4. Convert the raw score to a 0-100 scale via percentile rank against the
     player's own trailing distribution, so "80" means "more fatigued than
     80% of this player's own season," not an arbitrary absolute unit.

Everything is a tunable weight in FPIConfig -- treat the defaults as a
starting hypothesis, not ground truth. The real validation step is checking
whether FPI predicts something (3rd period shot share against, giveaways,
etc.) on held-out games.
"""

from dataclasses import dataclass
from datetime import datetime
import math

from pipeline.arenas import TEAM_ARENAS


@dataclass
class FPIConfig:
    halflife_days: float = 4.0          # decay speed of accumulated load
    b2b_multiplier: float = 1.35        # load multiplier on 2nd night of back-to-back
    travel_penalty_per_500mi: float = 0.4   # load units added per 500 miles traveled
    east_travel_multiplier: float = 1.5     # eastward tz shift penalty vs westward
    tz_penalty_per_hour: float = 0.6        # load units per hour of tz shift
    recovery_per_rest_day: float = 1.2      # load units removed per full rest day
    rolling_window_games: int = 25          # window for percentile normalization


def haversine_miles(lat1, lon1, lat2, lon2):
    r = 3958.8  # earth radius, miles
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _parse_date(d):
    return datetime.strptime(d, "%Y-%m-%d")


def build_game_log_features(games: list[dict]) -> list[dict]:
    """
    games: list of dicts, each must have:
        game_id, date ('YYYY-MM-DD'), venue_team (tricode of arena the game
        was played at), toi_minutes (player's TOI that game)
    Sorted ascending by date is NOT required -- this function sorts internally.

    Returns the same records enriched with: rest_days, is_back_to_back,
    travel_miles, tz_shift_hours, tz_direction_east (bool), raw_load.
    """
    games = sorted(games, key=lambda g: g["date"])
    enriched = []
    prev = None

    for g in games:
        venue = TEAM_ARENAS.get(g["venue_team"])
        if venue is None:
            raise KeyError(f"Unknown venue team code: {g['venue_team']}")
        lat, lon, tz_offset, _ = venue

        if prev is None:
            rest_days = None
            travel_miles = 0.0
            tz_shift = 0.0
            east = False
        else:
            rest_days = (_parse_date(g["date"]) - _parse_date(prev["date"])).days
            prev_lat, prev_lon, prev_tz, _ = TEAM_ARENAS[prev["venue_team"]]
            travel_miles = haversine_miles(prev_lat, prev_lon, lat, lon)
            tz_shift = abs(tz_offset - prev_tz)
            east = tz_offset > prev_tz  # moving to a more positive (eastward) offset

        is_b2b = rest_days == 1  # NHL "back-to-back" = games on consecutive days

        enriched.append({
            **g,
            "rest_days": rest_days,
            "is_back_to_back": is_b2b,
            "travel_miles": travel_miles,
            "tz_shift_hours": tz_shift,
            "tz_direction_east": east,
        })
        prev = g

    return enriched


def compute_raw_load(game: dict, cfg: FPIConfig) -> float:
    """Raw fatigue load contributed by a single game, before decay/recovery."""
    load = game["toi_minutes"]

    if game.get("is_back_to_back"):
        load *= cfg.b2b_multiplier

    load += (game["travel_miles"] / 500.0) * cfg.travel_penalty_per_500mi

    tz_penalty = game["tz_shift_hours"] * cfg.tz_penalty_per_hour
    if game.get("tz_direction_east"):
        tz_penalty *= cfg.east_travel_multiplier
    load += tz_penalty

    return load


def compute_fpi_series(games: list[dict], cfg: FPIConfig = FPIConfig()) -> list[dict]:
    """
    games: output of build_game_log_features(), sorted or not (will sort).

    For each game, computes:
      - raw_load: this game's own contribution
      - decayed_fatigue: exponentially-decayed cumulative load ENTERING this
        game (i.e. does not include the current game's own load -- this is
        "how fatigued were they walking in", which is what you'd use to
        predict performance in that game)
      - fpi_pct: percentile rank of decayed_fatigue against the player's own
        trailing `rolling_window_games` games, scaled 0-100

    Returns games list with these fields added.
    """
    games = sorted(games, key=lambda g: g["date"])
    lam = math.log(2) / cfg.halflife_days

    cumulative = 0.0
    last_date = None
    history = []  # for rolling percentile

    out = []
    for g in games:
        # decay existing cumulative fatigue based on days since last game
        if last_date is not None:
            days_elapsed = (_parse_date(g["date"]) - last_date).days
            cumulative *= math.exp(-lam * days_elapsed)
            # recovery credit for rest
            rest = g.get("rest_days") or 0
            cumulative = max(0.0, cumulative - rest * cfg.recovery_per_rest_day)

        entering_fatigue = cumulative

        window = history[-cfg.rolling_window_games:] if history else [0.0]
        rank = sum(1 for v in window if v <= entering_fatigue) / len(window)
        fpi_pct = round(rank * 100, 1)

        out.append({
            **g,
            "raw_load": round(compute_raw_load(g, cfg), 2),
            "decayed_fatigue_entering": round(entering_fatigue, 2),
            "fpi_pct": fpi_pct,
        })

        history.append(entering_fatigue)
        cumulative += compute_raw_load(g, cfg)
        last_date = _parse_date(g["date"])

    return out
