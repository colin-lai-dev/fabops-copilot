"""人工標註表（judge 校準，ADR-0005／0008）：產生標註表，以及把 Colin 填好的表轉成 JudgeLabel。

標註結果必須是 Colin 的判斷（CLAUDE.md）：這裡只準備題目、系統回答與評分準則，
**不放任何判斷**——連 score.py 的自動評分結果也不放，避免先入為主。

    uv run python -m evals.label_sheet make <run_id>     # 產生 evals/labels/label-sheet.md
    uv run python -m evals.label_sheet parse             # 填好後轉成 evals/judge_labels.jsonl

選題：從一次 dev 執行中選 50 題，各題型都要有，open 題優先（全部收入），其餘依題型分層抽樣。
只能用 dev 的執行結果。
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

from evals.run import EVALS, RESULTS, check_split_allowed, question_files
from evals.schema import JudgeLabel, QType, Question, RunRecord, load_questions

SHEET = EVALS / "labels" / "label-sheet.md"
LABELS = EVALS / "judge_labels.jsonl"
SEED = 20261109
N = 50
VERDICTS = {"對": True, "錯": False, "部分": False}  # 「部分」嚴格算不通過（ADR-0005 規則 6）
_VERDICT = re.compile(r"^- 判斷（對／錯／部分）：(.*)$")
_NOTE = re.compile(r"^- 備註：(.*)$")
_HEAD = re.compile(r"^### \d+\. (\S+)")
_RUN = re.compile(r"^- run_id：`([^`]+)`")


def select(questions: list[Question], n: int = N, seed: int = SEED) -> list[Question]:
    """open 題全收；其餘依題型比例分配，每個題型至少 1 題；結果依原順序排列。"""
    if len(questions) <= n:
        return list(questions)
    rng = random.Random(seed)
    opens = [q for q in questions if q.qtype is QType.OPEN][:n]
    by_type: dict[QType, list[Question]] = defaultdict(list)
    for q in questions:
        if q.qtype is not QType.OPEN:
            by_type[q.qtype].append(q)
    budget = n - len(opens)
    total = sum(len(v) for v in by_type.values())
    # 最大餘數法：先取整數部分（至少 1），剩下的名額給小數部分最大的題型
    exact = {t: budget * len(v) / total for t, v in by_type.items()}
    quota = {t: max(1, int(x)) for t, x in exact.items()}
    for t in sorted(exact, key=lambda t: exact[t] - int(exact[t]), reverse=True):
        if sum(quota.values()) >= budget:
            break
        if quota[t] < len(by_type[t]):
            quota[t] += 1
    picked = {q.qid for q in opens}
    for t, qs in by_type.items():
        picked |= {q.qid for q in rng.sample(qs, quota[t])}
    return [q for q in questions if q.qid in picked]


def _criteria(q: Question) -> list[str]:
    if q.should_refuse:
        lines = ["應拒答（資料中沒有答案）"]
        if q.forbidden_facts:
            lines.append("不得出現：" + "、".join(q.forbidden_facts))
        return lines
    lines = []
    if q.rubric:
        lines.append(f"評分準則：{q.rubric}")
    if q.key_facts:
        lines.append("關鍵事實（全部都要有）：" + "、".join(q.key_facts))
    lines.append("應引用：" + "、".join(f"`{d}`" for d in q.expected_doc_ids))
    return lines


def render(run_id: str, questions: list[Question], records: dict[str, RunRecord]) -> str:
    counts: dict[str, int] = defaultdict(int)
    for q in questions:
        counts[q.qtype.value] += 1
    out = [
        "# 人工標註表（judge 校準）",
        "",
        f"- run_id：`{run_id}`",
        f"- 題數：{len(questions)}（"
        + "、".join(f"{t} {n}" for t, n in sorted(counts.items()))
        + "）",
        "- 由 `evals/label_sheet.py` 產生。**判斷欄由 Colin 填寫**，這份表沒有預先填入任何判斷，"
        "也不含自動評分結果。",
        "- 填法：在「判斷」後面寫 `對`、`錯` 或 `部分`；有理由就寫在「備註」。"
        "填完執行 `uv run python -m evals.label_sheet parse`。",
        "- 判斷標準：回答是否滿足每題下方的評分準則（關鍵事實、拒答）。"
        "引用是否正確另由程式計算，可以在備註中提到，但不影響判斷。",
        "",
    ]
    for i, q in enumerate(questions, 1):
        o = records[q.qid].output
        answer = o.answer.strip() or "（空白）"
        out += [
            f"### {i}. {q.qid}（{q.qtype.value}）",
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
            *[f"- {c}" for c in _criteria(q)],
            "- 判斷（對／錯／部分）：",
            "- 備註：",
            "",
        ]
    return "\n".join(out)


def make(run_id: str, results_dir: Path = RESULTS, out: Path = SHEET) -> Path:
    summary = json.loads((results_dir / f"{run_id}.summary.json").read_text(encoding="utf-8"))
    if summary["split"] != "dev":
        raise ValueError("label sheets are built from dev runs only")
    check_split_allowed(summary["split"], allow_test=False)
    questions = load_questions(question_files("dev"))
    with (results_dir / f"{run_id}.jsonl").open(encoding="utf-8") as f:
        records = {r.qid: r for r in (RunRecord.model_validate_json(x) for x in f if x.strip())}
    chosen = select([q for q in questions if q.qid in records])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(run_id, chosen, records) + "\n", encoding="utf-8", newline="\n")
    return out


def parse(sheet: Path = SHEET) -> list[JudgeLabel]:
    """讀填好的表。沒填判斷的題目略過；填了但不是 對／錯／部分 的會報錯。"""
    run_id, qid, verdict = None, None, None
    labels: list[JudgeLabel] = []
    for line in sheet.read_text(encoding="utf-8").splitlines():
        if m := _RUN.match(line):
            run_id = m.group(1)
        elif m := _HEAD.match(line):
            qid, verdict = m.group(1).split("（")[0], None
        elif m := _VERDICT.match(line):
            verdict = m.group(1).strip()
            if verdict and verdict not in VERDICTS:
                raise ValueError(f"{qid}: verdict must be one of {list(VERDICTS)}, got {verdict!r}")
        elif (m := _NOTE.match(line)) and verdict:
            if run_id is None or qid is None:
                raise ValueError("sheet has no run_id or question heading")
            note = m.group(1).strip()
            notes = f"{verdict}；{note}" if note else verdict
            labels.append(
                JudgeLabel(
                    run_id=run_id,
                    qid=qid,
                    passed=VERDICTS[verdict],
                    partial=verdict == "部分",
                    notes=notes,
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
    m.add_argument("run_id")
    sub.add_parser("parse")
    a = p.parse_args(argv)
    if a.cmd == "make":
        print(f"wrote {make(a.run_id)}")
    else:
        labels = parse()
        with LABELS.open("w", encoding="utf-8", newline="\n") as f:
            for lab in labels:
                f.write(lab.model_dump_json() + "\n")
        print(f"wrote {len(labels)} labels to {LABELS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
