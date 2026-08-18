"""
Diagnostic only -- not part of the regular pipeline. Prints the RAW shape of
a real boxscore response so we can stop guessing at field names from
secondhand blog posts and fix pipeline/nhl_api.py against ground truth.

Usage: python -m backend.debug_boxscore --date 2026-02-01
"""

import argparse
import json
from pipeline import nhl_api


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="YYYY-MM-DD, a date with completed games")
    args = ap.parse_args()

    games = nhl_api.fetch_schedule_by_date(args.date)
    finished = [g for g in games if g.get("gameState") in ("OFF", "FINAL")]
    if not finished:
        print(f"No finished games found on {args.date}. Games found: {games}")
        return

    game_id = finished[0]["id"]
    print(f"Using game_id={game_id} ({finished[0].get('awayTeam', {}).get('abbrev')} @ "
          f"{finished[0].get('homeTeam', {}).get('abbrev')})\n")

    box = nhl_api.fetch_boxscore(game_id)

    print("=== top-level boxscore keys ===")
    print(list(box.keys()))

    pbgs = box.get("playerByGameStats", {})
    print("\n=== playerByGameStats top-level keys ===")
    print(list(pbgs.keys()))

    for side_key, side_val in pbgs.items():
        print(f"\n=== playerByGameStats.{side_key} keys ===")
        if isinstance(side_val, dict):
            print(list(side_val.keys()))
            for pos_key, pos_list in side_val.items():
                if pos_list:
                    print(f"\n--- sample player from {side_key}.{pos_key}[0] (RAW, full object) ---")
                    print(json.dumps(pos_list[0], indent=2))
                    break  # one sample is enough to see the shape
        else:
            print(f"(unexpected type: {type(side_val)})")


if __name__ == "__main__":
    main()
