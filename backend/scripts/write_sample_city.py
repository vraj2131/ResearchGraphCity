from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.sample_data import write_sample_city


if __name__ == "__main__":
    processed_dir = Path(__file__).resolve().parents[2] / "data" / "processed"
    write_sample_city(processed_dir)
    print(f"Wrote sample processed city to {processed_dir}")
