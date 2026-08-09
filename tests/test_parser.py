from pathlib import Path

import pytest

from douban_movies.parser import ParseError, parse_doulist_page


def test_parse_doulist_page() -> None:
    fixture = Path(__file__).parent / "fixtures" / "doulist_page.html"
    records, next_url = parse_doulist_page(
        fixture.read_text(encoding="utf-8"),
        source_id="240962",
        source_name="高分电影",
        kind="电影",
        page_url="https://www.douban.com/doulist/240962/",
    )
    assert [record.subject_id for record in records] == ["1292052", "1291546"]
    assert records[0].rating == 9.7
    assert records[0].rating_count == 3_312_447
    assert records[1].rating_count == 2_445_001
    assert next_url == "https://www.douban.com/doulist/240962/?start=25&sort=seq"


def test_reject_captcha_page() -> None:
    with pytest.raises(ParseError, match="验证码"):
        parse_doulist_page(
            '<html><form id="captcha-form"></form></html>',
            source_id="240962",
            source_name="高分电影",
            kind="电影",
            page_url="https://www.douban.com/doulist/240962/",
        )
