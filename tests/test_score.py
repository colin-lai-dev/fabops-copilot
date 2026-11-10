"""evals/score.py 的預期行為，依 ADR-0005「修訂（2026-11-08）：評分細節的預設規則」。
推翻某條規則時，更新 ADR-0005 與這裡對應的測試。
"""

import pytest

from evals import score
from evals.schema import Question, SystemOutput

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


def test_recall_at_k_is_a_fraction():
    assert score.recall_at_k(["A", "B", "C"], ["B"], k=5) == 1.0
    assert score.recall_at_k(["A", "B", "C"], ["A", "Z"], k=5) == 0.5
    assert score.recall_at_k(["A", "B", "C"], ["Z"], k=5) == 0.0
    assert score.recall_at_k(["A", "B", "C", "D", "E", "F"], ["F"], k=5) == 0.0


def test_hit_at_k():
    assert score.hit_at_k(["A", "B"], ["B", "Z"], k=5) is True
    assert score.hit_at_k(["A", "B"], ["Z"], k=5) is False


def test_reciprocal_rank():
    assert score.reciprocal_rank(["A", "B"], ["A"]) == 1.0
    assert score.reciprocal_rank(["A", "B"], ["B"]) == 0.5
    assert score.reciprocal_rank(["A", "B"], ["Z"]) == 0.0


# Rule 2: a number must not touch another digit or a decimal point.


def test_contains_fact_number_boundaries():
    assert score.contains_fact("上限為 45 mTorr。", "45 mTorr", {})
    assert not score.contains_fact("上限為 40 mTorr。", "45 mTorr", {})
    assert not score.contains_fact("上限為 145 mTorr。", "45 mTorr", {})
    assert not score.contains_fact("上限為 45.5 mTorr。", "45 mTorr", {})
    assert not score.contains_fact("上限為 0.45 mTorr。", "45 mTorr", {})


# Rule 3: NFKC, whitespace removed, units case-insensitive, synonyms from evals/synonyms.py.


def test_contains_fact_normalisation_and_synonyms():
    assert score.contains_fact("等待10分鐘", "10 分鐘", {})
    assert score.contains_fact("上限４５ ｍＴｏｒｒ", "45 mTorr", {})
    assert score.contains_fact("上限 45 MTORR", "45 mTorr", {})
    assert score.contains_fact("要做月PM", "月保養", {"保養": ["PM"]})


# Rule 4: the `refused` flag decides; a disagreeing answer text is counted as a mismatch.


def test_refusal_is_decided_by_the_flag():
    assert score.is_refusal(SystemOutput(answer="查無資料", refused=True))
    assert not score.is_refusal(SystemOutput(answer="無法回答這個問題。", refused=False))


def test_refusal_mismatch_does_not_change_the_verdict():
    q = question(qtype="refuse", should_refuse=True, key_facts=[], expected_doc_ids=[])
    s = score.score_question(q, SystemOutput(answer="無法回答這個問題。", refused=False), {})
    assert s.refusal_ok is False
    assert s.refusal_mismatch is True


# Rule 5: cite every expected doc and no superseded SOP; precision is reported separately.


def test_citation_requires_all_expected_and_no_superseded():
    q = question(qtype="old_version")
    ok = SystemOutput(answer="等待 5 分鐘", citations=[NEW])
    with_old = SystemOutput(answer="等待 5 分鐘", citations=[NEW, OLD])
    assert score.score_question(q, ok, {}, {OLD}).citation_ok is True
    assert score.score_question(q, with_old, {}, {OLD}).citation_ok is False


def test_citation_precision_is_reported_not_judged():
    q = question()
    out = SystemOutput(answer="等待 5 分鐘", citations=[NEW, "INC-2026-0001"])
    s = score.score_question(q, out, {}, {OLD})
    assert s.citation_ok is True
    assert s.citation_precision == 0.5


# 補充案例（實作時新增）


def test_recall_needs_expected_docs():
    with pytest.raises(ValueError):
        score.recall_at_k(["A"], [], k=5)


def test_contains_fact_trailing_decimal_point_is_not_a_number_boundary():
    # 句尾的英文句點不是小數點，不應讓數字比對失敗
    assert score.contains_fact("wait 5 min.", "5 min", {})
    assert score.contains_fact("版本為 v2.", "v2", {})
    assert not score.contains_fact("版本為 v2.1", "v2", {})


def test_contains_fact_synonym_in_either_direction():
    assert score.contains_fact("要做月保養", "月PM", {"保養": ["PM"]})
    assert score.contains_fact("chamber 暫停派貨", "腔體暫停派貨", {"腔體": ["chamber", "CH"]})


def test_refused_answer_finds_no_facts_and_is_wrong():
    q = question()
    s = score.score_question(q, SystemOutput(answer="等待 5 分鐘", refused=True), {})
    assert s.facts_found == 0
    assert s.answer_ok is False
    assert s.refusal_ok is False


def test_answer_ok_requires_every_key_fact():
    q = question(key_facts=["5 分鐘", "工程師"])
    half = score.score_question(q, SystemOutput(answer="等待 5 分鐘"), {})
    full = score.score_question(q, SystemOutput(answer="等待 5 分鐘並通知工程師"), {})
    assert (half.facts_found, half.answer_ok) == (1, False)
    assert (full.facts_found, full.answer_ok) == (2, True)


def test_refuse_question_with_leak_is_wrong():
    q = question(
        qtype="refuse",
        should_refuse=True,
        key_facts=[],
        expected_doc_ids=[],
        forbidden_facts=["45 mTorr"],
    )
    clean = score.score_question(q, SystemOutput(answer="查無可用資料", refused=True), {})
    leaky = score.score_question(
        q, SystemOutput(answer="查無資料，但上限是 45 mTorr", refused=True), {}
    )
    assert (clean.answer_ok, clean.leaked, clean.refusal_mismatch) == (True, False, False)
    assert (leaky.answer_ok, leaky.leaked) == (False, True)
    assert clean.recall_at_5 is None and clean.citation_ok is None


def test_open_question_is_left_to_the_judge():
    q = question(qtype="open", key_facts=[], rubric="說明處置步驟")
    s = score.score_question(q, SystemOutput(answer="……", citations=[NEW], retrieved=[NEW]), {})
    assert s.answer_ok is None
    assert s.citation_ok is True
    assert s.recall_at_5 == 1.0


def test_no_citations_gives_no_precision():
    s = score.score_question(question(), SystemOutput(answer="等待 5 分鐘"), {})
    assert s.citation_ok is False
    assert s.citation_precision is None


def test_aggregate_reports_n_for_every_metric():
    q1 = question(qid="R-FACT-0001")
    q2 = question(
        qid="R-REFUSE-0001", qtype="refuse", should_refuse=True, key_facts=[], expected_doc_ids=[]
    )
    scores = [
        score.score_question(
            q1, SystemOutput(answer="等待 5 分鐘", citations=[NEW], retrieved=["X", NEW]), {}
        ),
        score.score_question(q2, SystemOutput(answer="查無可用資料", refused=True), {}),
    ]
    m = score.aggregate(scores)
    assert m["overall"]["n"] == 2
    assert m["overall"]["answer_accuracy"] == {"value": 1.0, "n": 2}
    assert m["overall"]["recall@5"] == {"value": 1.0, "n": 1}
    assert m["overall"]["mrr"] == {"value": 0.5, "n": 1}
    assert m["overall"]["refusal_recall"] == {"value": 1.0, "n": 1}
    assert m["overall"]["false_refusal_rate"] == {"value": 0.0, "n": 1}
    assert m["overall"]["leak_rate"] == {"value": None, "n": 0}
    assert set(m["by_qtype"]) == {"fact", "refuse"}
    assert m["by_qtype"]["fact"]["n"] == 1


def test_refusal_text_variants_seen_from_qwen3():
    assert score.text_says_refusal("文件中沒有可用資料。")
    assert score.text_says_refusal("查無可用資料，無法回答這個問題。")
    assert not score.text_says_refusal("等待 5 分鐘後重新量測。")
