from __future__ import annotations

import json
import hashlib
import logging
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

from bs4 import BeautifulSoup

from .crawler import DoubanCrawler
from .models import MovieRecord
from .parser import ParseError, SUBJECT_RE

LOGGER = logging.getLogger(__name__)
TOP250_VOTES_RE = re.compile(r"([\d,，]+)\s*人评价")


@dataclass(frozen=True)
class CategoryType:
    id: str
    name: str


def _source_record(
    *,
    subject_id: str,
    title: str,
    rating: float,
    rating_count: int,
    source_id: str,
    source_name: str,
    genres: set[str] | None = None,
) -> MovieRecord:
    return MovieRecord(
        subject_id=subject_id,
        title=title,
        rating=rating,
        rating_count=rating_count,
        url=f"https://movie.douban.com/subject/{subject_id}/",
        kinds={"电影"},
        source_ids={source_id},
        source_names={source_name},
        genres=genres or set(),
    )


def discover_category_types(html: str) -> list[CategoryType]:
    soup = BeautifulSoup(html, "html.parser")
    discovered: dict[str, CategoryType] = {}
    for anchor in soup.select('a[href*="typerank"]'):
        href = anchor.get("href", "")
        query = parse_qs(urlparse(urljoin("https://movie.douban.com", href)).query)
        type_id = query.get("type", [""])[0]
        type_name = query.get("type_name", [""])[0] or anchor.get_text(" ", strip=True)
        if type_id.isdigit() and type_name:
            discovered[type_id] = CategoryType(type_id, type_name)
    if not discovered:
        raise ParseError("未能从分类排行榜页面发现电影类型")
    return sorted(discovered.values(), key=lambda item: int(item.id))


def parse_category_items(
    items: list[dict], *, category: CategoryType
) -> list[MovieRecord]:
    records: list[MovieRecord] = []
    for item in items:
        subject_id = str(item.get("id", ""))
        try:
            rating = float(item["score"])
            rating_count = int(item["vote_count"])
        except (KeyError, TypeError, ValueError):
            continue
        if not subject_id or not item.get("title") or rating_count <= 0:
            continue
        genres = {str(value).strip() for value in item.get("types", []) if str(value).strip()}
        genres.add(category.name)
        records.append(
            _source_record(
                subject_id=subject_id,
                title=str(item["title"]),
                rating=rating,
                rating_count=rating_count,
                source_id=f"category:{category.id}",
                source_name=f"分类排行榜：{category.name}",
                genres=genres,
            )
        )
    return records


def parse_top250_page(html: str) -> list[MovieRecord]:
    soup = BeautifulSoup(html, "html.parser")
    records: list[MovieRecord] = []
    for item in soup.select(".grid_view .item"):
        link = item.select_one('.hd a[href*="movie.douban.com/subject/"]')
        title_node = item.select_one(".hd .title")
        rating_node = item.select_one(".rating_num")
        if link is None or title_node is None or rating_node is None:
            continue
        match = SUBJECT_RE.search(link.get("href", ""))
        votes_match = TOP250_VOTES_RE.search(item.get_text(" ", strip=True))
        if match is None or votes_match is None:
            continue
        try:
            rating = float(rating_node.get_text(strip=True))
            rating_count = int(votes_match.group(1).replace(",", "").replace("，", ""))
        except ValueError:
            continue

        genres: set[str] = set()
        info = item.select_one(".bd p")
        if info is not None:
            detail_line = next(
                (line.strip() for line in reversed(info.get_text("\n").splitlines()) if "/" in line),
                "",
            )
            if detail_line:
                genres = {value for value in detail_line.split("/")[-1].strip().split() if value}

        records.append(
            _source_record(
                subject_id=match.group(1),
                title=title_node.get_text(" ", strip=True),
                rating=rating,
                rating_count=rating_count,
                source_id="top250",
                source_name="豆瓣电影 Top 250",
                genres=genres,
            )
        )
    return records


def _genres_from_card_subtitle(subtitle: str) -> set[str]:
    parts = [part.strip() for part in subtitle.split(" / ")]
    if len(parts) < 3:
        return set()
    return {genre for genre in parts[2].split() if genre}


def parse_explore_items(
    items: list[dict],
    *,
    source_id: str,
    source_name: str,
    selected_genre: str | None = None,
) -> list[MovieRecord]:
    records: list[MovieRecord] = []
    for item in items:
        if item.get("type") != "movie" or not item.get("id"):
            continue
        rating_data = item.get("rating") or {}
        try:
            rating = float(rating_data["value"])
            rating_count = int(rating_data["count"])
        except (KeyError, TypeError, ValueError):
            continue
        if rating_count <= 0 or not item.get("title"):
            continue
        genres = _genres_from_card_subtitle(str(item.get("card_subtitle", "")))
        if selected_genre:
            genres.add(selected_genre)
        records.append(
            _source_record(
                subject_id=str(item["id"]),
                title=str(item["title"]),
                rating=rating,
                rating_count=rating_count,
                source_id=source_id,
                source_name=source_name,
                genres=genres,
            )
        )
    return records


class OfficialSourcesCrawler:
    def __init__(self, crawler: DoubanCrawler) -> None:
        self.crawler = crawler
        self.json_headers = {
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://movie.douban.com/",
        }

    @staticmethod
    def _url(base: str, params: dict[str, object]) -> str:
        return f"{base}?{urlencode(params)}"

    @staticmethod
    def _stable_id(*parts: str) -> str:
        raw = "\0".join(parts).encode("utf-8")
        return hashlib.sha1(raw).hexdigest()[:16]

    def crawl_category_rankings(
        self, config: dict, *, max_pages: int | None = None
    ) -> tuple[list[MovieRecord], list[dict]]:
        entry_url = config.get(
            "url",
            "https://movie.douban.com/typerank?type_name=剧情&type=11&interval_id=100:90&action=",
        )
        html = self.crawler.get_text("official/category_types.html", entry_url)
        categories = discover_category_types(html)
        intervals = config.get(
            "intervals",
            ["100:90", "90:80", "80:70", "70:60", "60:50", "50:40", "40:30", "30:20", "20:10", "10:0"],
        )
        page_size = int(config.get("page_size", 1000))
        all_records: list[MovieRecord] = []
        summaries: list[dict] = []

        for category in categories:
            category_records: list[MovieRecord] = []
            for interval in intervals:
                start = 0
                page_number = 0
                while True:
                    if max_pages is not None and page_number >= max_pages:
                        break
                    page_number += 1
                    url = self._url(
                        "https://movie.douban.com/j/chart/top_list",
                        {
                            "type": category.id,
                            "interval_id": interval,
                            "action": "",
                            "start": start,
                            "limit": page_size,
                        },
                    )
                    upper, lower = interval.split(":", 1)
                    cache_key = f"official/category_{category.id}_{upper}_{lower}_start_{start}.json"
                    payload = self.crawler.get_json(cache_key, url, headers=self.json_headers)
                    if not isinstance(payload, list):
                        raise ParseError(f"分类排行榜接口结构异常：{category.name}")
                    page_records = parse_category_items(payload, category=category)
                    category_records.extend(page_records)
                    LOGGER.info(
                        "分类排行榜 %s %s：第 %d 页 %d 条",
                        category.name,
                        interval,
                        page_number,
                        len(page_records),
                    )
                    if len(payload) < page_size:
                        break
                    start += page_size
            all_records.extend(category_records)
            category_url = self._url(
                "https://movie.douban.com/typerank",
                {
                    "type_name": category.name,
                    "type": category.id,
                    "interval_id": intervals[0],
                    "action": "",
                },
            )
            summaries.append(
                {
                    "id": f"category:{category.id}",
                    "name": f"分类排行榜：{category.name}",
                    "kind": "电影",
                    "url": category_url,
                    "extracted_records": len(category_records),
                }
            )
        return all_records, summaries

    def crawl_top250(
        self, config: dict, *, max_pages: int | None = None
    ) -> tuple[list[MovieRecord], list[dict]]:
        base_url = config.get("url", "https://movie.douban.com/top250")
        page_size = int(config.get("page_size", 25))
        total = int(config.get("total", 250))
        records: list[MovieRecord] = []
        page_count = 0
        for start in range(0, total, page_size):
            if max_pages is not None and page_count >= max_pages:
                break
            page_count += 1
            url = self._url(base_url, {"start": start, "filter": ""})
            html = self.crawler.get_text(f"official/top250_start_{start}.html", url)
            page_records = parse_top250_page(html)
            records.extend(page_records)
            LOGGER.info("豆瓣电影 Top 250：第 %d 页 %d 条", page_count, len(page_records))
        return records, [
            {
                "id": "top250",
                "name": "豆瓣电影 Top 250",
                "kind": "电影",
                "url": base_url,
                "extracted_records": len(records),
            }
        ]

    def _explore_payload(
        self,
        *,
        cache_key: str,
        selected_categories: dict[str, str],
        tags: list[str],
        start: int,
        count: int,
        sort: str | None = None,
    ) -> dict:
        params: dict[str, object] = {
            "type": "movie",
            "refresh": 0,
            "start": start,
            "count": count,
            "selected_categories": json.dumps(selected_categories, ensure_ascii=False, separators=(",", ":")),
            "uncollect": "false",
            "score_range": "0,10",
        }
        if tags:
            params["tags"] = ",".join(tags)
        if sort:
            params["sort"] = sort
        url = self._url("https://m.douban.com/rexxar/api/v2/movie/recommend", params)
        payload = self.crawler.get_json(
            cache_key,
            url,
            headers={**self.json_headers, "Referer": "https://movie.douban.com/explore"},
        )
        if not isinstance(payload, dict):
            raise ParseError("选电影接口结构异常")
        return payload

    def _crawl_explore_filter(
        self,
        *,
        facet_type: str,
        value: str,
        selected_categories: dict[str, str],
        page_size: int,
        max_items: int,
        max_pages: int | None,
    ) -> tuple[list[MovieRecord], dict]:
        safe_id = self._stable_id(facet_type, value)
        records: list[MovieRecord] = []
        start = 0
        page_number = 0
        total = max_items
        while start < min(total, max_items):
            if max_pages is not None and page_number >= max_pages:
                break
            page_number += 1
            count = min(page_size, max_items - start)
            payload = self._explore_payload(
                cache_key=f"official/explore_{safe_id}_start_{start}.json",
                selected_categories=selected_categories,
                tags=[value],
                start=start,
                count=count,
            )
            total = int(payload.get("total") or 0)
            items = payload.get("items") or []
            if not isinstance(items, list):
                raise ParseError(f"选电影条目结构异常：{facet_type}={value}")
            page_records = parse_explore_items(
                items,
                source_id=f"explore:{facet_type}:{value}",
                source_name=f"选电影：{facet_type}={value}",
                selected_genre=value if facet_type == "类型" else None,
            )
            records.extend(page_records)
            LOGGER.info(
                "选电影 %s=%s：第 %d 页 %d 条（接口总数 %d）",
                facet_type,
                value,
                page_number,
                len(page_records),
                total,
            )
            if not items or len(items) < count:
                break
            start += count
        summary = {
            "id": f"explore:{facet_type}:{value}",
            "name": f"选电影：{facet_type}={value}",
            "kind": "电影",
            "url": "https://movie.douban.com/explore",
            "extracted_records": len(records),
            "reported_total": total,
            "max_items": max_items,
        }
        return records, summary

    def _crawl_recent_hot(
        self,
        *,
        page_size: int,
        max_items: int,
        max_pages: int | None,
    ) -> tuple[list[MovieRecord], list[dict]]:
        headers = {**self.json_headers, "Referer": "https://movie.douban.com/explore"}
        seed_url = self._url(
            "https://m.douban.com/rexxar/api/v2/subject/recent_hot/movie",
            {"start": 0, "limit": min(page_size, max_items)},
        )
        seed = self.crawler.get_json("official/explore_recent_hot_seed.json", seed_url, headers=headers)
        if not isinstance(seed, dict):
            raise ParseError("选电影热门子榜接口结构异常")

        records: list[MovieRecord] = []
        summaries: list[dict] = []
        for main_tag in seed.get("tags") or []:
            category = str(main_tag.get("category", ""))
            title = str(main_tag.get("title", category))
            for subtype in main_tag.get("types") or []:
                subtype_name = str(subtype.get("type", ""))
                if not category or not subtype_name:
                    continue
                source_id = f"explore:recent:{category}:{subtype_name}"
                source_name = f"选电影：{title}/{subtype_name}"
                combo_records: list[MovieRecord] = []
                start = 0
                page_number = 0
                total = max_items
                while start < min(total, max_items):
                    if max_pages is not None and page_number >= max_pages:
                        break
                    page_number += 1
                    limit = min(page_size, max_items - start)
                    url = self._url(
                        "https://m.douban.com/rexxar/api/v2/subject/recent_hot/movie",
                        {
                            "start": start,
                            "limit": limit,
                            "category": category,
                            "type": subtype_name,
                        },
                    )
                    safe_id = self._stable_id(category, subtype_name)
                    payload = self.crawler.get_json(
                        f"official/explore_recent_{safe_id}_start_{start}.json",
                        url,
                        headers=headers,
                    )
                    if not isinstance(payload, dict):
                        raise ParseError(f"选电影热门子榜结构异常：{source_name}")
                    total = int(payload.get("total") or 0)
                    items = payload.get("items") or []
                    page_records = parse_explore_items(
                        items,
                        source_id=source_id,
                        source_name=source_name,
                    )
                    combo_records.extend(page_records)
                    if not items or len(items) < limit:
                        break
                    start += limit
                records.extend(combo_records)
                summaries.append(
                    {
                        "id": source_id,
                        "name": source_name,
                        "kind": "电影",
                        "url": "https://movie.douban.com/explore",
                        "extracted_records": len(combo_records),
                        "reported_total": total,
                        "max_items": max_items,
                    }
                )
        return records, summaries

    def crawl_explore(
        self, config: dict, *, max_pages: int | None = None
    ) -> tuple[list[MovieRecord], list[dict]]:
        page_size = int(config.get("page_size", 500))
        max_items = int(config.get("max_items_per_filter", 500))
        seed = self._explore_payload(
            cache_key="official/explore_seed.json",
            selected_categories={},
            tags=[],
            start=0,
            count=20,
        )
        facets: list[tuple[str, str, dict[str, str]]] = []
        for category in seed.get("recommend_categories") or []:
            facet_type = str(category.get("type", ""))
            for item in category.get("data") or []:
                value = str(item.get("text", ""))
                if not facet_type or not value or item.get("default") or value == "全部":
                    continue
                facets.append((facet_type, value, {facet_type: value}))

        filter_url = self._url(
            "https://m.douban.com/rexxar/api/v2/movie/recommend/filter_tags",
            {"type": "movie", "selected_categories": "{}"},
        )
        filter_payload = self.crawler.get_json(
            "official/explore_filter_tags.json",
            filter_url,
            headers={**self.json_headers, "Referer": "https://movie.douban.com/explore"},
        )
        if isinstance(filter_payload, dict):
            for group in filter_payload.get("tags") or []:
                facet_type = str(group.get("type", ""))
                if facet_type == "标签":
                    continue
                for value in group.get("tags") or []:
                    value = str(value)
                    if value and value != "全部":
                        facets.append((facet_type, value, {}))

        if config.get("include_recommended_tags", True):
            recommended = list(seed.get("recommend_tags") or []) + list(seed.get("bottom_recommend_tags") or [])
            for value in dict.fromkeys(str(tag) for tag in recommended if str(tag)):
                facets.append(("推荐标签", value, {}))

        deduplicated: dict[tuple[str, str], tuple[str, str, dict[str, str]]] = {
            (facet_type, value): (facet_type, value, selected)
            for facet_type, value, selected in facets
        }
        all_records: list[MovieRecord] = []
        summaries: list[dict] = []
        for facet_type, value, selected in deduplicated.values():
            records, summary = self._crawl_explore_filter(
                facet_type=facet_type,
                value=value,
                selected_categories=selected,
                page_size=page_size,
                max_items=max_items,
                max_pages=max_pages,
            )
            all_records.extend(records)
            summaries.append(summary)

        if config.get("include_recent_hot", True):
            recent_records, recent_summaries = self._crawl_recent_hot(
                page_size=page_size,
                max_items=max_items,
                max_pages=max_pages,
            )
            all_records.extend(recent_records)
            summaries.extend(recent_summaries)
        return all_records, summaries

    def crawl_all(
        self, config: dict, *, max_pages: int | None = None
    ) -> tuple[list[MovieRecord], list[dict]]:
        records: list[MovieRecord] = []
        summaries: list[dict] = []
        category_config = config.get("category_rankings", {})
        if category_config.get("enabled", True):
            batch, batch_summaries = self.crawl_category_rankings(
                category_config, max_pages=max_pages
            )
            records.extend(batch)
            summaries.extend(batch_summaries)
        top250_config = config.get("top250", {})
        if top250_config.get("enabled", True):
            batch, batch_summaries = self.crawl_top250(top250_config, max_pages=max_pages)
            records.extend(batch)
            summaries.extend(batch_summaries)
        explore_config = config.get("explore", {})
        if explore_config.get("enabled", True):
            batch, batch_summaries = self.crawl_explore(explore_config, max_pages=max_pages)
            records.extend(batch)
            summaries.extend(batch_summaries)
        return records, summaries
