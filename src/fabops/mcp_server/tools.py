"""The five read-only agent tools (PLAN Phase 2), independent of MCP.

Each tool takes the caller's `Scope` as a separate, server-supplied argument; the MCP layer
(`server.py`) resolves it from the verified token and never exposes it to the LLM (ADR-0001).

Exit check (CLAUDE.md: every data exit): the store already filters by scope; before a
result leaves a tool, every row and search hit is checked again with `visible()` and dropped
if it fails, and the drop count goes to the masked trace. A record that does not exist and
one the caller may not see get the same "not found" reply, so tools are no existence oracle.

Returned text from documents and MES rows is data for the agent, never instructions.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Protocol

from fabops.authz.policy import visible
from fabops.authz.scope import Scope
from fabops.authz.trace import Tracer
from fabops.mcp_server.store import MesStore
from fabops.rag.retrieve import Retrieval

ID_PATTERN = re.compile(r"^[A-Za-z0-9-]{1,40}$")
CHAMBER_SUFFIX = re.compile(r"-CH[A-D]$")
MAX_QUERY_CHARS = 300
MAX_LIMIT = 20
NOT_FOUND = "查無此資料，或你沒有權限查看。"
PERMISSION_KEYS = ("department", "clearance")  # internal attributes, not shown to the agent

TOOL_NAMES = (
    "get_lot_history",
    "get_equipment_status",
    "get_dispatch_log",
    "search_sop",
    "search_similar_incidents",
)


class Searcher(Protocol):
    def search(self, query: str, scope: Scope, doc_type: str | None = None) -> Retrieval: ...


class ToolInputError(ValueError):
    """Invalid arguments; the message is safe to show to the agent."""


def _id(value: str, what: str) -> str:
    value = (value or "").strip()
    if not ID_PATTERN.match(value):
        raise ToolInputError(f"{what} 格式不正確")
    return value


def _limit(n: int) -> int:
    if not 1 <= int(n) <= MAX_LIMIT:
        raise ToolInputError(f"limit 必須介於 1 到 {MAX_LIMIT}")
    return int(n)


def _query(q: str) -> str:
    q = (q or "").strip()
    if not q:
        raise ToolInputError("query 不可為空")
    return q[:MAX_QUERY_CHARS]


class MesTools:
    def __init__(
        self,
        store: MesStore,
        searcher: Searcher | None = None,
        tracer: Tracer | None = None,
        *,
        exit_checks: bool = True,
    ):
        """`exit_checks=False` exists only for the eval-only leak control systems (evals/)."""
        self.store, self.searcher = store, searcher
        self.tracer = tracer or Tracer.from_env()
        self.exit_checks = exit_checks

    # ------------------------------------------------------------------ exit check

    def _out(self, scope: Scope, rows: list[dict[str, Any]], dropped: list[int]) -> list[dict]:
        kept = []
        for r in rows:
            if self.exit_checks and not visible(scope, r):
                dropped[0] += 1
                continue
            kept.append({k: v for k, v in r.items() if k not in PERMISSION_KEYS})
        return kept

    def _trace(self, tool: str, scope: Scope, result: dict, dropped: int, **fields) -> None:
        self.tracer.event(
            "tool",
            trace_id=uuid.uuid4().hex[:12],
            tool=tool,
            scope=scope.key(),
            n_hits=result.get("n", 0),
            dropped_rows=dropped,
            **fields,
        )

    # ------------------------------------------------------------------ MES tools

    def get_lot_history(self, scope: Scope, lot_id: str, limit: int = 10) -> dict:
        lot_id, limit, dropped = _id(lot_id, "lot_id"), _limit(limit), [0]
        lot = self._out(scope, self.store.select("lots", scope, {"lot_id": lot_id}), dropped)
        if not lot:
            result = {"found": False, "message": NOT_FOUND, "n": 0}
        else:
            w = {"lot_id": lot_id}
            disp = self.store.select("dispatch_log", scope, w, newest_first=limit)
            alarms = self.store.select("alarms", scope, w, newest_first=limit)
            result = {
                "found": True,
                "lot": lot[0],
                "dispatches": self._out(scope, disp, dropped),
                "alarms": self._out(scope, alarms, dropped),
            }
            result["n"] = 1 + len(result["dispatches"]) + len(result["alarms"])
        self._trace("get_lot_history", scope, result, dropped[0])
        return result

    def get_equipment_status(self, scope: Scope, equipment_id: str, limit: int = 5) -> dict:
        eq_id, limit, dropped = _id(equipment_id, "equipment_id"), _limit(limit), [0]
        eq_id = CHAMBER_SUFFIX.sub("", eq_id)  # a chamber id names its equipment
        w = {"equipment_id": eq_id}
        eq = self._out(scope, self.store.select("equipment", scope, w), dropped)
        if not eq:
            result = {"found": False, "message": NOT_FOUND, "n": 0}
        else:
            result = {
                "found": True,
                "equipment": eq[0],
                "chambers": self._out(scope, self.store.select("chambers", scope, w), dropped),
                "recent_alarms": self._out(
                    scope, self.store.select("alarms", scope, w, newest_first=limit), dropped
                ),
                "maintenance": self._out(
                    scope, self.store.select("maintenance", scope, w, newest_first=limit), dropped
                ),
            }
            result["n"] = 1 + sum(
                len(result[k]) for k in ("chambers", "recent_alarms", "maintenance")
            )
        self._trace("get_equipment_status", scope, result, dropped[0])
        return result

    def get_dispatch_log(
        self, scope: Scope, equipment_id: str, chamber_id: str | None = None, limit: int = 10
    ) -> dict:
        w = {"equipment_id": _id(equipment_id, "equipment_id")}
        if chamber_id:
            w["chamber_id"] = _id(chamber_id, "chamber_id")
        limit, dropped = _limit(limit), [0]
        rows = self._out(
            scope, self.store.select("dispatch_log", scope, w, newest_first=limit), dropped
        )
        if not rows:
            result = {"found": False, "message": NOT_FOUND, "n": 0}
        else:
            result = {"found": True, "dispatches": rows, "n": len(rows)}
        self._trace("get_dispatch_log", scope, result, dropped[0])
        return result

    # ------------------------------------------------------------------ document search

    def _search(self, tool: str, doc_type: str, scope: Scope, query: str, k: int) -> dict:
        if self.searcher is None:
            raise RuntimeError("document search is not configured")
        query, k, dropped = _query(query), _limit(k), [0]
        hits = self.searcher.search(query, scope, doc_type=doc_type).hits
        docs: dict[str, dict] = {}
        for h in hits:
            attrs = {"fab": h.fab, "department": h.department, "clearance": h.clearance}
            if self.exit_checks and not visible(scope, attrs):
                dropped[0] += 1
                continue
            if h.doc_type and h.doc_type != doc_type:
                continue
            if h.doc_id not in docs and len(docs) >= k:
                break
            docs.setdefault(h.doc_id, {"doc_id": h.doc_id, "excerpts": []})["excerpts"].append(
                h.text
            )
        result = {"found": bool(docs), "documents": list(docs.values())}
        result["n"] = len(result["documents"])
        if not docs:
            result["message"] = NOT_FOUND
        self._trace(
            tool, scope, result, dropped[0], doc_ids=[d["doc_id"] for d in result["documents"]]
        )
        return result

    def search_sop(self, scope: Scope, query: str, k: int = 3) -> dict:
        return self._search("search_sop", "sop", scope, query, k)

    def search_similar_incidents(self, scope: Scope, query: str, k: int = 3) -> dict:
        return self._search("search_similar_incidents", "incident", scope, query, k)
