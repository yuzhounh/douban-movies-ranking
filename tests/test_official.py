from douban_movies.official import (
    CategoryType,
    discover_category_types,
    parse_category_items,
    parse_explore_items,
    parse_top250_page,
)


def test_discover_category_types() -> None:
    html = """
    <a href="/typerank?type_name=%E5%89%A7%E6%83%85&type=11">剧情</a>
    <a href="./typerank?type_name=%E5%96%9C%E5%89%A7&type=24">喜剧</a>
    """
    assert discover_category_types(html) == [
        CategoryType("11", "剧情"),
        CategoryType("24", "喜剧"),
    ]


def test_parse_category_items_records_complete_genres() -> None:
    records = parse_category_items(
        [
            {
                "id": "1291546",
                "title": "霸王别姬",
                "score": "9.6",
                "vote_count": 2_444_062,
                "types": ["剧情", "爱情", "同性"],
            }
        ],
        category=CategoryType("11", "剧情"),
    )
    assert records[0].rating_count == 2_444_062
    assert records[0].genres == {"剧情", "爱情", "同性"}
    assert records[0].source_ids == {"category:11"}


def test_parse_explore_items_uses_hidden_rating_count() -> None:
    records = parse_explore_items(
        [
            {
                "id": "26752088",
                "type": "movie",
                "title": "我不是药神",
                "rating": {"value": 9.0, "count": 2_369_099},
                "card_subtitle": "2018 / 中国大陆 / 剧情 喜剧 / 文牧野 / 徐峥 王传君",
            },
            {"type": "ad"},
        ],
        source_id="explore:类型:喜剧",
        source_name="选电影：类型=喜剧",
        selected_genre="喜剧",
    )
    assert len(records) == 1
    assert records[0].rating_count == 2_369_099
    assert records[0].genres == {"剧情", "喜剧"}


def test_parse_explore_items_accepts_tv_subjects() -> None:
    records = parse_explore_items(
        [
            {
                "id": "26849758",
                "type": "tv",
                "title": "长安十二时辰",
                "rating": {"value": 8.1, "count": 518_751},
                "card_subtitle": "2019 / 中国大陆 / 剧情 悬疑 古装",
            },
            {"id": "1", "type": "movie", "title": "不是剧集"},
        ],
        source_id="explore:tv:test",
        source_name="选剧集：类型/电视剧/剧情",
        support_type="tv",
        selected_genre="剧情",
    )
    assert len(records) == 1
    assert records[0].kinds == {"剧集"}
    assert records[0].genres == {"剧情", "悬疑", "古装"}


def test_parse_top250_page() -> None:
    html = """
    <ol class="grid_view"><li><div class="item">
      <div class="hd"><a href="https://movie.douban.com/subject/1292052/">
        <span class="title">肖申克的救赎</span></a></div>
      <div class="bd"><p>导演：弗兰克<br>1994 / 美国 / 剧情 犯罪</p>
        <div class="star"><span class="rating_num">9.7</span><span>3312903人评价</span></div>
      </div>
    </div></li></ol>
    """
    records = parse_top250_page(html)
    assert len(records) == 1
    assert records[0].subject_id == "1292052"
    assert records[0].genres == {"剧情", "犯罪"}
    assert records[0].source_ids == {"top250"}
