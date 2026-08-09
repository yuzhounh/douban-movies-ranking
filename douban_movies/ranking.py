from __future__ import annotations

import math

from .models import MovieRecord


def rank_records(records: list[MovieRecord], *, delta: float = 2.5) -> list[MovieRecord]:
    """按质量与对数热度综合评分排序：score = (R - delta) * ln(v)。"""

    for record in records:
        record.comprehensive_score = round(
            (record.rating - delta) * math.log(record.rating_count)
            if record.rating_count > 0
            else 0.0,
            6,
        )

    ranked = sorted(
        records,
        key=lambda item: (
            item.comprehensive_score,
            item.rating,
            item.rating_count,
            item.subject_id,
        ),
        reverse=True,
    )
    for index, record in enumerate(ranked, start=1):
        record.rank = index
    return ranked
