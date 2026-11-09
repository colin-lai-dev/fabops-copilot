from collections import Counter

import pytest

from evals import label_sheet
from evals.schema import Question, RunRecord, SystemOutput


def q(qid: str, qtype: str) -> Question:
    if qtype == "refuse":
        return Question(
            qid=qid,
            qtype="refuse",
            source="rule",
            question="（測試）",
            user_id="admin_all",
            should_refuse=True,
        )
    extra = {"rubric": "說明步驟"} if qtype == "open" else {"key_facts": ["5 分鐘"]}
    if qtype == "cross_doc":
        extra["expected_doc_ids"] = ["A", "B"]
    return Question(
        qid=qid,
        qtype=qtype,
        source="rule",
        question="（測試）",
        user_id="admin_all",
        expected_doc_ids=extra.pop("expected_doc_ids", ["A"]),
        **extra,
    )


def pool() -> list[Question]:
    sizes = {"fact": 18, "paraphrase": 12, "dirty": 10, "cross_doc": 8, "refuse": 6}
    qs = [q(f"R-{t.upper()}-{i:04d}", t) for t, n in sizes.items() for i in range(n)]
    return qs + [q(f"H-{i:04d}", "open") for i in range(3)]


def test_select_takes_every_open_and_every_qtype():
    chosen = label_sheet.select(pool(), n=30)
    counts = Counter(x.qtype.value for x in chosen)
    assert len(chosen) == 30
    assert counts["open"] == 3
    assert set(counts) == {"fact", "paraphrase", "dirty", "cross_doc", "refuse", "open"}


def test_select_is_deterministic_and_keeps_order():
    a, b = label_sheet.select(pool(), n=30), label_sheet.select(pool(), n=30)
    assert a == b
    order = [x.qid for x in pool()]
    assert [x.qid for x in a] == sorted((x.qid for x in a), key=order.index)


def test_sheet_has_no_prefilled_verdicts_and_round_trips(tmp_path):
    qs = [q("R-FACT-0001", "fact"), q("R-REFUSE-0001", "refuse")]
    recs = {
        "R-FACT-0001": RunRecord(
            run_id="r1",
            qid="R-FACT-0001",
            output=SystemOutput(answer="等待 5 分鐘", citations=["A"]),
        ),
        "R-REFUSE-0001": RunRecord(
            run_id="r1", qid="R-REFUSE-0001", output=SystemOutput(answer="查無資料", refused=True)
        ),
    }
    text = label_sheet.render("r1", qs, recs)
    assert text.count("- 判斷（對／錯／部分）：\n") == 2  # 判斷欄全部空白
    sheet = tmp_path / "s.md"
    sheet.write_text(text, encoding="utf-8")
    assert label_sheet.parse(sheet) == []  # 沒填就沒有標註

    filled = text.replace("- 判斷（對／錯／部分）：\n", "- 判斷（對／錯／部分）：對\n", 1)
    filled = filled.replace(
        "- 判斷（對／錯／部分）：\n- 備註：", "- 判斷（對／錯／部分）：部分\n- 備註：少一步", 1
    )
    sheet.write_text(filled, encoding="utf-8")
    labels = label_sheet.parse(sheet)
    assert [(x.qid, x.passed, x.partial, x.notes) for x in labels] == [
        ("R-FACT-0001", True, False, "對"),
        ("R-REFUSE-0001", False, True, "部分；少一步"),
    ]
    rates = label_sheet.pass_rates(labels)
    assert rates == {"strict": {"value": 0.5, "n": 2}, "lenient": {"value": 1.0, "n": 2}}
    assert {x.run_id for x in labels} == {"r1"}


def test_parse_rejects_unknown_verdict(tmp_path):
    recs = {
        "R-FACT-0001": RunRecord(run_id="r1", qid="R-FACT-0001", output=SystemOutput(answer="x"))
    }
    text = label_sheet.render("r1", [q("R-FACT-0001", "fact")], recs)
    sheet = tmp_path / "s.md"
    sheet.write_text(text.replace("部分）：\n", "部分）：大概對\n"), encoding="utf-8")
    with pytest.raises(ValueError):
        label_sheet.parse(sheet)


def test_partial_label_cannot_be_passed():
    from evals.schema import JudgeLabel

    with pytest.raises(ValueError):
        JudgeLabel(run_id="r", qid="q", passed=True, partial=True)
