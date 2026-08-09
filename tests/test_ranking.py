import math

from douban_movies.models import MovieRecord
from douban_movies.ranking import rank_records


def make_record(subject_id: str, rating: float, votes: int) -> MovieRecord:
    return MovieRecord(subject_id, subject_id, rating, votes, "https://example.test")


def test_quality_times_log_popularity_score_and_order() -> None:
    records = [
        make_record("popular", 9.3, 1_000_000),
        make_record("tiny", 9.7, 100),
    ]
    ranked = rank_records(records, delta=2.5)
    assert [record.subject_id for record in ranked] == ["popular", "tiny"]
    assert ranked[0].rank == 1
    assert ranked[0].comprehensive_score == round(
        (9.3 - 2.5) * math.log(1_000_000), 6
    )


def test_zero_votes_gets_zero_score() -> None:
    record = make_record("zero", 9.9, 0)
    assert rank_records([record])[0].comprehensive_score == 0.0
