"""
Diagnostic only. Verifies the field-name assumptions in pipeline/pbp.py and
pipeline/shifts.py against a REAL play-by-play + shift-chart response, the
same way debug_boxscore.py verified nhl_api.py. Prints one raw sample of
each event type we actually use (hit, giveaway, takeaway, a shot type,
faceoff, penalty), the distinct situationCode values seen (for the 5v5
detection in strength.py), and one raw shift-chart record.

Usage: python -m backend.debug_pbp_shifts --date 2026-02-01
"""

import argparse
import json
from pipeline import nhl_api

WANTED_TYPES = [
    "hit", "giveaway", "takeaway", "shot-on-goal", "missed-shot",
    "blocked-shot", "goal", "faceoff", "penalty",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="YYYY-MM-DD, a date with completed games")
    args = ap.parse_args()

    games = nhl_api.fetch_schedule_by_date(args.date)
    finished = [g for g in games if g.get("gameState") in ("OFF", "FINAL")]
    if not finished:
        print(f"No finished games found on {args.date}.")
        return

    game_id = finished[0]["id"]
    print(f"Using game_id={game_id} ({finished[0].get('awayTeam', {}).get('abbrev')} @ "
          f"{finished[0].get('homeTeam', {}).get('abbrev')})\n")

    # --- play-by-play ---
    raw_plays = nhl_api.fetch_play_by_play(game_id)
    print(f"Total plays in game: {len(raw_plays)}")

    seen_types = sorted(set(p.get("typeDescKey") for p in raw_plays))
    print(f"\nAll distinct typeDescKey values seen: {seen_types}\n")

    situation_codes = sorted(set(p.get("situationCode") for p in raw_plays if p.get("situationCode")))
    print(f"All distinct situationCode values seen: {situation_codes}")
    print("(strength.py currently treats '1551' as full-strength 5v5 -- confirm that code is in this list)\n")

    zone_codes = set()
    for p in raw_plays:
        zc = (p.get("details") or {}).get("zoneCode")
        if zc:
            zone_codes.add(zc)
    print(f"All distinct zoneCode values seen: {sorted(zone_codes)}")
    print("(tolls.py currently expects 'O'/'D'/'N' -- confirm these match)\n")

    for t in WANTED_TYPES:
        sample = next((p for p in raw_plays if p.get("typeDescKey") == t), None)
        print(f"--- sample raw play: typeDescKey='{t}' ---")
        if sample is None:
            print(f"  (none found in this game -- try a different date if you need to verify this type)\n")
            continue
        print(json.dumps(sample, indent=2))
        print()

    # --- shift chart ---
    raw_shifts = nhl_api.fetch_shift_chart(game_id)
    print(f"\nTotal shift records: {len(raw_shifts)}")
    if raw_shifts:
        print("--- sample raw shift record ---")
        print(json.dumps(raw_shifts[0], indent=2))


if __name__ == "__main__":
    main()
