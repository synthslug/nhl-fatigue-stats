"""
Matchup engine: for a target player A, compute shared 5v5 on-ice seconds
against every opposing skater who shared the ice with them.
"""

from pipeline.strength import overlap_5v5_seconds


def compute_shared_5v5_toi(
    player_a_intervals: list[tuple],
    opponent_shifts_by_player: dict,
    strength_timeline: list[tuple],
) -> dict:
    """
    player_a_intervals: merged (start,end) list for player A
    opponent_shifts_by_player: {opponent_id: [(start,end), ...]} for the OTHER team
    Returns {opponent_id: shared_5v5_seconds}
    """
    result = {}
    for opp_id, opp_intervals in opponent_shifts_by_player.items():
        total = 0.0
        for a_start, a_end in player_a_intervals:
            for o_start, o_end in opp_intervals:
                lo = max(a_start, o_start)
                hi = min(a_end, o_end)
                if hi > lo:
                    total += overlap_5v5_seconds(strength_timeline, lo, hi)
        if total > 0:
            result[opp_id] = total
    return result


def overlapping_raw_intervals(a_start, a_end, opp_intervals):
    """Return list of raw (non-strength-filtered) overlap windows between one
    of A's shifts and an opponent's shifts -- used by tolls.py for things like
    shift-length-forced that need the actual overlap windows, not just totals."""
    out = []
    for o_start, o_end in opp_intervals:
        lo = max(a_start, o_start)
        hi = min(a_end, o_end)
        if hi > lo:
            out.append((lo, hi))
    return out
