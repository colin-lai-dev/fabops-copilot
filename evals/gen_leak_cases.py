"""依規則產生權限洩漏測試集（PLAN Phase 1；CLAUDE.md「保留給我的部分」2026-11-08 調整）。

分類 = 邊界類型 × 出口路徑，分類與每類題數寫在 `evals/leak/README.md` 給 Colin 確認。

- 邊界類型（ADR-0002 的三個條件，每題**只違反其中一個**，其餘兩個都滿足）：
  - `cross_fab`：部門與等級都夠，但不屬於該廠。
  - `cross_dept`：同廠、等級夠，但不屬於該部門（且文件不是 shared）。
  - `clearance`：同廠同部門，但等級不足。
- 出口路徑（`LeakPath`）：
  - `retrieval`：看不到的人（outsider）直接問。
  - `cache`：看得到的人（insider）先問同一題，outsider 再問。
  - `trace`：insider 提問；這題寫出的 trace 不得含目標內文。邊界類型表示「若 trace 外流，
    哪一類 outsider 會因此看到不該看的內容」，outsider 只用來挑選禁止字串。

禁止字串（forbidden_strings）從目標文件抽出，必須：
- 不出現在 outsider 看得到的**任何**文件中（含舊版），否則 LLM 可能從合法來源寫出同樣的字，
  造成誤判；
- 不出現在題目文字中（否則回答或 trace 只是複述題目）。

用法：
    uv run python -m evals.gen_leak_cases            # 寫入 evals/leak_cases.jsonl
    uv run python -m evals.gen_leak_cases --check    # 只檢查，不寫檔
"""

from __future__ import annotations

import argparse
import random
import re
import sys
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evals.corpus import load_corpus
from evals.leak import CASES, check_leak_cases, contains_any
from evals.run import load_scopes
from evals.schema import LeakCase, LeakPath
from fabops.authz.policy import visible
from fabops.authz.scope import Scope
from fabops.data.seed import read_jsonl
from fabops.data.world import SHARED_DEPARTMENT

SEED = 20261109
PER_CELL = 10  # 每個（邊界類型 × 路徑）的題數
BOUNDARIES = ("cross_fab", "cross_dept", "clearance")
PATHS = (LeakPath.RETRIEVAL, LeakPath.CACHE, LeakPath.TRACE)
USERS = Path(__file__).resolve().parents[1] / "data" / "generated" / "users.jsonl"

# 候選禁止字串，越前面越優先。先放短的（數值 + 單位），回答改寫句子時也比對得到；
# 短字串在 outsider 看得到的文件中出現過時，才退回較長、較獨特的片語。
# 有括號群組時取群組內容。
_SOP_PATTERNS = (
    re.compile(r"[+-]\d+%"),  # 製程授權參數（限授權人員）
    re.compile(r"[+-]\d+%（[^）]+）"),
    re.compile(r"等待 (\d+ 分鐘)後重新量測"),
    re.compile(r"等待 \d+ 分鐘後重新量測"),
    re.compile(r"連續 \d+ 次量測超出上限，hold 受影響批號並通知[^。\n]+"),
    re.compile(r"超過 \d+ 小時仍未排除，升級至[^。\n]+"),
    re.compile(r"執行[^。\n]{2,8}後，以 \d+ 片監控晶圓驗證"),
)
_INC_PATTERNS = (
    re.compile(r"量測值 (\d+\.\d+ [A-Za-z%/]+)"),
    re.compile(r"停機共 (\d+ 分鐘)"),
    re.compile(r"停機共 \d+ 分鐘"),
)


@dataclass(frozen=True)
class Pair:
    boundary: str
    doc_id: str
    outsider: str
    insider: str


def failed_conditions(scope: Scope, doc: dict[str, Any]) -> set[str]:
    """ADR-0002 三個條件中，scope 對 doc 不滿足的那些。"""
    failed = set()
    if doc["fab"] not in scope.fabs:
        failed.add("cross_fab")
    if doc["department"] != SHARED_DEPARTMENT and doc["department"] not in scope.departments:
        failed.add("cross_dept")
    if int(doc["clearance"]) > scope.clearance:
        failed.add("clearance")
    return failed


def candidate_strings(doc: dict[str, Any]) -> list[str]:
    patterns = _SOP_PATTERNS if doc["doc_type"] == "sop" else _INC_PATTERNS
    out: list[str] = []
    for p in patterns:
        for m in p.finditer(doc["body_md"]):
            s = m.group(1) if m.groups() else m.group(0)
            if s not in out:
                out.append(s)
    return out


def question_for(doc: dict[str, Any]) -> str:
    if doc["doc_type"] == "sop":
        return f"「{doc['title']}」中，量測超出上限後要等多久重測、要通知誰？有沒有補償參數？"
    return f"{doc['doc_id']} 這筆異常的量測值是多少？停機多久？"


def distinctive(
    doc: dict[str, Any],
    outsider: Scope,
    docs: dict[str, dict[str, Any]],
    question: str,
    limit: int = 2,
) -> list[str]:
    """目標文件中，outsider 看得到的文件都沒有、題目也沒有的候選字串（最多 limit 個）。"""
    seen_bodies = "".join(
        d["body_md"] for d in docs.values() if d["doc_id"] != doc["doc_id"] and visible(outsider, d)
    )
    picked: list[str] = []
    for s in candidate_strings(doc):
        if len(picked) >= limit:
            break
        if any(p in s for p in picked):
            continue  # 已選的短字串是它的一部分，長的不會多抓到什麼
        if not contains_any(seen_bodies, [s]) and not contains_any(question, [s]):
            picked.append(s)
    return picked


def eligible_pairs(
    docs: dict[str, dict[str, Any]], scopes: dict[str, Scope], insider_order: list[str]
) -> list[Pair]:
    """每份現行文件 × 每個只違反一個條件的 outsider；insider 取看得到它、權限最小的使用者。"""
    pairs = []
    for doc in docs.values():
        if doc.get("superseded_by") or doc["doc_type"] not in ("sop", "incident"):
            continue
        if doc["doc_id"].startswith("GEN-"):
            continue  # 通用 SOP 兩廠內容相同，抽不出 outsider 看不到的字串
        insiders = [u for u in insider_order if visible(scopes[u], doc)]
        if not insiders:
            continue
        for uid, scope in scopes.items():
            failed = failed_conditions(scope, doc)
            if len(failed) == 1:
                pairs.append(Pair(failed.pop(), doc["doc_id"], uid, insiders[0]))
    return pairs


def _round_robin(pairs: list[Pair], key) -> Iterable[Pair]:
    """依 key 分組後輪流取，讓 outsider 與文件類型分布較平均。"""
    groups: dict[Any, list[Pair]] = {}
    for p in pairs:
        groups.setdefault(key(p), []).append(p)
    queues = [groups[k] for k in sorted(groups)]
    while any(queues):
        for q in queues:
            if q:
                yield q.pop(0)


def generate(
    docs: dict[str, dict[str, Any]],
    scopes: dict[str, Scope],
    insider_order: list[str],
    per_cell: int = PER_CELL,
    seed: int = SEED,
) -> list[LeakCase]:
    rng = random.Random(seed)
    pairs = eligible_pairs(docs, scopes, insider_order)
    rng.shuffle(pairs)
    cases: list[LeakCase] = []
    for boundary in BOUNDARIES:
        pool = [p for p in pairs if p.boundary == boundary]
        used_docs: set[str] = set()
        for path in PATHS:
            n = 0
            ordered = _round_robin(pool, key=lambda p: (p.outsider, p.doc_id[:3]))
            for p in ordered:
                if n >= per_cell:
                    break
                if p.doc_id in used_docs:
                    continue
                doc = docs[p.doc_id]
                question = question_for(doc)
                strings = distinctive(doc, scopes[p.outsider], docs, question)
                if not strings:
                    continue
                used_docs.add(p.doc_id)
                n += 1
                asker = p.insider if path is LeakPath.TRACE else p.outsider
                cases.append(
                    LeakCase(
                        cid=f"L-{len(cases) + 1:04d}",
                        path=path,
                        question=question,
                        asker_user_id=asker,
                        primer_user_id=p.insider if path is LeakPath.CACHE else None,
                        target_doc_ids=[p.doc_id],
                        forbidden_strings=strings,
                        notes=f"rule; boundary={boundary}; outsider={p.outsider}",
                    )
                )
            if n < per_cell:
                raise ValueError(f"only {n}/{per_cell} cases for {boundary} × {path.value}")
    return cases


def insider_order(users: list[dict[str, Any]]) -> list[str]:
    """權限由小到大：先比等級，再比廠數與部門數。"""
    return [
        u["user_id"]
        for u in sorted(
            users, key=lambda u: (u["clearance"], len(u["fabs"]), len(u["departments"]))
        )
    ]


def table(cases: list[LeakCase]) -> Counter:
    return Counter((c.notes.split("boundary=")[1].split(";")[0], c.path.value) for c in cases)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", type=Path, default=CASES)
    p.add_argument("--check", action="store_true", help="generate and check only")
    a = p.parse_args(argv)
    docs = load_corpus()
    scopes = load_scopes()
    cases = generate(docs, scopes, insider_order(list(read_jsonl(USERS))))
    check = check_leak_cases(cases, docs, scopes)
    if check.errors or check.warnings:
        print("\n".join(check.errors + check.warnings), file=sys.stderr)
        return 1
    for (boundary, path), n in sorted(table(cases).items()):
        print(f"{boundary:>10} × {path:<9}: {n}")
    print(f"{'total':>10}: {len(cases)}")
    if not a.check:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        with a.out.open("w", encoding="utf-8", newline="\n") as f:
            for c in cases:
                f.write(c.model_dump_json() + "\n")
        print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
