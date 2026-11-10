"""洩漏測試用的「故意不安全」baseline（交接指示 003 第 3 點）。**只能在 eval 中使用。**

⚠️ 這個模組裡的東西刻意拿掉權限檢查，用來證明正式路徑的檢查確實擋住了洩漏。
不得被 `src/fabops/` 匯入，也不得用在 API 或 agent；
`tests/test_baselines.py` 檢查 `src/` 沒有匯入它。

- `UnfilteredRetriever`：檢索不做權限 pre-filter（ADR-0003 的反例），其餘不變：
  引用出口檢查仍在，所以洩漏只會出現在回答文字或檢索結果。
- `NaiveQuestionCache`：在整個 RAG 前面加一層只以「問題文字」當 key 的快取，
  不含權限範圍、也不含檢索內容，模擬常見的問題層快取。命中時直接回傳上一位提問者的輸出。

系統名稱（`evals/systems.py`）：`rag-<preset>-noprefilter`、`rag-<preset>-naivecache`。
"""

from __future__ import annotations

from typing import Any

from evals.schema import SystemOutput
from fabops.authz.scope import Scope
from fabops.rag.retrieve import Retriever

UNSAFE_SUFFIXES = ("-noprefilter", "-naivecache")


class UnfilteredRetriever(Retriever):
    """⚠️ eval 專用：權限條件換成 TRUE，任何人都檢索得到所有文件。"""

    def _where(self, scope: Scope, doc_type: str | None = None) -> tuple[str, dict[str, Any]]:
        cond, params = "TRUE", {}
        if not self.cfg.include_superseded:
            cond += " AND d.superseded_by IS NULL"
        if doc_type is not None:
            cond += " AND d.doc_type = %(doc_type)s"
            params["doc_type"] = doc_type
        return cond, params


class NaiveQuestionCache:
    """⚠️ eval 專用：以問題文字為 key 的快取，包在任何 System 外面（同一個程序內有效）。"""

    def __init__(self, inner: Any, name: str):
        self.inner, self.name = inner, name
        self.answerer = getattr(inner, "answerer", None)  # 讓 leak.py 找得到 trace 檔
        self._cache: dict[str, SystemOutput] = {}
        self.hits = 0

    def answer(self, question: str, scope: Scope) -> SystemOutput:
        key = question.strip()  # 刻意不含 scope
        if key in self._cache:
            self.hits += 1
            return self._cache[key].model_copy(update={"latency_ms": 0.0})
        out = self.inner.answer(question, scope)
        if out.error is None:
            self._cache[key] = out
        return out
