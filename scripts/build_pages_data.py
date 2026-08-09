"""Build the compact dataset consumed by the GitHub Pages site."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "output" / "log_score" / "douban_movies_ranked.json"
DEFAULT_OUTPUT = ROOT / "docs" / "data" / "movies.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = json.loads(args.input.read_text(encoding="utf-8"))
    movies = [
        {
            "id": str(record["id"]),
            "title": record["title"],
            "rating": record["rating"],
            "rating_count": record["rating_count"],
            "url": record["url"],
        }
        for record in records
    ]

    payload = {
        "generated_at": records[0].get("crawled_at") if records else None,
        "formula": "score = (R - 2.5) * ln(v)",
        "count": len(movies),
        "movies": movies,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"Wrote {len(movies):,} records to {args.output}")


if __name__ == "__main__":
    main()
