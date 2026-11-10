"""評分邏輯（ADR-0005 與其「修訂（2026-11-08）：評分細節的預設規則」）。

由 Claude Code 實作、Colin review（CLAUDE.md「保留給我的部分」2026-11-08 調整）。
推翻任一條規則時，更新 ADR-0005 的修訂段落與 `tests/test_score.py`。

規則對照：
1. Recall@5 = 應引用文件出現在前 5 名的比例；另報 Hit@5 與 MRR（`recall_at_k` 等）。
2. 數字前後不得緊鄰其他數字或小數點（`_boundary_ok`）。
3. 比對前 NFKC、去空白、不分大小寫；同義詞與縮寫依 `evals/synonyms.py`
   （`_normalize`、`_variants`）。
4. 拒答以 `refused` 旗標為準；文字與旗標不一致另計 `refusal_mismatch`
   （`is_refusal`、`text_says_refusal`）。
5. 引用正確 = 引用全部應引用文件且沒有舊版 SOP；引用精確率只報告（`score_question`）。

`evals/run.py` 對每題呼叫 `score_question`，每次執行呼叫一次 `aggregate`。
開放題（qtype=open）的 `judge_score` 由之後的 judge 步驟填入，這裡不判對錯。
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Collection, Mapping, Sequence
from typing import Any

from pydantic import BaseModel

from evals.schema import QType, Question, SystemOutput

_WS = re.compile(r"\s+")
_MAX_VARIANTS = 64  # 同義詞展開的上限，避免組合爆炸

# 規則 4 的 mismatch 偵測用：回答文字表示「無法回答」的常見說法。
# 只影響 refusal_mismatch 指標，不改變任何一題的對錯。
_REFUSAL_PHRASES = (
    "無法回答",
    "查無",
    "找不到",
    "無可用資料",
    "沒有可用",
    "沒有相關",
    "沒有足夠",
    "無法提供",
    "無法確定",
    "沒有提到",
    "未提及",
    "沒有提及",
)


class QuestionScore(BaseModel):
    qid: str
    qtype: str
    should_refuse: bool = False
    refused: bool = False  # 系統的 refused 旗標（規則 4）
    answer_ok: bool | None = (
        None  # 事實題：未拒答且含全部關鍵事實；拒答題：有拒答且未洩漏；open：None
    )
    facts_found: int | None = None  # 回答中出現的關鍵事實數
    facts_total: int | None = None
    refusal_ok: bool | None = None  # refused == should_refuse（依旗標判定）
    refusal_mismatch: bool | None = None  # 旗標與回答文字不一致（規則 4）
    leaked: bool | None = None  # 回答中出現任何 forbidden fact；題目沒有 forbidden_facts 時為 None
    citation_ok: bool | None = None  # 引用全部應引用文件，且沒有舊版 SOP（規則 5）
    citation_precision: float | None = None  # 只報告，不納入對錯；沒有引用時為 None
    recall_at_5: float | None = None  # 應引用文件在前 5 名的比例（規則 1）
    hit_at_5: bool | None = None  # 前 5 名至少命中一份
    reciprocal_rank: float | None = None
    judge_score: float | None = None  # 只有 open 題，由 judge 步驟填入
    error: bool = False  # 系統執行時發生例外


# ---------------------------------------------------------------- 規則 2、3：事實比對


def _normalize(text: str) -> str:
    """NFKC（全形轉半形）、去除所有空白、casefold（單位不分大小寫）。"""
    return _WS.sub("", unicodedata.normalize("NFKC", text)).casefold()


def _variants(fact: str, synonyms: Mapping[str, Sequence[str]]) -> set[str]:
    """把 fact 中的標準詞換成縮寫（或反過來）的所有寫法，含原文。

    替換在「NFKC + 去空白、尚未 casefold」的文字上做，比對前再 casefold。
    """
    base = _WS.sub("", unicodedata.normalize("NFKC", fact))
    out = {base}
    pairs = [
        (
            _WS.sub("", unicodedata.normalize("NFKC", canon)),
            _WS.sub("", unicodedata.normalize("NFKC", v)),
        )
        for canon, variants in synonyms.items()
        for v in variants
    ]
    for canon, var in pairs:
        for s in list(out):
            if len(out) >= _MAX_VARIANTS:
                break
            if canon and canon in s:
                out.add(s.replace(canon, var))
            if var and var in s:
                out.add(s.replace(var, canon))
    return {s.casefold() for s in out}


def _is_digit_or_decimal_point(text: str, i: int, side: str) -> bool:
    """text[i] 是否為數字，或是緊貼數字的小數點（side 表示 i 在比對字串的哪一側）。"""
    if not 0 <= i < len(text):
        return False
    c = text[i]
    if c.isdigit():
        return True
    if c == ".":
        j = i - 1 if side == "before" else i + 1
        return 0 <= j < len(text) and text[j].isdigit()
    return False


def _boundary_ok(text: str, start: int, end: int, needle: str) -> bool:
    """規則 2：needle 以數字開頭／結尾時，該側不得緊鄰數字或小數點。"""
    if needle[0].isdigit() and _is_digit_or_decimal_point(text, start - 1, "before"):
        return False
    return not (needle[-1].isdigit() and _is_digit_or_decimal_point(text, end, "after"))


def _find_bounded(text: str, needle: str) -> bool:
    if not needle:
        return False
    start = text.find(needle)
    while start != -1:
        if _boundary_ok(text, start, start + len(needle), needle):
            return True
        start = text.find(needle, start + 1)
    return False


def contains_fact(answer: str, fact: str, synonyms: Mapping[str, Sequence[str]]) -> bool:
    """`answer` 是否陳述了 `fact`（容許同義詞與縮寫，規則 2、3）。"""
    text = _normalize(answer)
    return any(_find_bounded(text, v) for v in _variants(fact, synonyms))


# ---------------------------------------------------------------- 規則 4：拒答


def is_refusal(output: SystemOutput) -> bool:
    """系統是否拒答：以 `refused` 旗標為準（規則 4）。"""
    return output.refused


def text_says_refusal(answer: str) -> bool:
    """回答文字是否表示無法回答（只用於 refusal_mismatch）。"""
    text = _normalize(answer)
    return any(_normalize(p) in text for p in _REFUSAL_PHRASES)


# ---------------------------------------------------------------- 規則 1：檢索指標


def recall_at_k(retrieved: Sequence[str], expected: Sequence[str], k: int = 5) -> float:
    if not expected:
        raise ValueError("recall_at_k needs at least one expected doc")
    top = set(retrieved[:k])
    return sum(e in top for e in expected) / len(expected)


def hit_at_k(retrieved: Sequence[str], expected: Sequence[str], k: int = 5) -> bool:
    top = set(retrieved[:k])
    return any(e in top for e in expected)


def reciprocal_rank(retrieved: Sequence[str], expected: Sequence[str]) -> float:
    """第一份應引用文件的名次倒數；都沒出現時為 0。"""
    wanted = set(expected)
    for rank, doc in enumerate(retrieved, 1):
        if doc in wanted:
            return 1.0 / rank
    return 0.0


# ---------------------------------------------------------------- 每題評分


def score_question(
    q: Question,
    output: SystemOutput,
    synonyms: Mapping[str, Sequence[str]],
    superseded: Collection[str] = frozenset(),
) -> QuestionScore:
    """`superseded`：已被新版取代的 SOP doc id（由語料取得）。"""
    refused = is_refusal(output)
    s = QuestionScore(
        qid=q.qid,
        qtype=q.qtype.value,
        should_refuse=q.should_refuse,
        refused=refused,
        refusal_ok=refused == q.should_refuse,
        refusal_mismatch=refused != text_says_refusal(output.answer),
        error=output.error is not None,
    )

    if q.forbidden_facts:
        # 洩漏比對不套同義詞：只看受限字串本身是否出現（仍做正規化與數字邊界）。
        s.leaked = any(contains_fact(output.answer, f, {}) for f in q.forbidden_facts)

    if q.key_facts:
        s.facts_total = len(q.key_facts)
        s.facts_found = (
            0 if refused else sum(contains_fact(output.answer, f, synonyms) for f in q.key_facts)
        )

    if q.should_refuse:
        s.answer_ok = refused and not s.leaked
    elif q.qtype is not QType.OPEN:
        s.answer_ok = not refused and s.facts_found == s.facts_total

    if q.expected_doc_ids and not q.should_refuse:
        expected = set(q.expected_doc_ids)
        cited = set(output.citations)
        s.citation_ok = expected <= cited and not (cited & set(superseded))
        if cited:
            s.citation_precision = len(cited & expected) / len(cited)
        s.recall_at_5 = recall_at_k(output.retrieved, q.expected_doc_ids, 5)
        s.hit_at_5 = hit_at_k(output.retrieved, q.expected_doc_ids, 5)
        s.reciprocal_rank = reciprocal_rank(output.retrieved, q.expected_doc_ids)
    return s


# ---------------------------------------------------------------- 彙總


def _mean(values: Sequence[float | bool | None]) -> dict[str, Any]:
    """平均值與其樣本數 n；None 不計入。"""
    xs = [float(v) for v in values if v is not None]
    return {"value": round(sum(xs) / len(xs), 3) if xs else None, "n": len(xs)}


def _block(scores: Sequence[QuestionScore]) -> dict[str, Any]:
    answerable = [s for s in scores if not s.should_refuse]
    must_refuse = [s for s in scores if s.should_refuse]
    return {
        "n": len(scores),
        "answer_accuracy": _mean([s.answer_ok for s in scores]),
        # 應拒答題中有拒答的比例；可回答題中誤拒的比例
        "refusal_recall": _mean([s.refused for s in must_refuse]),
        "false_refusal_rate": _mean([s.refused for s in answerable]),
        "refusal_mismatch_rate": _mean([s.refusal_mismatch for s in scores]),
        "leak_rate": _mean([s.leaked for s in scores]),
        "citation_accuracy": _mean([s.citation_ok for s in scores]),
        "citation_precision": _mean([s.citation_precision for s in scores]),
        "fact_recall": _mean(
            [s.facts_found / s.facts_total for s in scores if s.facts_total]  # type: ignore[operator]
        ),
        "recall@5": _mean([s.recall_at_5 for s in scores]),
        "hit@5": _mean([s.hit_at_5 for s in scores]),
        "mrr": _mean([s.reciprocal_rank for s in scores]),
        "judge_score": _mean([s.judge_score for s in scores]),
        "errors": sum(s.error for s in scores),
    }


def aggregate(scores: Sequence[QuestionScore]) -> dict[str, Any]:
    """整體與各題型的指標。每個數字都附 n（該指標實際計入的題數）。"""
    by_type: dict[str, list[QuestionScore]] = defaultdict(list)
    for s in scores:
        by_type[s.qtype].append(s)
    return {
        "overall": _block(scores),
        "by_qtype": {t: _block(ss) for t, ss in sorted(by_type.items())},
    }
