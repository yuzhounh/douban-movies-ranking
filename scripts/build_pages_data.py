"""Build the compact dataset consumed by the GitHub Pages site."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "output" / "log_score" / "douban_movies_ranked.json"
DEFAULT_SUMMARY = ROOT / "output" / "log_score" / "crawl_summary.json"
DEFAULT_OUTPUT = ROOT / "docs" / "data" / "movies.json"

SECTION_ORDER = {"选电影": 0, "选剧集": 1, "分类排行榜": 2}
TAB_ORDER = {
    "选电影": {"全部": 0, "热门电影": 1, "最新电影": 2, "豆瓣高分": 3, "冷门佳片": 4},
    "选剧集": {"全部": 0, "最近热门剧集": 1, "最近热门综艺": 2},
    "分类排行榜": {"Top 250": 0, "类型排行榜": 1, "精选豆列": 2},
}
FILTER_ORDER = {
    "全部": 0,
    "类型": 1,
    "地区": 2,
    "年代": 3,
    "平台": 4,
    "排序": 5,
    "标签": 6,
    "子榜": 7,
    "榜单": 8,
    "豆列": 9,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = json.loads(args.input.read_text(encoding="utf-8"))
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    navigation_sources = []
    for order, source in enumerate(summary.get("sources", [])):
        navigation = source.get("navigation")
        if not navigation:
            continue
        navigation_sources.append(
            {
                "source_id": str(source["id"]),
                "section": navigation["section"],
                "tab": navigation["tab"],
                "filter": navigation["filter"],
                "value": navigation["value"],
                "group": navigation.get("group"),
                "count": int(source.get("extracted_records", 0)),
                "order": order,
            }
        )
    navigation_sources.sort(
        key=lambda source: (
            SECTION_ORDER.get(source["section"], 99),
            TAB_ORDER.get(source["section"], {}).get(source["tab"], 99),
            FILTER_ORDER.get(source["filter"], 99),
            source["order"],
        )
    )
    source_indexes = {
        source.pop("source_id"): index for index, source in enumerate(navigation_sources)
    }
    movies = [
        {
            "id": str(record["id"]),
            "title": record["title"],
            "rating": record["rating"],
            "rating_count": record["rating_count"],
            "url": record["url"],
            "sources": sorted(
                source_indexes[source_id]
                for source_id in record.get("source_doulist_ids", "").split(" / ")
                if source_id in source_indexes
            ),
        }
        for record in records
    ]

    payload = {
        "generated_at": records[0].get("crawled_at") if records else None,
        "formula": "score = (R - 2.5) * ln(v)",
        "count": len(movies),
        "navigation": navigation_sources,
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
