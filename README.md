# 豆瓣影视综合排行榜

从公开的豆瓣影视豆列、分类排行榜、Top 250、“选电影”和“选剧集”中采集条目 **ID、评分、评价人数、分类**，去重后计算综合评分并排序，输出 CSV 和 JSON。

> 使用前请确认你的使用方式符合豆瓣网站条款与当地法律。程序默认低频请求，不绕过验证码；电影和剧集筛选最多并发 3 个相互独立的请求。如果出现验证页，请停止运行、降低并发数或延长间隔后再试。

## 在线排行榜

GitHub Pages 按“分类排行榜、选电影、选剧集”三个一级板块展示数据，并依次使用二级类别和三级标签继续筛选。“全部”会对当前一级板块或二级类别中的作品去重汇总；“分类排行榜”中的三级标签按作品数量从多到少排列，Top 250 作为其中的独立榜单。表格展示排序后的豆瓣ID、标题、评分和评价人数，点击任意影视条目所在行即可打开对应豆瓣页面，并支持分类内搜索与分页。

在线展示页面：<https://yuzhounh.github.io/douban-movies-ranking/>

## 数据规模

最近一次完整抓取（2026-08-10）得到 153,850 条原始记录，按豆瓣 subject ID 去重后为 **51,970 部影视作品**；其中 **51,940 部带有分类，覆盖率 99.94%**。

## 默认数据源

默认同时抓取以下官方页面和公开豆列，完整配置见 `config/doulists.json`：

- **分类排行榜**：自动发现并遍历豆瓣当前提供的 28 个电影分类；每个分类遍历从 `100:90` 到 `10:0` 的十个评价区间，并把分类合并到作品的 `genres` 字段。
- **豆瓣电影 Top 250**：遍历全部 10 页、250 部影片。
- **选电影**：98 个导航分支，遍历“全部”下的类型、地区、年代、排序和当前推荐标签；同时遍历“热门电影、最新电影、豆瓣高分、冷门佳片”及其全部子榜。
- **选剧集**：106 个导航分支，遍历“不限类型、全部剧集、全部综艺”，电视剧与综艺各自的类型，以及地区、年代、平台、排序和当前推荐标签；同时遍历“最近热门剧集、最近热门综艺”的全部子榜。
- **21 个公开豆列**（检索和核对日期：2026-08-09）：
  - 大众电影：高分电影上/中/下三榜，以及评分人数超过 5 万且评分高于 7 分的电影。
  - 小众电影：冷门佳片上/下榜及容易忽视的国产电影。
  - 特殊片种：高分纪录片两榜、动画长片、热门与冷门高分短片。
  - 综合剧集：热门电视剧排行榜、9 分电视剧及五星电视剧两榜。
  - 分区剧集：国产剧、日剧、港剧、动画剧集和悬疑探案剧。

这些来源兼顾高评价人数的大众作品、低评价人数的小众作品、电影和剧集。“选电影”和“选剧集”的类型、地区、年代、平台及排序是可枚举筛选项；自由输入标签不存在有限全集，因此项目遍历的是豆瓣页面当时返回的推荐标签，而不是声称穷尽所有可能的自由标签。评分区间是连续滑块，也不做无限组合穷举，保持默认 `0–10`。推荐接口返回的条目数据中包含评价人数，因此不需要逐个请求 subject 详情页。每个筛选分支最多抓取 500 条，可在配置中调整。

## 安装与运行

需要 Python 3.10 或更高版本。

```powershell
cd "E:\Archives\20260809 Douban Movies"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m douban_movies
```

首次运行会抓取所有启用来源，默认每次请求等待 2-3 秒。输出：

- `output/douban_movies_ranked.csv`：Excel 友好的 UTF-8 BOM CSV
- `output/douban_movies_ranked.json`：UTF-8 JSON
- `output/crawl_summary.json`：各来源解析数量、原始/去重数量和排名参数
- `output/cache/`：原始 HTML/JSON 缓存，用于断点续跑和减少重复请求

快速验证前两页：

```powershell
python -m douban_movies --max-pages 2 --delay 1 --jitter 0.5
```

刷新已有缓存：

```powershell
python -m douban_movies --refresh
```

抓取完成后，可用下面的命令从最终 JSON 重新生成网页数据：

```powershell
python scripts/build_pages_data.py
```

## 综合评分

采用与豆瓣读书项目相同的质量与对数热度综合评分：

```text
综合评分 = (评分 - delta) * ln(评价人数)
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
| `genres` | 分类排行榜和豆列中识别到的分类；多个分类以 `/` 分隔 |
| `url` | 豆瓣影视条目 URL |
| `source_doulist_ids` | 来源 ID；兼容早期字段名，现也包含官方榜单和筛选来源 |
| `source_doulists` | 来源名称；重复条目会合并 |
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
--skip-official        只抓豆列，跳过分类榜、Top 250、选电影和选剧集
--delta VALUE          覆盖质量基线，默认 2.5
--verbose              输出调试日志
```

如需加入新豆列，只要在 `config/doulists.json` 的 `doulists` 数组追加相同结构的对象。解析器会忽略豆列内被删除、无评分或不是豆瓣影视 subject 的项目。

## 测试

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```
