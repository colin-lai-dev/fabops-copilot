"""人工標註表（judge 校準，ADR-0005／0008）：產生標註表，以及把 Colin 填好的表轉成 JudgeLabel。

標註結果必須是 Colin 的判斷（CLAUDE.md）：這裡只準備題目、系統回答與評分準則，
**不放任何判斷**——連 score.py 的自動評分結果也不放，避免先入為主。

    uv run python -m evals.label_sheet make --calibration <run_id> --dev <run_id>
    uv run python -m evals.label_sheet parse      # 填好後轉成 evals/judge_labels.jsonl

選題（交接指示 003 補充第 8 點）：
- open 題全收：校準題庫（`evals/calibration/open.jsonl`）的執行結果，加上 dev 中的 open 題。
  judge 只評 open 題，所以標註以它們為主；每題列出評分準則的 5 個要點，讓 Colin 逐點判斷。
- 其餘名額從 dev 的其他題型選：拒答、跨文件優先（全收），剩下依題型比例分層抽樣（每型至少 1 題）。
只能用 dev 與 calibration 的執行結果，不能用 test。

另外輸出手機閱讀版 `private/label-sheet-mobile.md`（只有題號、問題、回答、要點；不進 git）。
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import Path

from evals.run import EVALS, RESULTS, ROOT, question_files
from evals.schema import JudgeLabel, QType, Question, RunRecord, load_questions

SHEET = EVALS / "labels" / "label-sheet.md"
MOBILE = ROOT / "private" / "label-sheet-mobile.md"
LABELS = EVALS / "judge_labels.jsonl"
SEED = 20261109
N = 50
PRIORITY = (QType.REFUSE, QType.CROSS_DOC)
VERDICTS = {"對": True, "錯": False, "部分": False}  # 「部分」嚴格算不通過（ADR-0005 規則 6）
POINT_VERDICTS = ("有", "漏", "錯")
_VERDICT = re.compile(r"^- 判斷（對／錯／部分）：(.*)$")
_POINT = re.compile(r"^  - 有／漏／錯：(.*)$")
_NOTE = re.compile(r"^- 備註：(.*)$")
_HEAD = re.compile(r"^### \d+\. (\S+?)（")
_RUN = re.compile(r"^- run_id：`([^`]+)`")
_RUBRIC_POINT = re.compile(r"\((\d+)\) ([^；。]+)")

Item = tuple[Question, RunRecord]


# ---------------------------------------------------------------- 選題


def stratified(questions: Sequence[Question], budget: int, rng: random.Random) -> list[Question]:
    """依題型比例分配 budget（最大餘數法，每型至少 1 題），回傳抽到的題目。"""
    by_type: dict[QType, list[Question]] = defaultdict(list)
    for q in questions:
        by_type[q.qtype].append(q)
    if budget <= 0 or not by_type:
        return []
    if budget >= len(questions):
        return list(questions)
    total = len(questions)
    exact = {t: budget * len(v) / total for t, v in by_type.items()}
    quota = {t: min(len(by_type[t]), max(1, int(x))) for t, x in exact.items()}
    for t in sorted(exact, key=lambda t: exact[t] - int(exact[t]), reverse=True):
        if sum(quota.values()) >= budget:
            break
        if quota[t] < len(by_type[t]):
            quota[t] += 1
    return [q for t in sorted(by_type) for q in rng.sample(by_type[t], quota[t])]


def select(
    opens: Sequence[Item], others: Sequence[Item], n: int = N, seed: int = SEED
) -> list[Item]:
    """open 題全收（最多 n）；其餘名額先給拒答、跨文件，再依題型分層抽樣。"""
    rng = random.Random(seed)
    chosen = list(opens)[:n]
    budget = n - len(chosen)
    rest = [it for it in others if it[0].qtype is not QType.OPEN]
    first = [it for it in rest if it[0].qtype in PRIORITY][:budget]
    chosen += first
    pool = [it for it in rest if it[0].qtype not in PRIORITY]
    picked = {q.qid for q in stratified([q for q, _ in pool], n - len(chosen), rng)}
    chosen += [it for it in pool if it[0].qid in picked]
    return chosen


# ---------------------------------------------------------------- 產生


def rubric_points(rubric: str) -> tuple[list[str], str]:
    """把「要點：(1) …；(2) …。說明」拆成要點清單與其餘的評分說明。"""
    points = [m.group(2).strip() for m in _RUBRIC_POINT.finditer(rubric)]
    tail = rubric.split("。", 1)[1].strip() if "。" in rubric else ""
    return points, tail


def _criteria(q: Question) -> list[str]:
    if q.should_refuse:
        lines = ["- 應拒答（資料中沒有答案）"]
        if q.forbidden_facts:
            lines.append("- 不得出現：" + "、".join(q.forbidden_facts))
        return lines
    lines = []
    if q.rubric:
        points, tail = rubric_points(q.rubric)
        for i, p in enumerate(points, 1):
            lines += [f"- 要點 {i}：{p}", "  - 有／漏／錯："]
        if tail:
            lines.append(f"- 評分說明：{tail}")
    if q.key_facts:
        lines.append("- 關鍵事實（全部都要有）：" + "、".join(q.key_facts))
    lines.append("- 應引用：" + "、".join(f"`{d}`" for d in q.expected_doc_ids))
    return lines


def render(items: Sequence[Item]) -> str:
    counts = Counter(q.qtype.value for q, _ in items)
    runs = sorted({r.run_id for _, r in items})
    out = [
        "# 人工標註表（judge 校準）",
        "",
        f"- 題數：{len(items)}（" + "、".join(f"{t} {n}" for t, n in sorted(counts.items())) + "）",
        "- 來源執行：" + "、".join(f"`{r}`" for r in runs),
        "- 由 `evals/label_sheet.py` 產生。**判斷欄由 Colin 填寫**，這份表沒有預先填入任何判斷，"
        "也不含自動評分結果。",
        "- open 題：每個要點在「有／漏／錯」後面寫 `有`（回答有提到且正確）、"
        "`漏`（沒提到）或 `錯`（提到但內容不符），"
        "再在「判斷」寫整題的 `對`、`錯` 或 `部分`。其他題型只填「判斷」。",
        "- 「部分」在主要指標算不通過，另外報告寬鬆比例（ADR-0005 規則 6）。",
        "- 引用是否正確另由程式計算，可以在備註中提到，但不影響判斷。",
        "- 填完執行 `uv run python -m evals.label_sheet parse`。",
        "",
    ]
    for i, (q, r) in enumerate(items, 1):
        o = r.output
        answer = o.answer.strip() or "（空白）"
        out += [
            f"### {i}. {q.qid}（{q.qtype.value}）",
            "",
            f"- run_id：`{r.run_id}`",
            "",
            f"**問題**：{q.question}",
            "",
            "**系統回答**：",
            "",
            *[f"> {line}" if line else ">" for line in answer.splitlines()],
            "",
            "- 系統引用："
            + ("、".join(f"`{c}`" for c in o.citations) if o.citations else "（無）"),
            f"- 系統自稱拒答：{'是' if o.refused else '否'}",
            *_criteria(q),
            "- 判斷（對／錯／部分）：",
            "- 備註：",
            "",
        ]
    return "\n".join(out)


def render_mobile(items: Sequence[Item]) -> str:
    """手機閱讀版：只有題號、問題、回答、要點。"""
    out = ["# 標註表（手機閱讀版）", "", "判斷請填在 `evals/labels/label-sheet.md`。", ""]
    for i, (q, r) in enumerate(items, 1):
        out += [f"## {i}. {q.qid}", "", f"**問**：{q.question}", "", "**答**：", ""]
        out += [line for line in (r.output.answer.strip() or "（空白）").splitlines()]
        out.append("")
        if q.should_refuse:
            out.append("要點：應拒答")
        elif q.rubric:
            out += [f"{j}. {p}" for j, p in enumerate(rubric_points(q.rubric)[0], 1)]
        else:
            out.append("要點：" + "、".join(q.key_facts))
        out.append("")
    return "\n".join(out)


def load_run(run_id: str, results_dir: Path = RESULTS) -> list[Item]:
    summary = json.loads((results_dir / f"{run_id}.summary.json").read_text(encoding="utf-8"))
    if summary["split"] not in ("dev", "calibration"):
        raise ValueError("label sheets use dev or calibration runs only, never test")
    questions = {q.qid: q for q in load_questions(question_files(summary["split"]))}
    with (results_dir / f"{run_id}.jsonl").open(encoding="utf-8") as f:
        records = [RunRecord.model_validate_json(x) for x in f if x.strip()]
    return [(questions[r.qid], r) for r in records if r.qid in questions]


def make(
    calibration_run: str,
    dev_run: str,
    *,
    results_dir: Path = RESULTS,
    out: Path = SHEET,
    mobile: Path = MOBILE,
) -> list[Item]:
    cal, dev = load_run(calibration_run, results_dir), load_run(dev_run, results_dir)
    opens = [it for it in cal + dev if it[0].qtype is QType.OPEN]
    items = select(opens, dev)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(items) + "\n", encoding="utf-8", newline="\n")
    mobile.parent.mkdir(parents=True, exist_ok=True)
    mobile.write_text(render_mobile(items) + "\n", encoding="utf-8", newline="\n")
    return items


# ---------------------------------------------------------------- 讀回


def parse(sheet: Path = SHEET) -> list[JudgeLabel]:
    """讀填好的表。整題「判斷」沒填的略過；填了不在選項內的會報錯。"""
    run_id: str | None = None
    qid: str | None = None
    verdict: str | None = None
    points: list[str] = []
    labels: list[JudgeLabel] = []
    for line in sheet.read_text(encoding="utf-8").splitlines():
        if m := _HEAD.match(line):
            qid, run_id, verdict, points = m.group(1), None, None, []
        elif m := _RUN.match(line):
            run_id = m.group(1)
        elif m := _POINT.match(line):
            p = m.group(1).strip()
            if p and p not in POINT_VERDICTS:
                raise ValueError(f"{qid}: point verdict must be one of {POINT_VERDICTS}, got {p!r}")
            points.append(p)
        elif m := _VERDICT.match(line):
            verdict = m.group(1).strip()
            if verdict and verdict not in VERDICTS:
                raise ValueError(f"{qid}: verdict must be one of {list(VERDICTS)}, got {verdict!r}")
        elif (m := _NOTE.match(line)) and verdict:
            if run_id is None or qid is None:
                raise ValueError(f"{qid}: question without a run_id line")
            note = m.group(1).strip()
            labels.append(
                JudgeLabel(
                    run_id=run_id,
                    qid=qid,
                    passed=VERDICTS[verdict],
                    partial=verdict == "部分",
                    points=points,
                    notes=f"{verdict}；{note}" if note else verdict,
                )
            )
    return labels


def pass_rates(labels: list[JudgeLabel]) -> dict[str, dict[str, float | int | None]]:
    """ADR-0005 規則 6：嚴格（部分＝不通過）為主，寬鬆（部分＝通過）並列，各自標 n。"""
    n = len(labels)

    def rate(k: int) -> float | None:
        return round(k / n, 3) if n else None

    return {
        "strict": {"value": rate(sum(x.passed for x in labels)), "n": n},
        "lenient": {"value": rate(sum(x.passed or x.partial for x in labels)), "n": n},
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make")
    m.add_argument("--calibration", required=True, help="run_id of a --split calibration run")
    m.add_argument("--dev", required=True, help="run_id of a --split dev run")
    sub.add_parser("parse")
    a = p.parse_args(argv)
    if a.cmd == "make":
        items = make(a.calibration, a.dev)
        counts = Counter(q.qtype.value for q, _ in items)
        print(f"wrote {SHEET} and {MOBILE}: {len(items)} questions {dict(sorted(counts.items()))}")
    else:
        labels = parse()
        with LABELS.open("w", encoding="utf-8", newline="\n") as f:
            for lab in labels:
                f.write(lab.model_dump_json() + "\n")
        print(f"wrote {len(labels)} labels to {LABELS}: {pass_rates(labels)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
