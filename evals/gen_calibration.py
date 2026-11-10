"""judge 校準題庫：open 題（交接指示 003 補充第 8 點）。

judge 只評 open 題（ADR-0005），但 dev 只有 3 題 open，不夠校準。這個題庫用和手寫 open 題
（`evals/handwritten.jsonl`，H-0001～H-0008）**相同的模板**——情境問題＋5 個評分要點——
對**手寫 open 題沒用到的**現行 SOP 各出一題。

⚠️ 只用於 judge 校準（人工標註與 judge 一致率）：**不進 dev/test、不計入任何系統指標**。
寫到 `evals/calibration/open.jsonl`；`evals/run.py --split calibration` 可以對它跑系統。

數值（等待分鐘、連續次數、通知對象、保養方式、監控晶圓、升級時數）都直接從 SOP 內文抽出，
評分要點與文件逐字一致。

    uv run python -m evals.gen_calibration
"""

from __future__ import annotations

import random
import re
import sys
from pathlib import Path
from typing import Any

from evals.corpus import check_questions, load_corpus
from evals.gen_leak_cases import USERS, insider_order
from evals.run import load_scopes
from evals.schema import QType, Question, dump_questions, load_questions
from fabops.authz.policy import visible
from fabops.data.seed import read_jsonl

EVALS = Path(__file__).resolve().parent
OUT = EVALS / "calibration" / "open.jsonl"
HANDWRITTEN = EVALS / "handwritten.jsonl"
SEED = 20261109

_SCOPE = re.compile(r"規範 (FX\d) (\S+?)區 (\S+) 機台發生「(.+?)」")
_ROW = re.compile(r"^\| ([^|]+?) \| (\d+) \| (\d+) \| ([^|]+?) \|$", re.M)
_WAIT = re.compile(r"等待 (\d+) 分鐘後重新量測")
_HOLD = re.compile(r"若連續 (\d+) 次量測超出上限，hold 受影響批號並通知(\S+?)。")
_PM = re.compile(r"執行(\S+?)後，以 (\d+) 片監控晶圓驗證，通過才可復機")
_ESC = re.compile(r"異常持續超過 (\d+) 小時仍未排除，升級至(\S+?)。")


def parse_sop(doc: dict[str, Any]) -> dict[str, str]:
    body = doc["body_md"]
    found = {
        name: p.search(body)
        for name, p in {
            "scope": _SCOPE,
            "row": _ROW,
            "wait": _WAIT,
            "hold": _HOLD,
            "pm": _PM,
            "esc": _ESC,
        }.items()
    }
    missing = [k for k, m in found.items() if m is None]
    if missing:
        raise ValueError(f"{doc['doc_id']}: cannot parse {missing}")
    fab, _area, eqp, alarm = found["scope"].groups()  # type: ignore[union-attr]
    _param, _low, high, unit = found["row"].groups()  # type: ignore[union-attr]
    return {
        "fab": fab,
        "eqp": eqp,
        "alarm": alarm,
        "high": high,
        "unit": unit.strip(),
        "wait": found["wait"].group(1),  # type: ignore[union-attr]
        "consecutive": found["hold"].group(1),  # type: ignore[union-attr]
        "notify": found["hold"].group(2),  # type: ignore[union-attr]
        "pm": found["pm"].group(1),  # type: ignore[union-attr]
        "wafers": found["pm"].group(2),  # type: ignore[union-attr]
        "esc_hours": found["esc"].group(1),  # type: ignore[union-attr]
        "esc_to": found["esc"].group(2),  # type: ignore[union-attr]
    }


def over_limit(high: str) -> str:
    """略高於上限的量測值（約 1.15 倍）。"""
    v = int(high) * 1.15
    return str(round(v)) if int(high) >= 20 else f"{v:.1f}"


def rubric(f: dict[str, str]) -> str:
    return (
        "要點：(1) 先確認該腔體是否在保養中，並暫停該腔體派貨；"
        f"(2) 等待 {f['wait']} 分鐘後重新量測；"
        f"(3) 連續 {f['consecutive']} 次超出上限就 hold 受影響批號並通知{f['notify']}；"
        f"(4) 執行{f['pm']}後以 {f['wafers']} 片監控晶圓驗證才可復機；"
        f"(5) 超過 {f['esc_hours']} 小時未排除升級至{f['esc_to']}。"
        "每漏一個要點扣分；數值與 SOP 不符算錯；引用 SOP 以外的自創步驟或補償參數算錯。"
    )


def generate(
    docs: dict[str, dict[str, Any]],
    scopes: dict,
    order: list[str],
    exclude: set[str],
    seed: int = SEED,
) -> list[Question]:
    rng = random.Random(seed)
    sops = sorted(
        d["doc_id"]
        for d in docs.values()
        if d["doc_type"] == "sop"
        and not d.get("superseded_by")
        and not d["doc_id"].startswith("GEN-")
        and d["doc_id"] not in exclude
    )
    out = []
    for i, doc_id in enumerate(sops, 1):
        doc = docs[doc_id]
        f = parse_sop(doc)
        asker = next(u for u in order if visible(scopes[u], doc))
        chamber = f"CH{rng.choice('ABCD')}"
        out.append(
            Question(
                qid=f"C-OPEN-{i:04d}",
                qtype=QType.OPEN,
                source="rule",
                question=(
                    f"{f['fab']} 的 {f['eqp']} {chamber} 剛跳「{f['alarm']}」，"
                    f"量到 {over_limit(f['high'])} {f['unit']}，我現在該怎麼處理？"
                ),
                user_id=asker,
                expected_doc_ids=[doc_id],
                rubric=rubric(f),
                notes=(
                    "judge 校準題庫（不進 dev/test、不計入系統指標）；"
                    f"模板同手寫 open 題；依 {doc_id}。"
                ),
            )
        )
    return out


def main() -> int:
    docs, scopes = load_corpus(), load_scopes()
    hand = load_questions([HANDWRITTEN])
    exclude = {d for q in hand if q.qtype is QType.OPEN for d in q.expected_doc_ids}
    qs = generate(docs, scopes, insider_order(list(read_jsonl(USERS))), exclude)
    check = check_questions(qs, docs, scopes)
    if check.errors:
        print("\n".join(check.errors), file=sys.stderr)
        return 1
    dump_questions(qs, OUT)
    print(f"wrote {len(qs)} open questions to {OUT} (excluded {len(exclude)} SOPs used by H-*)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
