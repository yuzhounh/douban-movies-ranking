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


def _source(
    source_id: str,
    section: str,
    tab: str,
    filter_name: str,
    value: str,
    group: str | None = None,
) -> dict:
    return {
        "id": source_id,
        "navigation": {
            "section": section,
            "tab": tab,
            "filter": filter_name,
            "value": value,
            "group": group,
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
    assert movie_tabs == ["全部", "类型"]

    by_path = {
        (item["section"], item["tab"], item["value"]): item["count"]
        for item in navigation
    }
    assert by_path[("选电影", "全部", "全部")] == 3
    assert by_path[("选电影", "类型", "全部")] == 3
    assert by_path[("分类排行榜", "Top 250", "榜单")] == 1
    assert by_path[("分类排行榜", "类型排行榜", "全部")] == 2

    category_values = [
        item["value"]
        for item in navigation
        if item["section"] == "分类排行榜" and item["tab"] == "类型排行榜"
    ]
    assert category_values == ["全部", "喜剧", "剧情"]


def test_removed_tabs_are_hidden_but_still_contribute_to_section_all() -> None:
    records = [
        _record("1", ["movie_type"]),
        _record("2", ["movie_sort"]),
        _record("3", ["movie_hot"]),
        _record("4", ["tv_region"]),
        _record("5", ["tv_sort"]),
        _record("6", ["tv_recent"]),
    ]
    summary = {
        "sources": [
            _source("movie_type", "选电影", "全部", "类型", "喜剧"),
            _source("movie_sort", "选电影", "全部", "排序", "综合排序"),
            _source("movie_hot", "选电影", "热门电影", "子榜", "全部"),
            _source("tv_region", "选剧集", "全部", "地区", "华语"),
            _source("tv_sort", "选剧集", "全部", "排序", "综合排序"),
            _source("tv_recent", "选剧集", "最近热门剧集", "子榜", "综合"),
        ]
    }

    navigation = build_payload(records, summary)["navigation"]
    paths = {(item["section"], item["tab"], item["value"]): item["count"] for item in navigation}
    assert ("选电影", "排序", "综合排序") not in paths
    assert ("选电影", "热门电影", "全部") not in paths
    assert ("选剧集", "排序", "综合排序") not in paths
    assert ("选剧集", "最近热门剧集", "综合") not in paths
    assert paths[("选电影", "全部", "全部")] == 3
    assert paths[("选剧集", "全部", "全部")] == 3


def test_decades_are_normalized_and_years_use_chronological_order() -> None:
    source_ids = ["all", "d2020", "d2010", "d90", "d80", "older"]
    records = [_record(str(index), [source_id]) for index, source_id in enumerate(source_ids)]
    summary = {
        "sources": [
            _source("all", "选电影", "全部", "年代", "全部"),
            _source("d2010", "选电影", "全部", "年代", "2010年代"),
            _source("d90", "选电影", "全部", "年代", "90年代"),
            _source("older", "选电影", "全部", "年代", "更早"),
            _source("d80", "选电影", "全部", "年代", "80年代"),
            _source("d2020", "选电影", "全部", "年代", "2020年代"),
        ]
    }

    values = [
        item["value"]
        for item in build_payload(records, summary)["navigation"]
        if item["section"] == "选电影" and item["tab"] == "年代"
    ]
    assert values == ["全部", "2020年代", "2010年代", "1990年代", "1980年代", "更早"]


def test_2020_decade_follows_individual_years() -> None:
    records = [
        _record("1", ["all"]),
        _record("2", ["year_2026"]),
        _record("3", ["year_2019"]),
        _record("4", ["decade_2020"]),
        _record("5", ["decade_2010"]),
    ]
    summary = {
        "sources": [
            _source("all", "选剧集", "全部", "年代", "全部"),
            _source("decade_2020", "选剧集", "全部", "年代", "2020年代"),
            _source("year_2026", "选剧集", "全部", "年代", "2026"),
            _source("year_2019", "选剧集", "全部", "年代", "2019"),
            _source("decade_2010", "选剧集", "全部", "年代", "2010年代"),
        ]
    }

    values = [
        item["value"]
        for item in build_payload(records, summary)["navigation"]
        if item["section"] == "选剧集" and item["tab"] == "年代"
    ]
    assert values == ["全部", "2026", "2019", "2020年代", "2010年代"]


def test_empty_movie_tags_are_removed() -> None:
    records = [_record("1", ["nonempty_tag"])]
    summary = {
        "sources": [
            _source("nonempty_tag", "选电影", "全部", "标签", "推理", "推荐标签"),
            _source("empty_tag", "选电影", "全部", "标签", "空标签", "推荐标签"),
        ]
    }

    payload = build_payload(records, summary)
    values = [
        item["value"]
        for item in payload["navigation"]
        if item["section"] == "选电影" and item["tab"] == "标签"
    ]
    assert values == ["推理"]
    assert payload["formula"] == "综合评分 = (评分 - 2.5) * ln(评价人数)"


def test_movie_values_and_tv_requested_groups_are_sorted_by_count() -> None:
    records = [
        _record("1", ["movie_a", "movie_b", "tv_all", "tv_drama", "tv_cn", "tv_tag_a"]),
        _record("2", ["movie_b", "tv_drama", "tv_us", "tv_tag_a"]),
        _record("3", ["movie_b", "tv_comedy", "tv_us", "tv_tag_b"]),
    ]
    summary = {
        "sources": [
            _source("movie_a", "选电影", "全部", "类型", "甲"),
            _source("movie_b", "选电影", "全部", "类型", "乙"),
            _source("tv_all", "选剧集", "全部", "类型", "不限类型", "全部"),
            _source("tv_drama", "选剧集", "全部", "类型", "剧情", "电视剧"),
            _source("tv_comedy", "选剧集", "全部", "类型", "喜剧", "电视剧"),
            _source("tv_cn", "选剧集", "全部", "地区", "华语"),
            _source("tv_us", "选剧集", "全部", "地区", "欧美"),
            _source("tv_tag_a", "选剧集", "全部", "标签", "标签甲", "推荐标签"),
            _source("tv_tag_b", "选剧集", "全部", "标签", "标签乙", "推荐标签"),
        ]
    }
    navigation = build_payload(records, summary)["navigation"]

    movie_values = [item["value"] for item in navigation if item["section"] == "选电影" and item["tab"] == "类型"]
    assert movie_values == ["乙", "甲"]

    tv_type_values = [item["value"] for item in navigation if item["section"] == "选剧集" and item["tab"] == "类型"]
    assert tv_type_values == ["全部", "剧情", "喜剧"]

    tv_region_values = [item["value"] for item in navigation if item["section"] == "选剧集" and item["tab"] == "地区"]
    assert tv_region_values == ["欧美", "华语"]

    tv_tag_values = [item["value"] for item in navigation if item["section"] == "选剧集" and item["tab"] == "标签"]
    assert tv_tag_values == ["标签甲", "标签乙"]
