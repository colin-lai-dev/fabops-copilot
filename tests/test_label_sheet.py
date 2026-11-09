from collections import Counter

import pytest

from evals import label_sheet
from evals.schema import JudgeLabel, Question, RunRecord, SystemOutput

RUBRIC = (
    "要點：(1) 先確認保養狀態並暫停派貨；(2) 等待 10 分鐘後重新量測；(3) 連續 3 次超出上限就 hold；"
    "(4) 執行月保養後以 1 片監控晶圓驗證才可復機；(5) 超過 8 小時未排除升級至模組經理。"
    "每漏一個要點扣分。"
)


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
    extra = {"rubric": RUBRIC} if qtype == "open" else {"key_facts": ["5 分鐘"]}
    docs = ["A", "B"] if qtype == "cross_doc" else ["A"]
    return Question(
        qid=qid,
        qtype=qtype,
        source="rule",
        question="（測試）",
        user_id="admin_all",
        expected_doc_ids=docs,
        **extra,
    )


def item(qid: str, qtype: str, run: str = "dev1", **out):
    return q(qid, qtype), RunRecord(
        run_id=run, qid=qid, output=SystemOutput(answer=out.pop("answer", "答"), **out)
    )


def dev_pool():
    sizes = {
        "fact": 18,
        "paraphrase": 12,
        "dirty": 10,
        "old_version": 6,
        "cross_doc": 8,
        "refuse": 6,
    }
    items = [item(f"R-{t.upper()}-{i:04d}", t) for t, n in sizes.items() for i in range(n)]
    return items + [item(f"H-{i:04d}", "open") for i in range(3)]


def test_select_takes_all_opens_then_priority_types_then_stratified():
    opens = [item(f"C-OPEN-{i:04d}", "open", "cal1") for i in range(22)]
    dev = dev_pool()
    dev_opens = [it for it in dev if it[0].qtype.value == "open"]
    chosen = label_sheet.select(opens + dev_opens, dev)
    counts = Counter(x.qtype.value for x, _ in chosen)
    assert len(chosen) == 50
    assert counts["open"] == 25 and counts["refuse"] == 6 and counts["cross_doc"] == 8
    assert {"fact", "paraphrase", "dirty", "old_version"} <= set(counts)
    assert len({x.qid for x, _ in chosen}) == 50
    assert label_sheet.select(opens, dev) == label_sheet.select(opens, dev)


def test_rubric_points_are_split_into_five():
    points, tail = label_sheet.rubric_points(RUBRIC)
    assert len(points) == 5 and points[1] == "等待 10 分鐘後重新量測"
    assert tail == "每漏一個要點扣分。"


def test_sheet_has_no_prefilled_verdicts_and_round_trips(tmp_path):
    items = [
        item("C-OPEN-0001", "open", "cal1"),
        item("R-REFUSE-0001", "refuse", "dev1", answer="查無資料", refused=True),
    ]
    text = label_sheet.render(items)
    assert text.count("- 判斷（對／錯／部分）：\n") == 2  # 整題判斷全部空白
    assert text.count("  - 有／漏／錯：\n") == 5  # open 題的 5 個要點也空白
    sheet = tmp_path / "s.md"
    sheet.write_text(text, encoding="utf-8")
    assert label_sheet.parse(sheet) == []  # 沒填就沒有標註

    filled = text
    for v in ["有", "有", "漏", "有", "錯"]:
        filled = filled.replace("  - 有／漏／錯：\n", f"  - 有／漏／錯：{v}\n", 1)
    filled = filled.replace("- 判斷（對／錯／部分）：\n", "- 判斷（對／錯／部分）：部分\n", 1)
    filled = filled.replace("- 判斷（對／錯／部分）：\n", "- 判斷（對／錯／部分）：對\n", 1)
    filled = filled.replace("- 備註：\n", "- 備註：少一步\n", 1)
    sheet.write_text(filled, encoding="utf-8")
    labels = label_sheet.parse(sheet)
    assert [(x.run_id, x.qid, x.passed, x.partial, x.points, x.notes) for x in labels] == [
        ("cal1", "C-OPEN-0001", False, True, ["有", "有", "漏", "有", "錯"], "部分；少一步"),
        ("dev1", "R-REFUSE-0001", True, False, [], "對"),
    ]
    assert label_sheet.pass_rates(labels) == {
        "strict": {"value": 0.5, "n": 2},
        "lenient": {"value": 1.0, "n": 2},
    }


def test_parse_rejects_unknown_verdicts(tmp_path):
    text = label_sheet.render([item("C-OPEN-0001", "open", "cal1")])
    sheet = tmp_path / "s.md"
    sheet.write_text(text.replace("部分）：\n", "部分）：大概對\n"), encoding="utf-8")
    with pytest.raises(ValueError):
        label_sheet.parse(sheet)
    sheet.write_text(text.replace("有／漏／錯：\n", "有／漏／錯：還好\n", 1), encoding="utf-8")
    with pytest.raises(ValueError):
        label_sheet.parse(sheet)


def test_mobile_version_has_no_paths_or_fill_lines():
    text = label_sheet.render_mobile([item("C-OPEN-0001", "open", "cal1")])
    assert "run_id" not in text and "有／漏／錯" not in text and "`A`" not in text
    assert "2. 等待 10 分鐘後重新量測" in text


def test_partial_label_cannot_be_passed():
    with pytest.raises(ValueError):
        JudgeLabel(run_id="r", qid="q", passed=True, partial=True)
