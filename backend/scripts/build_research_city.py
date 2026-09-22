from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.openalex import build_city_from_openalex


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build processed Research Graph City data from OpenAlex.")
    parser.add_argument("--target-total", type=int, default=1000, help="Target number of unique OpenAlex works to ingest.")
    parser.add_argument("--per-query", type=int, default=100, help="OpenAlex page size, capped at 100 by the fetcher.")
    args = parser.parse_args()

    processed_dir = Path(__file__).resolve().parents[2] / "data" / "processed"
    city = build_city_from_openalex(processed_dir=processed_dir, per_query=args.per_query, target_total=args.target_total)
    print(
        f"Wrote Research Graph City: {len(city.vertices)} vertices, "
        f"{len(city.edges)} edges, {len(city.buildings)} buildings, "
        f"{len(city.floors)} floors, {len(city.bridges)} bridges, "
        f"{len(city.streets)} streets, {len(city.communities)} communities"
    )
