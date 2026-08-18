"""
Fatigue Induction Index (FII) -- combines all toll components, weighted by
opponent role, into a single per-60 rate stat.
"""

from dataclasses import dataclass


@dataclass
class FIIConfig:
    w_physical: float = 1.0        # per hit delivered
    w_shift_forced: float = 1.0    # per extra second of forced shift length
    w_pursuit: float = 1.5         # per forced-turnover pursuit
    w_zone_time: float = 0.05      # per second of defensive-zone time forced
    w_rush: float = 2.0            # per rush sequence forced
    role_floor: float = 0.15       # min opponent weight (see roles.py)


def combine_tolls(
    physical: dict, shift_forced: dict, pursuit: dict,
    zone_time: dict, rush: dict, role_weights: dict,
    cfg: FIIConfig = FIIConfig(),
) -> dict:
    """
    Returns {opponent_id: {"raw_toll": ..., "weighted_toll": ..., "role_weight": ...,
                            "components": {...}}}
    """
    all_opponents = set(physical) | set(shift_forced) | set(pursuit) | set(zone_time) | set(rush)
    out = {}
    for b in all_opponents:
        components = {
            "physical": physical.get(b, 0) * cfg.w_physical,
            "shift_forced": shift_forced.get(b, 0.0) * cfg.w_shift_forced,
            "pursuit": pursuit.get(b, 0) * cfg.w_pursuit,
            "zone_time": zone_time.get(b, 0.0) * cfg.w_zone_time,
            "rush": rush.get(b, 0) * cfg.w_rush,
        }
        raw = sum(components.values())
        weight = role_weights.get(b, cfg.role_floor)
        out[b] = {
            "raw_toll": round(raw, 3),
            "role_weight": round(weight, 3),
            "weighted_toll": round(raw * weight, 3),
            "components": {k: round(v, 3) for k, v in components.items()},
        }
    return out


def aggregate_fii(matchup_tolls: dict, shared_toi_seconds: dict) -> dict:
    """
    matchup_tolls: output of combine_tolls()
    shared_toi_seconds: {opponent_id: shared_5v5_seconds} from matchup.py

    Returns {"fii_per_60": float, "total_weighted_toll": float,
             "total_shared_toi_min": float, "by_opponent": matchup_tolls}
    """
    total_weighted = sum(v["weighted_toll"] for v in matchup_tolls.values())
    total_toi_min = sum(shared_toi_seconds.values()) / 60.0

    fii_per_60 = (total_weighted / total_toi_min) * 60.0 if total_toi_min > 0 else 0.0

    return {
        "fii_per_60": round(fii_per_60, 3),
        "total_weighted_toll": round(total_weighted, 3),
        "total_shared_toi_min": round(total_toi_min, 2),
        "by_opponent": matchup_tolls,
    }
