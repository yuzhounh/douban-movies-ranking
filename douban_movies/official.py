from __future__ import annotations

import hashlib
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
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
    kind: str = "电影",
    genres: set[str] | None = None,
) -> MovieRecord:
    return MovieRecord(
        subject_id=subject_id,
        title=title,
        rating=rating,
        rating_count=rating_count,
        url=f"https://movie.douban.com/subject/{subject_id}/",
        kinds={kind},
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
    support_type: str = "movie",
    selected_genre: str | None = None,
) -> list[MovieRecord]:
    records: list[MovieRecord] = []
    for item in items:
        if item.get("type") != support_type or not item.get("id"):
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
                kind="电影" if support_type == "movie" else "剧集",
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
                    "navigation": self._navigation(
                        "分类排行榜", "类型排行榜", "类型", category.name
                    ),
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
                "navigation": self._navigation(
                    "分类排行榜", "Top 250", "榜单", "Top 250"
                ),
            }
        ]

    @staticmethod
    def _navigation(
        section: str,
        tab: str,
        filter_name: str,
        value: str,
        *,
        group: str | None = None,
    ) -> dict[str, str]:
        navigation = {
            "section": section,
            "tab": tab,
            "filter": filter_name,
            "value": value,
        }
        if group:
            navigation["group"] = group
        return navigation

    def _explore_payload(
        self,
        *,
        support_type: str,
        cache_key: str,
        selected_categories: dict[str, str],
        tags: list[str],
        start: int,
        count: int,
        sort: str | None = None,
    ) -> dict:
        params: dict[str, object] = {
            "type": support_type,
            "refresh": 0,
            "start": start,
            "count": count,
            "selected_categories": json.dumps(
                selected_categories, ensure_ascii=False, separators=(",", ":")
            ),
            "uncollect": "false",
            "score_range": "0,10",
        }
        if tags:
            params["tags"] = ",".join(tags)
        if sort:
            params["sort"] = sort
        url = self._url(
            f"https://m.douban.com/rexxar/api/v2/{support_type}/recommend",
            params,
        )
        page_url = (
            "https://movie.douban.com/explore"
            if support_type == "movie"
            else "https://movie.douban.com/tv/"
        )
        payload = self.crawler.get_json(
            cache_key,
            url,
            headers={**self.json_headers, "Referer": page_url},
        )
        if not isinstance(payload, dict):
            raise ParseError(f"{support_type} 推荐接口结构异常")
        return payload

    def _crawl_explore_filter(
        self,
        *,
        support_type: str,
        page_url: str,
        section: str,
        tab: str,
        filter_name: str,
        value: str,
        group: str | None,
        selected_categories: dict[str, str],
        tags: list[str],
        sort: str | None,
        page_size: int,
        max_items: int,
        max_pages: int | None,
    ) -> tuple[list[MovieRecord], dict]:
        source_hash = self._stable_id(
            support_type, tab, filter_name, group or "", value
        )
        source_id = f"explore:{support_type}:{source_hash}"
        path = "/".join(part for part in (tab, filter_name, group, value) if part)
        source_name = f"{section}：{path}"
        query_hash = self._stable_id(
            "query",
            support_type,
            json.dumps(selected_categories, ensure_ascii=False, sort_keys=True),
            ",".join(tags),
            sort or "",
        )
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
                support_type=support_type,
                cache_key=f"official/explore_{query_hash}_start_{start}.json",
                selected_categories=selected_categories,
                tags=tags,
                start=start,
                count=count,
                sort=sort,
            )
            total = int(payload.get("total") or 0)
            items = payload.get("items") or []
            if not isinstance(items, list):
                raise ParseError(f"{section}条目结构异常：{path}")
            selected_genre = None
            if filter_name == "类型" and value not in {
                "全部",
                "不限类型",
                "全部剧集",
                "全部综艺",
            }:
                selected_genre = value
            page_records = parse_explore_items(
                items,
                source_id=source_id,
                source_name=source_name,
                support_type=support_type,
                selected_genre=selected_genre,
            )
            records.extend(page_records)
            LOGGER.info(
                "%s %s：第 %d 页 %d 条（接口总数 %d）",
                section,
                path,
                page_number,
                len(page_records),
                total,
            )
            if not items or len(items) < count:
                break
            start += count
        summary = {
            "id": source_id,
            "name": source_name,
            "kind": "电影" if support_type == "movie" else "剧集",
            "url": page_url,
            "extracted_records": len(records),
            "reported_total": total,
            "max_items": max_items,
            "navigation": self._navigation(
                section, tab, filter_name, value, group=group
            ),
        }
        return records, summary

    def _crawl_recent_hot(
        self,
        *,
        support_type: str,
        page_url: str,
        section: str,
        page_size: int,
        max_items: int,
        max_pages: int | None,
    ) -> tuple[list[MovieRecord], list[dict]]:
        headers = {**self.json_headers, "Referer": page_url}
        endpoint = (
            f"https://m.douban.com/rexxar/api/v2/subject/recent_hot/{support_type}"
        )
        seed_url = self._url(
            endpoint,
            {"start": 0, "limit": min(page_size, max_items)},
        )
        seed = self.crawler.get_json(
            f"official/explore_recent_{support_type}_seed.json",
            seed_url,
            headers=headers,
        )
        if not isinstance(seed, dict):
            raise ParseError(f"{section}热门子榜接口结构异常")

        records: list[MovieRecord] = []
        summaries: list[dict] = []
        for main_tag in seed.get("tags") or []:
            category = str(main_tag.get("category", ""))
            tab = str(main_tag.get("title", category))
            for subtype in main_tag.get("types") or []:
                subtype_value = str(subtype.get("type", ""))
                subtype_title = str(subtype.get("title", subtype_value))
                if not category or not subtype_value:
                    continue
                source_hash = self._stable_id(
                    support_type, "recent", category, subtype_value
                )
                source_id = f"explore:{support_type}:recent:{source_hash}"
                source_name = f"{section}：{tab}/{subtype_title}"
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
                        endpoint,
                        {
                            "start": start,
                            "limit": limit,
                            "category": category,
                            "type": subtype_value,
                        },
                    )
                    payload = self.crawler.get_json(
                        f"official/explore_recent_{source_hash}_start_{start}.json",
                        url,
                        headers=headers,
                    )
                    if not isinstance(payload, dict):
                        raise ParseError(f"{section}热门子榜结构异常：{source_name}")
                    total = int(payload.get("total") or 0)
                    items = payload.get("items") or []
                    if not isinstance(items, list):
                        raise ParseError(f"{section}热门子榜条目结构异常：{source_name}")
                    page_records = parse_explore_items(
                        items,
                        source_id=source_id,
                        source_name=source_name,
                        support_type=support_type,
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
                        "kind": "电影" if support_type == "movie" else "剧集",
                        "url": page_url,
                        "extracted_records": len(combo_records),
                        "reported_total": total,
                        "max_items": max_items,
                        "navigation": self._navigation(
                            section, tab, "子榜", subtype_title
                        ),
                    }
                )
        return records, summaries

    def crawl_explore(
        self,
        config: dict,
        *,
        support_type: str = "movie",
        max_pages: int | None = None,
    ) -> tuple[list[MovieRecord], list[dict]]:
        if support_type not in {"movie", "tv"}:
            raise ValueError(f"不支持的推荐类型：{support_type}")
        section = "选电影" if support_type == "movie" else "选剧集"
        page_url = (
            "https://movie.douban.com/explore"
            if support_type == "movie"
            else "https://movie.douban.com/tv/"
        )
        page_size = int(config.get("page_size", 500))
        max_items = int(config.get("max_items_per_filter", 500))
        seed = self._explore_payload(
            support_type=support_type,
            cache_key=f"official/explore_{support_type}_seed.json",
            selected_categories={},
            tags=[],
            start=0,
            count=20,
        )
        requests_to_crawl: list[dict] = [
            {
                "tab": "全部",
                "filter_name": "全部",
                "value": "全部",
                "group": None,
                "selected_categories": {},
                "tags": [],
                "sort": None,
            }
        ]

        for category in seed.get("recommend_categories") or []:
            facet_type = str(category.get("type", ""))
            category_items = category.get("data") or []
            group_key = str(category.get("tag_groups", ""))
            if not facet_type:
                continue
            if group_key:
                group_names = [str(item.get("text", "")) for item in category_items]
                for group_index, item in enumerate(category_items):
                    group_name = str(item.get("text", ""))
                    for tag_index, raw_tag in enumerate(item.get("tags") or []):
                        value = str(raw_tag)
                        if not value:
                            continue
                        if group_index == 0 and tag_index == 0:
                            selected_categories: dict[str, str] = {}
                            tags: list[str] = []
                        elif group_index == 0:
                            selected_group = group_names[tag_index]
                            selected_categories = {
                                facet_type: "",
                                group_key: selected_group,
                            }
                            tags = [selected_group]
                        else:
                            selected_categories = {
                                facet_type: value,
                                group_key: group_name,
                            }
                            tags = [value]
                        requests_to_crawl.append(
                            {
                                "tab": "全部",
                                "filter_name": facet_type,
                                "value": value,
                                "group": "全部" if group_index == 0 else group_name,
                                "selected_categories": selected_categories,
                                "tags": tags,
                                "sort": None,
                            }
                        )
            else:
                for item in category_items:
                    value = str(item.get("text", ""))
                    if not value:
                        continue
                    is_default = bool(item.get("default")) or value == "全部"
                    requests_to_crawl.append(
                        {
                            "tab": "全部",
                            "filter_name": facet_type,
                            "value": value,
                            "group": None,
                            "selected_categories": {}
                            if is_default
                            else {facet_type: value},
                            "tags": [] if is_default else [value],
                            "sort": None,
                        }
                    )

        filter_url = self._url(
            f"https://m.douban.com/rexxar/api/v2/{support_type}/recommend/filter_tags",
            {"type": support_type, "selected_categories": "{}"},
        )
        filter_payload = self.crawler.get_json(
            f"official/explore_{support_type}_filter_tags.json",
            filter_url,
            headers={**self.json_headers, "Referer": page_url},
        )
        if isinstance(filter_payload, dict):
            for filter_group in filter_payload.get("tags") or []:
                facet_type = str(filter_group.get("type", ""))
                if facet_type == "标签" or not facet_type:
                    continue
                for raw_value in filter_group.get("tags") or []:
                    value = str(raw_value)
                    if not value:
                        continue
                    requests_to_crawl.append(
                        {
                            "tab": "全部",
                            "filter_name": facet_type,
                            "value": value,
                            "group": None,
                            "selected_categories": {},
                            "tags": [] if value == "全部" else [value],
                            "sort": None,
                        }
                    )

        for sort_item in seed.get("sorts") or []:
            sort_name = str(sort_item.get("name", ""))
            sort_text = str(sort_item.get("text", sort_name))
            if sort_name and sort_text:
                requests_to_crawl.append(
                    {
                        "tab": "全部",
                        "filter_name": "排序",
                        "value": sort_text,
                        "group": None,
                        "selected_categories": {},
                        "tags": [],
                        "sort": sort_name,
                    }
                )

        if config.get("include_recommended_tags", True):
            recommended = list(seed.get("recommend_tags") or []) + list(
                seed.get("bottom_recommend_tags") or []
            )
            for value in dict.fromkeys(str(tag) for tag in recommended if str(tag)):
                requests_to_crawl.append(
                    {
                        "tab": "全部",
                        "filter_name": "标签",
                        "value": value,
                        "group": "推荐标签",
                        "selected_categories": {},
                        "tags": [value],
                        "sort": None,
                    }
                )

        deduplicated: dict[tuple[str, str, str, str], dict] = {}
        for request in requests_to_crawl:
            key = (
                request["tab"],
                request["filter_name"],
                request.get("group") or "",
                request["value"],
            )
            deduplicated[key] = request

        query_groups: dict[tuple[str, str, str], list[dict]] = {}
        for request in deduplicated.values():
            query_key = (
                json.dumps(
                    request["selected_categories"],
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                ",".join(request["tags"]),
                request.get("sort") or "",
            )
            query_groups.setdefault(query_key, []).append(request)

        def crawl_query_group(
            group_requests: list[dict],
        ) -> tuple[list[MovieRecord], list[dict]]:
            group_records: list[MovieRecord] = []
            group_summaries: list[dict] = []
            for request in group_requests:
                records, summary = self._crawl_explore_filter(
                    support_type=support_type,
                    page_url=page_url,
                    section=section,
                    page_size=page_size,
                    max_items=max_items,
                    max_pages=max_pages,
                    **request,
                )
                group_records.extend(records)
                group_summaries.append(summary)
            return group_records, group_summaries

        all_records: list[MovieRecord] = []
        summaries: list[dict] = []
        workers = max(1, min(int(config.get("workers", 1)), 4))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for records, source_summaries in executor.map(
                crawl_query_group, query_groups.values()
            ):
                all_records.extend(records)
                summaries.extend(source_summaries)

        if config.get("include_recent_hot", True):
            recent_records, recent_summaries = self._crawl_recent_hot(
                support_type=support_type,
                page_url=page_url,
                section=section,
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
        explore_config = config.get("explore", {})
        if explore_config.get("enabled", True):
            batch, batch_summaries = self.crawl_explore(
                explore_config,
                support_type="movie",
                max_pages=max_pages,
            )
            records.extend(batch)
            summaries.extend(batch_summaries)
        tv_config = config.get("tv", {})
        if tv_config.get("enabled", True):
            batch, batch_summaries = self.crawl_explore(
                tv_config,
                support_type="tv",
                max_pages=max_pages,
            )
            records.extend(batch)
            summaries.extend(batch_summaries)
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
        return records, summaries
