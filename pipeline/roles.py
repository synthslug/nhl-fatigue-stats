"""
Opponent role weighting.

Weight is derived from the opponent's ice-time rank within their own team
for that game -- a top-pair D-man or top-line forward gets weight near 1.0,
a 4th-liner gets weight near the floor. This uses the same TOI extraction
already built for FPI (nhl_api.extract_player_toi), so no new data source.
"""


def compute_role_weights(team_toi_map: dict, floor: float = 0.15) -> dict:
    """
    team_toi_map: {player_id: toi_minutes} for ONE team in ONE game (skaters only)
    Returns {player_id: weight in [floor, 1.0]}, weight 1.0 = highest TOI on
    the team that game, weight floor = lowest.
    """
    if not team_toi_map:
        return {}
    ranked = sorted(team_toi_map.items(), key=lambda kv: kv[1], reverse=True)
    n = len(ranked)
    weights = {}
    for i, (pid, _toi) in enumerate(ranked):
        if n == 1:
            weights[pid] = 1.0
        else:
            frac = i / (n - 1)  # 0 for top TOI, 1 for lowest
            weights[pid] = 1.0 - frac * (1.0 - floor)
    return weights
