"""
Fatigue toll components, each attributed per (Player A, Opponent B) pair.

Design notes / honest assumptions:

- physical_toll: directly tagged in play-by-play (hit events carry both
  hitter and hittee IDs). Clean signal, no inference.

- shift_length_forced_toll: compares an opponent's shift duration DURING
  shifts matched against A vs. that opponent's own baseline shift duration
  in shifts NOT matched against A. Clean-ish -- built entirely from shift
  chart timestamps, no coordinate guessing. This is the best proxy available
  for "elusiveness/possession exhausts opponents" (the Hughes case) since
  public data has no skating-distance tracking.

- pursuit_toll: INFERRED. NHL's feed does not explicitly link a takeaway to
  the giveaway that caused it. We pair a takeaway by A with the nearest
  preceding giveaway by the opposing team within a short time window. This
  will miss cases where the "giveaway" wasn't logged as a discrete event
  (e.g., a loose puck recovery), so it's a conservative undercount, not an
  overcount -- a deliberate choice to avoid false attribution.

- zone_time_toll: INFERRED. Buckets time between consecutive events into
  "A's team possessing in their offensive zone" and attributes that duration
  to whichever opponents were simultaneously on ice. Segment duration is
  capped (default 8s) so a long gap before a stoppage doesn't get counted
  as one giant possession.

- rush_toll: INFERRED. Looks for a turnover in A's defensive/neutral zone
  followed shortly by a shot from A's team -- the signature of a fast-break
  that forces a defensive sprint rather than a positional recovery. Credited
  to whichever opponents were on ice for the resulting shot.
"""

from pipeline.matchup import overlapping_raw_intervals


def players_on_ice_at(t: float, shifts_by_player: dict) -> list:
    out = []
    for pid, intervals in shifts_by_player.items():
        for s, e in intervals:
            if s <= t < e:
                out.append(pid)
                break
    return out


def in_intervals(t: float, intervals: list) -> bool:
    return any(s <= t < e for s, e in intervals)


def physical_toll(events: list[dict], player_a_id) -> dict:
    """opponent_id -> hit count delivered by A"""
    out = {}
    for e in events:
        if e["type"] == "hit" and e.get("hitter_id") == player_a_id:
            b = e.get("hittee_id")
            if b:
                out[b] = out.get(b, 0) + 1
    return out


def shift_length_forced_toll(player_a_intervals: list, opponent_shifts_by_player: dict) -> dict:
    """opponent_id -> extra seconds per matched shift (avg_matched - avg_baseline),
    floored at 0 (we only count it as a toll if A's presence lengthened the shift)."""
    out = {}
    for opp_id, opp_intervals in opponent_shifts_by_player.items():
        matched_durs, baseline_durs = [], []
        for s, e in opp_intervals:
            dur = e - s
            overlaps_a = any(
                max(s, a_s) < min(e, a_e) for a_s, a_e in player_a_intervals
            )
            (matched_durs if overlaps_a else baseline_durs).append(dur)

        if not matched_durs or not baseline_durs:
            continue
        avg_matched = sum(matched_durs) / len(matched_durs)
        avg_baseline = sum(baseline_durs) / len(baseline_durs)
        extra = max(0.0, avg_matched - avg_baseline)
        if extra > 0:
            out[opp_id] = extra
    return out


def pursuit_toll(events: list[dict], player_a_id, a_team_id, opp_team_id, window_s: float = 4.0) -> dict:
    """opponent_id -> count of giveaways by that opponent immediately (within
    window_s) preceding a takeaway by player A."""
    out = {}
    takeaways = [e for e in events if e["type"] == "takeaway" and e.get("player_id") == player_a_id]
    giveaways = [e for e in events if e["type"] == "giveaway" and e.get("team_id") == opp_team_id]

    for tk in takeaways:
        # nearest preceding giveaway within window
        candidates = [g for g in giveaways if 0 <= tk["abs_time"] - g["abs_time"] <= window_s]
        if not candidates:
            continue
        nearest = max(candidates, key=lambda g: g["abs_time"])
        b = nearest.get("player_id")
        if b:
            out[b] = out.get(b, 0) + 1
    return out


def zone_time_toll(
    events: list[dict],
    a_team_id,
    player_a_intervals: list,
    opponent_shifts_by_player: dict,
    max_segment_s: float = 8.0,
) -> dict:
    """opponent_id -> seconds spent defending in their own zone while matched
    against A, estimated from consecutive-event gaps where the event team is
    A's team and zoneCode == 'O' (offensive for A's team)."""
    out = {}
    team_events = [e for e in events if e.get("team_id") == a_team_id]
    team_events.sort(key=lambda e: e["abs_time"])

    for i in range(len(team_events) - 1):
        e = team_events[i]
        if e.get("zone_code") != "O":
            continue
        t0, t1 = e["abs_time"], team_events[i + 1]["abs_time"]
        seg = min(t1 - t0, max_segment_s)
        if seg <= 0:
            continue
        # midpoint check keeps this cheap; good enough given the segment cap
        mid = t0 + seg / 2
        if not in_intervals(mid, player_a_intervals):
            continue
        on_ice_opps = players_on_ice_at(mid, opponent_shifts_by_player)
        for b in on_ice_opps:
            out[b] = out.get(b, 0.0) + seg
    return out


def rush_toll(
    events: list[dict],
    a_team_id,
    opponent_shifts_by_player: dict,
    threshold_s: float = 5.0,
) -> dict:
    """opponent_id -> count of rush sequences (defensive/neutral-zone turnover
    -> shot within threshold_s) that opponent had to defend against."""
    out = {}
    turnovers = [
        e for e in events
        if e.get("team_id") == a_team_id
        and e["type"] == "takeaway"
        and e.get("zone_code") in ("D", "N")
    ]
    shots = [e for e in events if e.get("team_id") == a_team_id and e["type"] in
             ("shot-on-goal", "missed-shot", "blocked-shot", "goal")]
    shots.sort(key=lambda e: e["abs_time"])

    for to in turnovers:
        window_shots = [s for s in shots if 0 < s["abs_time"] - to["abs_time"] <= threshold_s]
        if not window_shots:
            continue
        shot_time = window_shots[0]["abs_time"]
        on_ice_opps = players_on_ice_at(shot_time, opponent_shifts_by_player)
        for b in on_ice_opps:
            out[b] = out.get(b, 0) + 1
    return out
