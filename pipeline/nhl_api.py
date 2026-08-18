"""
Thin client for the (unofficial, undocumented) NHL API.

Two hosts are in play:
  api-web.nhle.com   -> modern JSON API: schedule, boxscore, play-by-play
  api.nhle.com/stats -> legacy "stats" API: shift charts (individual shift
                         start/end times), which api-web doesn't expose.

These endpoints aren't officially documented and NHL has changed them before
without notice. If a call starts 404ing, the shape probably shifted -- check
response JSON structure directly rather than assuming this code is stale-proof.
"""

import time
import requests

WEB_BASE = "https://api-web.nhle.com/v1"
STATS_BASE = "https://api.nhle.com/stats/rest/en"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "nhl-fpi-research/0.1"})


def _get(url, params=None, retries=3, backoff=1.5):
    last_exc = None
    for attempt in range(retries):
        try:
            resp = SESSION.get(url, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            last_exc = exc
            time.sleep(backoff ** attempt)
    raise RuntimeError(f"GET {url} failed after {retries} attempts: {last_exc}")


def fetch_club_schedule_season(team_code: str, season: str):
    """
    season format: '20242025'
    Returns list of game dicts: id, gameDate, homeTeam/awayTeam tricodes, venue.
    """
    url = f"{WEB_BASE}/club-schedule-season/{team_code}/{season}"
    data = _get(url)
    return data.get("games", [])


def fetch_boxscore(game_id: int):
    """
    Full boxscore including playerByGameStats with per-player TOI strings ('MM:SS').
    """
    url = f"{WEB_BASE}/gamecenter/{game_id}/boxscore"
    return _get(url)


def fetch_schedule_by_date(date_str: str):
    """date_str: 'YYYY-MM-DD'. Returns list of game dicts across the whole
    league for that date (id, gameState, teams, etc.) -- used by the daily
    ingestion job to discover newly-completed games automatically."""
    url = f"{WEB_BASE}/schedule/{date_str}"
    data = _get(url)
    games = []
    for day in data.get("gameWeek", []):
        if day.get("date") == date_str:
            games.extend(day.get("games", []))
    return games


def fetch_play_by_play(game_id: int):
    """Raw 'plays' list for a game -- feed this into pbp.normalize_events()."""
    url = f"{WEB_BASE}/gamecenter/{game_id}/play-by-play"
    data = _get(url)
    return data.get("plays", [])


def fetch_shift_chart(game_id: int):
    """
    Legacy stats API. Returns individual shift start/end (period + time) per player
    for a game -- used to derive shift length distribution / high-intensity shifts.
    """
    url = f"{STATS_BASE}/shiftcharts"
    params = {"cayenneExp": f"gameId={game_id}"}
    data = _get(url, params=params)
    return data.get("data", [])


def toi_string_to_minutes(toi_str: str) -> float:
    """Convert 'MM:SS' TOI string to float minutes. Returns 0.0 for missing/blank."""
    if not toi_str or ":" not in toi_str:
        return 0.0
    minutes, seconds = toi_str.split(":")
    return int(minutes) + int(seconds) / 60.0


def extract_team_ids(boxscore: dict) -> dict:
    """{'home': (numeric id, abbrev), 'away': (numeric id, abbrev)}"""
    home = boxscore.get("homeTeam", {})
    away = boxscore.get("awayTeam", {})
    return {
        "home": (home.get("id"), home.get("abbrev")),
        "away": (away.get("id"), away.get("abbrev")),
    }


def extract_player_toi(boxscore: dict) -> dict:
    """
    Pull {player_id: (name, team_tricode, toi_minutes)} out of a boxscore payload.
    Confirmed against a real response (2026-02-01, LAK @ CAR): playerByGameStats
    is keyed by "homeTeam"/"awayTeam", and each player has a "name" field shaped
    {"default": "A. Kempe"} -- first-initial + last name, NOT firstName/lastName
    split (that was a wrong guess in an earlier pass; reverted here).
    """
    out = {}
    pbgs = boxscore.get("playerByGameStats", {})
    for side in ("homeTeam", "awayTeam"):
        team_code = boxscore.get(side, {}).get("abbrev")
        group = pbgs.get(side, {})
        for position_group in ("forwards", "defense", "goalies"):
            for p in group.get(position_group, []):
                pid = p.get("playerId")
                name = p.get("name", {}).get("default") or f"player_{pid}"
                toi = toi_string_to_minutes(p.get("toi", "0:00"))
                out[pid] = {"name": name, "team": team_code, "toi_minutes": toi}
    return out
