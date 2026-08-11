"""Build the compact, aggregated dataset consumed by the GitHub Pages site."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "output" / "log_score" / "douban_movies_ranked.json"
DEFAULT_SUMMARY = ROOT / "output" / "log_score" / "crawl_summary.json"
DEFAULT_OUTPUT = ROOT / "docs" / "data" / "movies.json"

SECTION_ORDER = {"分类排行榜": 0, "选电影": 1, "选剧集": 2}
TAB_ORDER = {
    "分类排行榜": {"类型排行榜": 0, "精选豆列": 1, "Top 250": 2},
    "选电影": {
        "全部": 0,
        "类型": 1,
        "地区": 2,
        "年代": 3,
        "排序": 4,
        "标签": 5,
        "热门电影": 6,
        "最新电影": 7,
        "豆瓣高分": 8,
        "冷门佳片": 9,
    },
    "选剧集": {
        "全部": 0,
        "类型": 1,
        "地区": 2,
        "年代": 3,
        "平台": 4,
        "排序": 5,
        "标签": 6,
        "最近热门剧集": 7,
        "最近热门综艺": 8,
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def _source_ids(record: dict) -> list[str]:
    return [
        source_id
        for source_id in record.get("source_doulist_ids", "").split(" / ")
        if source_id
    ]


def _map_navigation(navigation: dict) -> tuple[str, str, str | None, str] | None:
    section = navigation["section"]
    old_tab = navigation["tab"]
    old_filter = navigation["filter"]
    value = navigation["value"]
    group = navigation.get("group")

    if section in {"选电影", "选剧集"}:
        if old_tab == "全部":
            if old_filter == "全部":
                return None
            tab = old_filter
        else:
            tab = old_tab
        return section, tab, group, value

    if section == "分类排行榜":
        if old_tab == "Top 250":
            value = "榜单"
        return section, old_tab, group, value
    return None


def build_payload(records: list[dict], summary: dict) -> dict:
    raw_members: dict[str, set[int]] = defaultdict(set)
    for movie_index, record in enumerate(records):
        for source_id in _source_ids(record):
            raw_members[source_id].add(movie_index)

    leaves: dict[tuple[str, str, str | None, str], dict] = {}
    section_members: dict[str, set[int]] = defaultdict(set)
    for order, source in enumerate(summary.get("sources", [])):
        navigation = source.get("navigation")
        if not navigation:
            continue
        source_id = str(source["id"])
        members = raw_members.get(source_id, set())
        section_members[navigation["section"]].update(members)
        mapped = _map_navigation(navigation)
        if mapped is None:
            continue
        leaf = leaves.setdefault(
            mapped,
            {
                "section": mapped[0],
                "tab": mapped[1],
                "group": mapped[2],
                "value": mapped[3],
                "members": set(),
                "order": order,
            },
        )
        leaf["members"].update(members)
        leaf["order"] = min(leaf["order"], order)

    # “选电影/选剧集 → 全部 → 全部”是整个一级板块的并集。
    for section in ("选电影", "选剧集"):
        if section not in section_members:
            continue
        leaves[(section, "全部", None, "全部")] = {
            "section": section,
            "tab": "全部",
            "group": None,
            "value": "全部",
            "members": set(section_members.get(section, set())),
            "order": -1,
        }

    # 任何现有的三级“全部”都改为当前二级标签全部叶子的并集。
    tab_members: dict[tuple[str, str], set[int]] = defaultdict(set)
    for leaf in leaves.values():
        tab_members[(leaf["section"], leaf["tab"])].update(leaf["members"])
    for leaf in leaves.values():
        if leaf["value"] == "全部":
            leaf["members"] = set(tab_members[(leaf["section"], leaf["tab"])])

    def leaf_sort_key(leaf: dict) -> tuple:
        section = leaf["section"]
        tab = leaf["tab"]
        base = (
            SECTION_ORDER.get(section, 99),
            TAB_ORDER.get(section, {}).get(tab, 99),
        )
        if section == "分类排行榜":
            return (*base, -len(leaf["members"]), leaf["value"])
        return (
            *base,
            0 if leaf["value"] == "全部" else 1,
            leaf["order"],
        )

    ordered_leaves = sorted(leaves.values(), key=leaf_sort_key)
    navigation = []
    movie_sources: list[list[int]] = [[] for _ in records]
    for source_index, leaf in enumerate(ordered_leaves):
        entry = {
            "section": leaf["section"],
            "tab": leaf["tab"],
            "value": leaf["value"],
            "count": len(leaf["members"]),
        }
        if leaf["group"]:
            entry["group"] = leaf["group"]
        navigation.append(entry)
        for movie_index in leaf["members"]:
            movie_sources[movie_index].append(source_index)

    movies = [
        {
            "id": str(record["id"]),
            "title": record["title"],
            "rating": record["rating"],
            "rating_count": record["rating_count"],
            "url": record["url"],
            "sources": movie_sources[movie_index],
        }
        for movie_index, record in enumerate(records)
    ]
    return {
        "generated_at": records[0].get("crawled_at") if records else None,
        "formula": "score = (R - 2.5) * ln(v)",
        "count": len(movies),
        "navigation": navigation,
        "movies": movies,
    }


def main() -> None:
    args = parse_args()
    records = json.loads(args.input.read_text(encoding="utf-8"))
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    payload = build_payload(records, summary)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(
        f"Wrote {payload['count']:,} records and "
        f"{len(payload['navigation']):,} navigation entries to {args.output}"
    )


if __name__ == "__main__":
    main()
