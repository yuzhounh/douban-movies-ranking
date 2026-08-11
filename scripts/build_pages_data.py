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
        "标签": 4,
        "豆瓣高分": 5,
        "冷门佳片": 6,
    },
    "选剧集": {
        "全部": 0,
        "类型": 1,
        "地区": 2,
        "年代": 3,
        "平台": 4,
        "标签": 5,
    },
}

HIDDEN_TABS = {
    "选电影": {"排序", "热门电影", "最新电影"},
    "选剧集": {"排序", "最近热门剧集", "最近热门综艺"},
}

DECADE_LABELS = {
    "90年代": "1990年代",
    "80年代": "1980年代",
    "70年代": "1970年代",
    "60年代": "1960年代",
}

YEAR_ORDER = {
    value: order
    for order, value in enumerate(
        (
            "全部",
            "2020年代",
            "2026",
            "2025",
            "2024",
            "2023",
            "2022",
            "2021",
            "2020",
            "2019",
            "2010年代",
            "2000年代",
            "1990年代",
            "1980年代",
            "1970年代",
            "1960年代",
            "更早",
        )
    )
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
        if tab in HIDDEN_TABS[section]:
            return None
        value = DECADE_LABELS.get(value, value)
        if section == "选剧集" and tab == "类型" and value == "不限类型":
            value = "全部"
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

    # 类型排行榜新增一个三级“全部”，聚合该二级榜单的全部作品。
    category_type_members: set[int] = set()
    for leaf in leaves.values():
        if leaf["section"] == "分类排行榜" and leaf["tab"] == "类型排行榜":
            category_type_members.update(leaf["members"])
    if category_type_members:
        leaves[("分类排行榜", "类型排行榜", None, "全部")] = {
            "section": "分类排行榜",
            "tab": "类型排行榜",
            "group": None,
            "value": "全部",
            "members": category_type_members,
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
        value = leaf["value"]
        count = len(leaf["members"])
        if section == "分类排行榜":
            return (*base, 0 if value == "全部" else 1, -count, value)
        if tab == "年代":
            return (*base, YEAR_ORDER.get(value, 999), value)
        if section == "选电影":
            return (*base, 0 if value == "全部" else 1, -count, value)
        if section == "选剧集" and tab == "类型":
            group_order = {"全部": 0, "电视剧": 1, "综艺": 2}
            return (
                *base,
                group_order.get(leaf["group"], 99),
                0 if value == "全部" else 1,
                -count,
                value,
            )
        if section == "选剧集" and tab in {"地区", "标签"}:
            return (*base, 0 if value == "全部" else 1, -count, value)
        return (*base, 0 if value == "全部" else 1, leaf["order"])

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
