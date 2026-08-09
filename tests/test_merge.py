from douban_movies.crawler import merge_records
from douban_movies.models import MovieRecord


def test_merge_sources_and_keep_larger_vote_snapshot() -> None:
    first = MovieRecord(
        "1", "旧标题", 8.0, 100, "u1", {"电影"}, {"a"}, {"A"}
    )
    second = MovieRecord(
        "1", "新标题", 8.1, 120, "u2", {"电视剧"}, {"b"}, {"B"}
    )
    merged = merge_records([first, second])
    assert len(merged) == 1
    assert merged[0].title == "新标题"
    assert merged[0].rating_count == 120
    assert merged[0].source_ids == {"a", "b"}
    assert merged[0].kinds == {"电影", "电视剧"}
