from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from requests.exceptions import RequestException

from .crawler import DoubanCrawler, DoulistSource, merge_records
from .official import OfficialSourcesCrawler
from .parser import ParseError
from .ranking import rank_records
from .output import write_outputs, write_summary

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="从豆瓣影视榜单采集 ID、评分、评价人数和分类，并生成综合排行。"
    )
    parser.add_argument("--config", type=Path, default=Path("config/doulists.json"))
    parser.add_argument("--output", type=Path, default=Path("output"))
    parser.add_argument(
        "--cache-dir",
        type=Path,
        help="HTML 缓存目录；默认使用输出目录下的 cache",
    )
    parser.add_argument("--delay", type=float, default=2.0, help="请求前固定等待秒数")
    parser.add_argument("--jitter", type=float, default=1.0, help="额外随机等待秒数")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--max-pages", type=int, help="每个豆列最多抓取页数（调试用）")
    parser.add_argument("--refresh", action="store_true", help="忽略 HTML 缓存重新请求")
    parser.add_argument(
        "--skip-official",
        action="store_true",
        help="只抓豆列，跳过分类榜、Top 250、选电影和选剧集",
    )
    parser.add_argument(
        "--delta", type=float, help="综合评分的质量基线 delta，默认 2.5"
    )
    parser.add_argument("--verbose", action="store_true")
    return parser


def load_config(path: Path) -> tuple[list[DoulistSource], dict, dict]:
    with path.open(encoding="utf-8") as handle:
        config = json.load(handle)
    sources = [
        DoulistSource(
            id=str(item["id"]),
            name=item["name"],
            kind=item["kind"],
            url=item["url"],
        )
        for item in config["doulists"]
        if item.get("enabled", True)
    ]
    if not sources:
        raise ValueError("配置中没有启用的豆列")
    return sources, config.get("ranking", {}), config.get("official_sources", {})


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        sources, ranking_config, official_config = load_config(args.config)
        crawler = DoubanCrawler(
            cache_dir=args.cache_dir or args.output / "cache",
            delay=args.delay,
            jitter=args.jitter,
            timeout=args.timeout,
            refresh=args.refresh,
        )
        all_records = []
        source_results = []
        for source in sources:
            source_records = crawler.crawl_source(source, max_pages=args.max_pages)
            all_records.extend(source_records)
            source_results.append(
                {
                    "id": source.id,
                    "name": source.name,
                    "kind": source.kind,
                    "url": source.url,
                    "extracted_records": len(source_records),
                    "navigation": {
                        "section": "分类排行榜",
                        "tab": "精选豆列",
                        "filter": "豆列",
                        "value": source.name,
                    },
                }
            )

        if not args.skip_official and official_config.get("enabled", True):
            official_records, official_results = OfficialSourcesCrawler(crawler).crawl_all(
                official_config,
                max_pages=args.max_pages,
            )
            all_records.extend(official_records)
            source_results.extend(official_results)

        unique_records = merge_records(all_records)
        delta = (
            args.delta
            if args.delta is not None
            else float(ranking_config.get("delta", 2.5))
        )
        ranked = rank_records(unique_records, delta=delta)
        crawled_at = datetime.now().astimezone().isoformat(timespec="seconds")
        csv_path, json_path = write_outputs(
            ranked, output_dir=args.output, crawled_at=crawled_at
        )
        summary_path = write_summary(
            {
                "generated_at": crawled_at,
                "source_count": len(source_results),
                "raw_record_count": len(all_records),
                "unique_record_count": len(ranked),
                "ranking": {
                    "method": "quality_times_log_popularity",
                    "formula": "(rating - delta) * ln(rating_count)",
                    "delta": delta,
                },
                "sources": source_results,
            },
            output_dir=args.output,
        )
        LOGGER.info(
            "完成：原始 %d 条，去重后 %d 条；CSV=%s；JSON=%s；摘要=%s",
            len(all_records),
            len(ranked),
            csv_path,
            json_path,
            summary_path,
        )
        return 0
    except (
        OSError,
        ValueError,
        KeyError,
        json.JSONDecodeError,
        ParseError,
        RequestException,
    ) as exc:
        LOGGER.error("执行失败：%s", exc)
        return 1
    except KeyboardInterrupt:
        LOGGER.warning("用户中止；已下载的页面缓存可在下次运行时继续使用。")
        return 130


if __name__ == "__main__":
    sys.exit(main())
