# 豆瓣影视爬虫

从公开的豆瓣影视豆列中采集条目 **ID、评分、评价人数**，去重后计算综合评分并排序，输出 CSV 和 JSON。

> 使用前请确认你的使用方式符合豆瓣网站条款与当地法律。程序默认低频串行请求，不绕过验证码；如果出现验证页，请停止运行、延长间隔后再试。

## 默认数据源

默认启用 21 个豆列（检索和核对日期：2026-08-09），完整清单见 `config/doulists.json`：

- 大众电影：高分电影上/中/下三榜，以及评分人数超过 5 万且评分高于 7 分的电影。
- 小众电影：冷门佳片上/下榜及容易忽视的国产电影。
- 特殊片种：高分纪录片两榜、动画长片、热门与冷门高分短片。
- 综合剧集：热门电视剧排行榜、9 分电视剧及五星电视剧两榜。
- 分区剧集：国产剧、日剧、港剧、动画剧集和悬疑探案剧。

这些来源兼顾高评价人数的大众作品和低评价人数的小众作品。项目只访问豆列页，豆列本身已经包含本项目需要的三个核心字段，因此不必逐个请求 subject 详情页，能显著减少请求量。

## 安装与运行

需要 Python 3.10 或更高版本。

```powershell
cd "E:\Archives\20260809 Douban Movies"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m douban_movies
```

首次运行会抓取所有启用豆列，默认每次请求等待 2-3 秒。输出：

- `output/douban_movies_ranked.csv`：Excel 友好的 UTF-8 BOM CSV
- `output/douban_movies_ranked.json`：UTF-8 JSON
- `output/crawl_summary.json`：各豆列解析数量、原始/去重数量和排名参数
- `output/cache/`：原始豆列 HTML 缓存，用于断点续跑和减少重复请求

快速验证前两页：

```powershell
python -m douban_movies --max-pages 2 --delay 1 --jitter 0.5
```

刷新已有缓存：

```powershell
python -m douban_movies --refresh
```

## 综合评分

采用与豆瓣读书项目相同的质量与对数热度综合评分：

```text
score = (R - delta) * ln(v)
```

- `R`：豆瓣评分
- `v`：评价人数
- `delta`：质量基线，默认 2.5
- `ln`：自然对数

该公式以 `R - delta` 表示评分超过质量基线的幅度，再用评价人数的自然对数衡量热度。对数可以降低超高评价人数的边际影响，同时仍让经过更多用户评价的作品获得更高综合分。可在 `config/doulists.json` 修改默认值，或临时覆盖：

```powershell
python -m douban_movies --delta 2.5
```

## 输出字段

| 字段 | 含义 |
|---|---|
| `rank` | 综合排名 |
| `id` | 豆瓣 subject ID |
| `title` | 影视名称 |
| `rating` | 豆瓣评分 |
| `rating_count` | 评价人数 |
| `comprehensive_score` | `(rating - delta) × ln(rating_count)` 综合评分 |
| `kind` | 电影/电视剧（按来源标记） |
| `url` | 豆瓣影视条目 URL |
| `source_doulist_ids` | 来源豆列 ID；重复条目会合并 |
| `source_doulists` | 来源豆列名称 |
| `crawled_at` | 本轮输出时间（含时区） |

## 常用参数

```text
--config PATH          豆列配置文件
--output PATH          输出目录
--cache-dir PATH       HTML 缓存目录，默认是输出目录下的 cache
--delay SECONDS        请求固定间隔，默认 2.0
--jitter SECONDS       随机附加间隔，默认 1.0
--timeout SECONDS      单次请求超时，默认 30
--max-pages N          每个豆列最多抓 N 页，适合测试
--refresh              忽略 HTML 缓存
--delta VALUE          覆盖质量基线，默认 2.5
--verbose              输出调试日志
```

如需加入新豆列，只要在 `config/doulists.json` 的 `doulists` 数组追加相同结构的对象。解析器会忽略豆列内被删除、无评分或不是豆瓣影视 subject 的项目。

## 测试

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

## 在线排行榜

GitHub Pages 页面展示排序后的 `id`、`title`、`rating`、`rating_count` 和 `url`，并支持搜索与分页：

<https://yuzhounh.github.io/douban-movies-ranking/>

抓取完成后，可用下面的命令从最终 JSON 重新生成网页数据：

```powershell
python scripts/build_pages_data.py
```
