from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class MovieRecord:
    subject_id: str
    title: str
    rating: float
    rating_count: int
    url: str
    kinds: set[str] = field(default_factory=set)
    source_ids: set[str] = field(default_factory=set)
    source_names: set[str] = field(default_factory=set)
    comprehensive_score: float = 0.0
    rank: int = 0

    def merge(self, other: "MovieRecord") -> None:
        """合并同一 subject；采用评价人数更多的一份作为最新评分快照。"""
        if other.subject_id != self.subject_id:
            raise ValueError("只能合并相同 subject_id 的记录")
        if other.rating_count >= self.rating_count:
            self.title = other.title
            self.rating = other.rating
            self.rating_count = other.rating_count
            self.url = other.url
        self.kinds.update(other.kinds)
        self.source_ids.update(other.source_ids)
        self.source_names.update(other.source_names)

    def to_dict(self, crawled_at: str) -> dict[str, Any]:
        row = asdict(self)
        row["id"] = row.pop("subject_id")
        row["kind"] = " / ".join(sorted(row.pop("kinds")))
        row["source_doulist_ids"] = " / ".join(sorted(row.pop("source_ids")))
        row["source_doulists"] = " / ".join(sorted(row.pop("source_names")))
        row["crawled_at"] = crawled_at
        return row
