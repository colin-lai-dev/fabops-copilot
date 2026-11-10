"""open 題的要點字串比對（rubric match）：judge 之前的代理指標，也是 judge 要贏過的下限。

open 題的評分準則由模板產生，每個要點都有可比對的關鍵詞（數字＋單位、通知對象、保養類型）。
這裡只檢查關鍵詞有沒有出現在回答裡（沿用 `score.contains_fact` 的正規化、數字邊界與同義詞），
**不判斷語意**：提到但說錯（例如把 46 ppm 判成未超標）抓不到，所以它不能取代 judge。

    uv run python -m evals.rubric_match <run_id> [<run_id> ...]   # 只限 dev 與 calibration
    uv run python -m evals.rubric_match --agreement               # 與 Colin 標註的一致率

每個要點：關鍵詞全部出現 → `有`，否則 → `漏`。整題：全部 `有` → 對，全部 `漏` → 錯，其餘 → 部分
（與標註表的換算方式相同，交接指示 004）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path

from evals.label_sheet import LABELS, load_run, rubric_points
from evals.run import RESULTS
from evals.schema import JudgeLabel, QType
from evals.score import contains_fact
from evals.synonyms import synonym_table

_WAIT = re.compile(r"等待\s*(\d+)\s*分鐘")
_HOLD = re.compile(r"連續\s*(\d+)\s*次.*通知(\S+)$")
_PM = re.compile(r"執行(\S+?)後以\s*(\d+)\s*片")
_ESC = re.compile(r"超過\s*(\d+)\s*小時")
_NUM_UNIT = re.compile(r"\d+(?:\.\d+)?\s*(?:分鐘|小時|次|片|%|ppm|°C|s|wafers)")


def point_needles(point: str) -> list[str]:
    """要點 → 回答中必須出現的關鍵詞（全部出現才算有）。"""
    if "保養中" in point:
        return ["保養中", "暫停"]
    if m := _WAIT.search(point):
        return [f"{m.group(1)} 分鐘"]
    if m := _HOLD.search(point):
        return [f"{m.group(1)} 次", m.group(2)]
    if m := _PM.search(point):
        return [m.group(1), f"{m.group(2)} 片"]
    if m := _ESC.search(point):
        return [f"{m.group(1)} 小時"]
    return _NUM_UNIT.findall(point) or [point]


def match_points(
    answer: str, rubric: str, synonyms: Mapping[str, Sequence[str]], refused: bool = False
) -> list[str]:
    points, _ = rubric_points(rubric)
    if refused:
        return ["漏"] * len(points)
    return [
        "有" if all(contains_fact(answer, n, synonyms) for n in point_needles(p)) else "漏"
        for p in points
    ]


def verdict(points: Sequence[str]) -> str:
    if points and all(p == "有" for p in points):
        return "對"
    if all(p != "有" for p in points):
        return "錯"
    return "部分"


def score_run(run_id: str, results_dir: Path = RESULTS) -> dict[str, dict]:
    """每題 open 的要點判斷與整題判斷（只接受 dev／calibration 執行，見 `load_run`）。"""
    table = synonym_table()
    out = {}
    for q, r in load_run(run_id, results_dir):
        if q.qtype is not QType.OPEN:
            continue
        pts = match_points(r.output.answer, q.rubric or "", table, r.output.refused)
        out[q.qid] = {"points": pts, "verdict": verdict(pts)}
    return out


def summarize(scored: Mapping[str, Mapping]) -> dict:
    v = Counter(x["verdict"] for x in scored.values())
    pts = [p for x in scored.values() for p in x["points"]]
    n = len(scored)
    return {
        "n": n,
        "verdicts": {k: v.get(k, 0) for k in ("對", "部分", "錯")},
        "strict_pass": round(v["對"] / n, 3) if n else None,
        "point_recall": {
            "value": round(pts.count("有") / len(pts), 3) if pts else None,
            "n": len(pts),
        },
    }


def label_verdict(lab: JudgeLabel) -> str:
    return "對" if lab.passed else ("部分" if lab.partial else "錯")


def agreement(labels: Sequence[JudgeLabel], results_dir: Path = RESULTS) -> dict:
    """要點比對與 Colin 標註的一致率（只看有逐點標註的 open 題）。"""
    labels = [lab for lab in labels if lab.points]
    scored: dict[tuple[str, str], dict] = {}
    for run_id in sorted({lab.run_id for lab in labels}):
        for qid, x in score_run(run_id, results_dir).items():
            scored[(run_id, qid)] = x
    q_agree = p_agree = p_total = 0
    for lab in labels:
        x = scored[(lab.run_id, lab.qid)]
        q_agree += x["verdict"] == label_verdict(lab)
        # Colin 的「漏」與「錯」未區分（交接指示 004），兩者都視為「沒有」
        human = ["有" if p == "有" else "漏" for p in lab.points]
        p_agree += sum(a == b for a, b in zip(human, x["points"], strict=True))
        p_total += len(human)
    return {
        "question": {"agree": q_agree, "n": len(labels)},
        "point": {"agree": p_agree, "n": p_total},
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("run_ids", nargs="*")
    p.add_argument("--agreement", action="store_true")
    a = p.parse_args(argv)
    if a.agreement:
        with LABELS.open(encoding="utf-8") as f:
            labels = [JudgeLabel.model_validate_json(x) for x in f if x.strip()]
        print(json.dumps(agreement(labels), ensure_ascii=False))
    for run_id in a.run_ids:
        print(run_id, json.dumps(summarize(score_run(run_id)), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
