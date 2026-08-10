from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .models import MovieRecord

SUBJECT_RE = re.compile(r"movie\.douban\.com/subject/(\d+)")
VOTES_RE = re.compile(r"\(([\d,，]+)\s*人评价\)")


class ParseError(RuntimeError):
    pass


def parse_doulist_page(
    html: str,
    *,
    source_id: str,
    source_name: str,
    kind: str,
    page_url: str,
) -> tuple[list[MovieRecord], str | None]:
    soup = BeautifulSoup(html, "html.parser")
    if soup.select_one("form#captcha-form") or "sec.douban.com" in page_url:
        raise ParseError("豆瓣返回了验证码页面")

    items = soup.select(".doulist-item")
    if not items and ("异常请求" in soup.get_text() or "检测到有异常请求" in soup.get_text()):
        raise ParseError("豆瓣判定请求异常")

    records: list[MovieRecord] = []
    for item in items:
        link = None
        match = None
        for candidate in item.select('a[href*="movie.douban.com/subject/"]'):
            candidate_match = SUBJECT_RE.search(candidate.get("href", ""))
            if candidate_match and candidate.get_text(" ", strip=True):
                link = candidate
                match = candidate_match
                break
        if link is None or match is None:
            continue

        rating_node = item.select_one(".rating_nums")
        votes_match = VOTES_RE.search(item.get_text(" ", strip=True))
        if rating_node is None or votes_match is None:
            continue

        try:
            rating = float(rating_node.get_text(strip=True))
            rating_count = int(votes_match.group(1).replace(",", "").replace("，", ""))
        except ValueError:
            continue

        subject_id = match.group(1)
        genres: set[str] = set()
        abstract = item.select_one(".abstract")
        if abstract is not None:
            for line in abstract.get_text("\n").splitlines():
                label, separator, values = line.strip().partition(":")
                if separator and label.strip() == "类型":
                    genres.update(
                        genre.strip() for genre in values.split("/") if genre.strip()
                    )
                    break
        records.append(
            MovieRecord(
                subject_id=subject_id,
                title=link.get_text(" ", strip=True),
                rating=rating,
                rating_count=rating_count,
                url=f"https://movie.douban.com/subject/{subject_id}/",
                kinds={kind},
                source_ids={source_id},
                source_names={source_name},
                genres=genres,
            )
        )

    next_url = None
    for anchor in soup.select(".paginator a[href]"):
        if "后页" in anchor.get_text(" ", strip=True):
            next_url = urljoin(page_url, anchor["href"])
            break
    return records, next_url
