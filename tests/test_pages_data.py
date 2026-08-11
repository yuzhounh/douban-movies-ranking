from scripts.build_pages_data import build_payload


def _record(subject_id: str, sources: list[str]) -> dict:
    return {
        "id": subject_id,
        "title": f"作品 {subject_id}",
        "rating": 8.0,
        "rating_count": 100,
        "url": f"https://movie.douban.com/subject/{subject_id}/",
        "source_doulist_ids": " / ".join(sources),
        "crawled_at": "2026-08-11T00:00:00+08:00",
    }


def _source(source_id: str, section: str, tab: str, filter_name: str, value: str) -> dict:
    return {
        "id": source_id,
        "navigation": {
            "section": section,
            "tab": tab,
            "filter": filter_name,
            "value": value,
        },
    }


def test_build_payload_flattens_navigation_and_aggregates_all() -> None:
    records = [
        _record("1", ["movie_default", "movie_type_all", "movie_comedy", "hot_all"]),
        _record("2", ["movie_comedy", "hot_cn"]),
        _record("3", ["movie_action"]),
        _record("4", ["category_drama", "category_comedy"]),
        _record("5", ["category_comedy", "top250"]),
    ]
    summary = {
        "sources": [
            _source("movie_default", "选电影", "全部", "全部", "全部"),
            _source("movie_type_all", "选电影", "全部", "类型", "全部"),
            _source("movie_comedy", "选电影", "全部", "类型", "喜剧"),
            _source("movie_action", "选电影", "全部", "类型", "动作"),
            _source("hot_all", "选电影", "热门电影", "子榜", "全部"),
            _source("hot_cn", "选电影", "热门电影", "子榜", "华语"),
            _source("category_drama", "分类排行榜", "类型排行榜", "类型", "剧情"),
            _source("category_comedy", "分类排行榜", "类型排行榜", "类型", "喜剧"),
            _source("top250", "分类排行榜", "Top 250", "榜单", "Top 250"),
        ]
    }

    payload = build_payload(records, summary)
    navigation = payload["navigation"]
    sections = list(dict.fromkeys(item["section"] for item in navigation))
    assert sections == ["分类排行榜", "选电影"]

    movie_tabs = list(
        dict.fromkeys(item["tab"] for item in navigation if item["section"] == "选电影")
    )
    assert movie_tabs == ["全部", "类型", "热门电影"]

    by_path = {
        (item["section"], item["tab"], item["value"]): item["count"]
        for item in navigation
    }
    assert by_path[("选电影", "全部", "全部")] == 3
    assert by_path[("选电影", "类型", "全部")] == 3
    assert by_path[("选电影", "热门电影", "全部")] == 2
    assert by_path[("分类排行榜", "Top 250", "榜单")] == 1

    category_values = [
        item["value"]
        for item in navigation
        if item["section"] == "分类排行榜" and item["tab"] == "类型排行榜"
    ]
    assert category_values == ["喜剧", "剧情"]
