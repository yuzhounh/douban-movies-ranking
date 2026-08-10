from __future__ import annotations

import csv
import json
from pathlib import Path

from .models import MovieRecord

FIELDNAMES = [
    "rank",
    "id",
    "title",
    "rating",
    "rating_count",
    "comprehensive_score",
    "kind",
    "genres",
    "url",
    "source_doulist_ids",
    "source_doulists",
    "crawled_at",
]


def write_outputs(
    records: list[MovieRecord], *, output_dir: Path, crawled_at: str
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [record.to_dict(crawled_at) for record in records]
    csv_path = output_dir / "douban_movies_ranked.csv"
    json_path = output_dir / "douban_movies_ranked.json"

    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    json_path.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return csv_path, json_path


def write_summary(summary: dict, *, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "crawl_summary.json"
    path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path
