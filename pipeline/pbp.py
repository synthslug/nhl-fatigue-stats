"""
Play-by-play fetch + normalization.

NHL's api-web play-by-play endpoint returns a list of "plays", each with a
typeDescKey ("hit", "giveaway", "takeaway", "shot-on-goal", "missed-shot",
"blocked-shot", "goal", "faceoff", "penalty", "stoppage", "period-start",
"period-end", ...) and a "details" object whose field names DEPEND on the
type. This module normalizes the ones FII actually needs into one flat shape.

CAVEAT: this schema is reverse-engineered / community-documented, not
officially published by NHL. Field names below (hittingPlayerId, playerId,
zoneCode, situationCode, etc.) are the commonly-observed names as of recent
seasons. If fetch_play_by_play_raw() succeeds but normalize_events() returns
mostly None fields, print a raw play dict and check the actual key names --
that's the first thing to fix.
"""

WEB_BASE = "https://api-web.nhle.com/v1"


def fetch_play_by_play_raw(game_id: int, _get):
    """_get is the shared HTTP helper from nhl_api.py (passed in to avoid a
    circular import -- call as: fetch_play_by_play_raw(game_id, nhl_api._get)"""
    url = f"{WEB_BASE}/gamecenter/{game_id}/play-by-play"
    data = _get(url)
    return data.get("plays", [])


def _period_to_abs_seconds(period_number: int, time_in_period: str) -> float:
    """Convert (period, 'MM:SS' elapsed) to absolute game-clock seconds from puck drop.
    Regulation periods assumed 20:00 (1200s). OT (period 4+) is NOT handled precisely
    here -- 3v3 OT and shootouts are excluded downstream via situationCode filtering,
    but if you need OT fatigue analysis this needs a period-length lookup."""
    mm, ss = time_in_period.split(":")
    elapsed = int(mm) * 60 + int(ss)
    return (period_number - 1) * 1200 + elapsed


NORMALIZERS = {
    "hit": lambda d: {
        "hitter_id": d.get("hittingPlayerId"),
        "hittee_id": d.get("hitteePlayerId"),
    },
    "giveaway": lambda d: {"player_id": d.get("playerId")},
    "takeaway": lambda d: {"player_id": d.get("playerId")},
    "shot-on-goal": lambda d: {"shooter_id": d.get("shootingPlayerId")},
    "missed-shot": lambda d: {"shooter_id": d.get("shootingPlayerId")},
    "blocked-shot": lambda d: {
        "shooter_id": d.get("shootingPlayerId"),
        "blocker_id": d.get("blockingPlayerId"),
    },
    "goal": lambda d: {"shooter_id": d.get("scoringPlayerId")},
    "faceoff": lambda d: {
        "winner_id": d.get("winningPlayerId"),
        "loser_id": d.get("losingPlayerId"),
    },
    "penalty": lambda d: {
        "committed_by_id": d.get("committedByPlayerId"),
        "drawn_by_id": d.get("drawnByPlayerId"),
    },
}

SHOT_EVENT_TYPES = {"shot-on-goal", "missed-shot", "blocked-shot", "goal"}


def normalize_events(raw_plays: list[dict]) -> list[dict]:
    """Flatten raw plays into: type, abs_time, period, situation_code, zone_code,
    x, y, team_id, plus type-specific fields merged in from NORMALIZERS."""
    out = []
    for p in raw_plays:
        type_key = p.get("typeDescKey")
        period_desc = p.get("periodDescriptor", {})
        period_num = period_desc.get("number", 1)
        time_in_period = p.get("timeInPeriod", "00:00")
        details = p.get("details", {}) or {}

        try:
            abs_time = _period_to_abs_seconds(period_num, time_in_period)
        except Exception:
            continue

        base = {
            "type": type_key,
            "period": period_num,
            "abs_time": abs_time,
            "situation_code": p.get("situationCode"),
            "zone_code": details.get("zoneCode"),
            "x": details.get("xCoord"),
            "y": details.get("yCoord"),
            "team_id": details.get("eventOwnerTeamId"),
        }

        norm_fn = NORMALIZERS.get(type_key)
        if norm_fn:
            base.update(norm_fn(details))

        out.append(base)

    out.sort(key=lambda e: e["abs_time"])
    return out
