from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import MovieRecord
from .parser import ParseError, parse_doulist_page

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class DoulistSource:
    id: str
    name: str
    kind: str
    url: str


class DoubanCrawler:
    def __init__(
        self,
        *,
        cache_dir: Path,
        delay: float = 2.0,
        jitter: float = 1.0,
        timeout: float = 30.0,
        refresh: bool = False,
        user_agent: str | None = None,
    ) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.delay = max(delay, 0.0)
        self.jitter = max(jitter, 0.0)
        self.timeout = timeout
        self.refresh = refresh
        self.session = requests.Session()
        retry = Retry(
            total=4,
            connect=4,
            read=4,
            status=4,
            backoff_factor=1.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(("GET",)),
            respect_retry_after_header=True,
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.headers.update(
            {
                "User-Agent": user_agent
                or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0 Safari/537.36",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )

    def _cache_path(self, source_id: str, url: str) -> Path:
        query = parse_qs(urlparse(url).query)
        start = query.get("start", ["0"])[0]
        return self.cache_dir / f"doulist_{source_id}_start_{start}.html"

    def _request_text(
        self,
        *,
        cache_path: Path,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> str:
        if cache_path.exists() and not self.refresh:
            LOGGER.info("读取缓存：%s", cache_path.name)
            return cache_path.read_text(encoding="utf-8")

        wait_seconds = self.delay + random.uniform(0, self.jitter)
        if wait_seconds:
            time.sleep(wait_seconds)
        LOGGER.info("请求：%s", url)
        response = self.session.get(url, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        if "sec.douban.com" in response.url:
            raise ParseError(f"请求被重定向到豆瓣验证页：{response.url}")
        response.encoding = response.apparent_encoding or "utf-8"
        html = response.text
        if (
            'id="captcha-form"' in html
            or "检测到有异常请求" in html
            or "豆瓣防刷机制" in html
        ):
            raise ParseError("豆瓣返回了验证或异常请求页面；该页面未写入缓存")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(html, encoding="utf-8")
        return html

    def _get_html(self, source: DoulistSource, url: str) -> str:
        return self._request_text(
            cache_path=self._cache_path(source.id, url),
            url=url,
        )

    def get_text(
        self,
        cache_key: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> str:
        """获取并缓存非豆列页面或接口响应。"""
        return self._request_text(
            cache_path=self.cache_dir / cache_key,
            url=url,
            headers=headers,
        )

    def get_json(
        self,
        cache_key: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> object:
        text = self.get_text(cache_key, url, headers=headers)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ParseError(f"豆瓣接口没有返回有效 JSON：{url}") from exc

    def crawl_source(
        self, source: DoulistSource, *, max_pages: int | None = None
    ) -> list[MovieRecord]:
        records: list[MovieRecord] = []
        page_url: str | None = source.url
        visited: set[str] = set()
        page_number = 0

        while page_url and page_url not in visited:
            if max_pages is not None and page_number >= max_pages:
                break
            visited.add(page_url)
            page_number += 1
            html = self._get_html(source, page_url)
            page_records, next_url = parse_doulist_page(
                html,
                source_id=source.id,
                source_name=source.name,
                kind=source.kind,
                page_url=page_url,
            )
            records.extend(page_records)
            LOGGER.info(
                "%s：第 %d 页解析 %d 条，累计 %d 条",
                source.name,
                page_number,
                len(page_records),
                len(records),
            )
            page_url = next_url
        return records


def merge_records(records: list[MovieRecord]) -> list[MovieRecord]:
    merged: dict[str, MovieRecord] = {}
    for record in records:
        existing = merged.get(record.subject_id)
        if existing is None:
            merged[record.subject_id] = record
        else:
            existing.merge(record)
    return list(merged.values())
