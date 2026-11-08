"""Expected behaviour of evals/score.py ([Colin]). xfail only while a function raises
NotImplementedError; once implemented, a wrong result fails the suite.

Only cases that ADR-0005 settles unambiguously are pinned here. Open choices (multi-document
Recall@k, number boundaries such as "145" vs "45", whitespace and unit normalisation) are
listed in docs/gates/phase-1.md for Colin to decide and add.
"""

import pytest

from evals import score
from evals.schema import SystemOutput

todo = pytest.mark.xfail(raises=NotImplementedError, reason="[Colin] evals/score.py", strict=False)


@todo
def test_recall_at_k_single_target():
    assert score.recall_at_k(["A", "B", "C"], ["B"], k=5) == 1.0
    assert score.recall_at_k(["A", "B", "C"], ["Z"], k=5) == 0.0
    assert score.recall_at_k(["A", "B", "C", "D", "E", "F"], ["F"], k=5) == 0.0


@todo
def test_reciprocal_rank():
    assert score.reciprocal_rank(["A", "B"], ["A"]) == 1.0
    assert score.reciprocal_rank(["A", "B"], ["B"]) == 0.5
    assert score.reciprocal_rank(["A", "B"], ["Z"]) == 0.0


@todo
def test_contains_fact_literal_and_synonym():
    assert score.contains_fact("上限為 45 mTorr。", "45 mTorr", {})
    assert not score.contains_fact("上限為 40 mTorr。", "45 mTorr", {})
    assert score.contains_fact("要做月PM", "月保養", {"保養": ["PM"]})


@todo
def test_explicit_refusal_flag_counts_as_refusal():
    assert score.is_refusal(SystemOutput(answer="查無資料", refused=True))
