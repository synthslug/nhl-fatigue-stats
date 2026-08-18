"""
Strength-state timeline.

Every normalized play-by-play event carries a situationCode -- a 4-digit
string [awayGoalie][awaySkaters][homeSkaters][homeGoalie], e.g. "1551" means
both goalies in net, 5 skaters each side (full-strength 5v5). We treat the
situationCode on each event as the ground-truth state AT that instant, and
carry it forward (step function) until the next event changes it. This is an
approximation between events (real strength changes happen continuously, e.g.
the instant a penalty is called), but events are frequent enough in NHL data
(every stoppage, shot, hit, etc.) that the error is small and, importantly,
doesn't bias in one direction over a full game.
"""

FULL_STRENGTH_5V5 = "1551"


def build_strength_timeline(events: list[dict]) -> list[tuple]:
    """Returns sorted list of (abs_time, situation_code) at each change point."""
    timeline = []
    last_code = None
    for e in sorted(events, key=lambda x: x["abs_time"]):
        code = e.get("situation_code")
        if code and code != last_code:
            timeline.append((e["abs_time"], code))
            last_code = code
    return timeline


def strength_at(timeline: list[tuple], t: float) -> str:
    """Situation code active at time t. Defaults to full-strength 5v5 if no
    events have occurred yet (reasonable: games start 5v5)."""
    code = FULL_STRENGTH_5V5
    for change_t, change_code in timeline:
        if change_t <= t:
            code = change_code
        else:
            break
    return code


def is_5v5(situation_code: str) -> bool:
    return situation_code == FULL_STRENGTH_5V5


def overlap_5v5_seconds(timeline: list[tuple], start: float, end: float) -> float:
    """Total seconds within [start, end) where strength state is 5v5.
    Walks the timeline's change points that fall inside the interval."""
    if end <= start:
        return 0.0

    # build the list of boundary points within [start, end]: interval start,
    # every change point inside the interval, interval end
    points = [start] + [t for t, _ in timeline if start < t < end] + [end]
    points = sorted(set(points))

    total = 0.0
    for i in range(len(points) - 1):
        seg_start, seg_end = points[i], points[i + 1]
        code = strength_at(timeline, seg_start)
        if is_5v5(code):
            total += seg_end - seg_start
    return total
