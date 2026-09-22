from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import load_settings
from app.db import create_engine_from_settings, create_session_factory
from app.import_legacy import import_legacy_city
from app.repositories.postgres_city import PostgresCityRepository


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a legacy JSON Research Graph City into PostgreSQL.")
    parser.add_argument("--prefix", choices=["research", "seeded"], required=True)
    parser.add_argument("--processed-dir", type=Path, default=Path(__file__).resolve().parents[2] / "data" / "processed")
    parser.add_argument("--replace", action="store_true", help="Accepted for explicit CLI intent; imports are idempotent.")
    args = parser.parse_args()

    engine = create_engine_from_settings(load_settings())
    repository = PostgresCityRepository(create_session_factory(engine))
    counts = import_legacy_city(args.processed_dir, args.prefix, repository)
    print(
        f"Imported {args.prefix}: {counts.paper_count} papers, {counts.edge_count} edges, "
        f"{counts.building_count} buildings, {counts.floor_count} floors, "
        f"{counts.bridge_count} bridges, {counts.street_count} streets, "
        f"{counts.community_count} communities"
    )


if __name__ == "__main__":
    main()
