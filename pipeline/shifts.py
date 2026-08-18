"""
Shift chart parsing.

Raw records from api.nhle.com/stats/rest/en/shiftcharts look like:
    {playerId, teamId, teamAbbrev, period, startTime: 'MM:SS', endTime: 'MM:SS',
     duration: 'MM:SS', shiftNumber, ...}

This converts each shift to absolute game-clock seconds (same clock as pbp.py's
abs_time) and groups into per-player interval lists for matchup computation.
"""


def _mmss_to_seconds(s: str) -> int:
    mm, ss = s.split(":")
    return int(mm) * 60 + int(ss)


def _period_abs(period_number: int, mmss: str) -> float:
    return (period_number - 1) * 1200 + _mmss_to_seconds(mmss)


def parse_shifts(raw_shifts: list[dict]) -> list[dict]:
    """Returns list of {player_id, team_id, start_abs, end_abs, duration_s}."""
    out = []
    for s in raw_shifts:
        period = s.get("period")
        start = s.get("startTime")
        end = s.get("endTime")
        if period is None or not start or not end:
            continue
        start_abs = _period_abs(period, start)
        end_abs = _period_abs(period, end)
        if end_abs <= start_abs:
            continue  # bad/zero-length record, skip
        out.append({
            "player_id": s.get("playerId"),
            "team_id": s.get("teamId"),
            "start_abs": start_abs,
            "end_abs": end_abs,
            "duration_s": end_abs - start_abs,
        })
    return out


def group_by_player(shifts: list[dict]) -> dict:
    """player_id -> sorted list of (start_abs, end_abs) tuples."""
    grouped = {}
    for s in shifts:
        grouped.setdefault(s["player_id"], []).append((s["start_abs"], s["end_abs"]))
    for pid in grouped:
        grouped[pid].sort()
    return grouped


def merge_intervals(intervals: list[tuple]) -> list[tuple]:
    """Merge overlapping/adjacent (start,end) intervals -- a player's shifts
    shouldn't overlap in real data, but this makes downstream code robust to
    any double-counted/duplicate shift records."""
    if not intervals:
        return []
    ivs = sorted(intervals)
    merged = [ivs[0]]
    for s, e in ivs[1:]:
        last_s, last_e = merged[-1]
        if s <= last_e:
            merged[-1] = (last_s, max(last_e, e))
        else:
            merged.append((s, e))
    return merged
