"""Expected behaviour of evals/score.py ([Colin]), following the default rules in ADR-0005
"修訂（2026-11-08）：評分細節的預設規則". Each test is xfail only while the function raises
NotImplementedError; once implemented, a wrong result fails the suite. Overriding a rule means
updating ADR-0005 and the matching test here.
"""

import pytest

from evals import score
from evals.schema import Question, SystemOutput

todo = pytest.mark.xfail(raises=NotImplementedError, reason="[Colin] evals/score.py", strict=False)

OLD, NEW = "SOP-FX1-ETC-EPD-0118-v1", "SOP-FX1-ETC-EPD-0118-v2"


def question(**kw) -> Question:
    base = {
        "qid": "R-FACT-0001",
        "qtype": "fact",
        "source": "rule",
        "question": "（測試）",
        "user_id": "eng_fx1_etch",
        "key_facts": ["5 分鐘"],
        "expected_doc_ids": [NEW],
    }
    return Question(**{**base, **kw})


# Rule 1: Recall@5 is the fraction of expected docs in the top 5; Hit@5 is reported too.


@todo
def test_recall_at_k_is_a_fraction():
    assert score.recall_at_k(["A", "B", "C"], ["B"], k=5) == 1.0
    assert score.recall_at_k(["A", "B", "C"], ["A", "Z"], k=5) == 0.5
    assert score.recall_at_k(["A", "B", "C"], ["Z"], k=5) == 0.0
    assert score.recall_at_k(["A", "B", "C", "D", "E", "F"], ["F"], k=5) == 0.0


@todo
def test_hit_at_k():
    assert score.hit_at_k(["A", "B"], ["B", "Z"], k=5) is True
    assert score.hit_at_k(["A", "B"], ["Z"], k=5) is False


@todo
def test_reciprocal_rank():
    assert score.reciprocal_rank(["A", "B"], ["A"]) == 1.0
    assert score.reciprocal_rank(["A", "B"], ["B"]) == 0.5
    assert score.reciprocal_rank(["A", "B"], ["Z"]) == 0.0


# Rule 2: a number must not touch another digit or a decimal point.


@todo
def test_contains_fact_number_boundaries():
    assert score.contains_fact("上限為 45 mTorr。", "45 mTorr", {})
    assert not score.contains_fact("上限為 40 mTorr。", "45 mTorr", {})
    assert not score.contains_fact("上限為 145 mTorr。", "45 mTorr", {})
    assert not score.contains_fact("上限為 45.5 mTorr。", "45 mTorr", {})
    assert not score.contains_fact("上限為 0.45 mTorr。", "45 mTorr", {})


# Rule 3: NFKC, whitespace removed, units case-insensitive, synonyms from evals/synonyms.py.


@todo
def test_contains_fact_normalisation_and_synonyms():
    assert score.contains_fact("等待10分鐘", "10 分鐘", {})
    assert score.contains_fact("上限４５ ｍＴｏｒｒ", "45 mTorr", {})
    assert score.contains_fact("上限 45 MTORR", "45 mTorr", {})
    assert score.contains_fact("要做月PM", "月保養", {"保養": ["PM"]})


# Rule 4: the `refused` flag decides; a disagreeing answer text is counted as a mismatch.


@todo
def test_refusal_is_decided_by_the_flag():
    assert score.is_refusal(SystemOutput(answer="查無資料", refused=True))
    assert not score.is_refusal(SystemOutput(answer="無法回答這個問題。", refused=False))


@todo
def test_refusal_mismatch_does_not_change_the_verdict():
    q = question(qtype="refuse", should_refuse=True, key_facts=[], expected_doc_ids=[])
    s = score.score_question(q, SystemOutput(answer="無法回答這個問題。", refused=False), {})
    assert s.refusal_ok is False
    assert s.refusal_mismatch is True


# Rule 5: cite every expected doc and no superseded SOP; precision is reported separately.


@todo
def test_citation_requires_all_expected_and_no_superseded():
    q = question(qtype="old_version")
    ok = SystemOutput(answer="等待 5 分鐘", citations=[NEW])
    with_old = SystemOutput(answer="等待 5 分鐘", citations=[NEW, OLD])
    assert score.score_question(q, ok, {}, {OLD}).citation_ok is True
    assert score.score_question(q, with_old, {}, {OLD}).citation_ok is False


@todo
def test_citation_precision_is_reported_not_judged():
    q = question()
    out = SystemOutput(answer="等待 5 分鐘", citations=[NEW, "INC-2026-0001"])
    s = score.score_question(q, out, {}, {OLD})
    assert s.citation_ok is True
    assert s.citation_precision == 0.5
