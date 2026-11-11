"""Write proposals, human approval and the audit log (ADR-0006, CLAUDE.md 安全與權限).

The agent never writes. It can only *propose* one of `ACTIONS`; a human approves or rejects;
only an approved proposal is executed, exactly once, and every transition is audited.

Idempotency: a proposal's key is `sha256(thread_id, action, target_id)`. Proposing the same
thing again in a run returns the existing record, and `execute_once` is a compare-and-set
from `approved` to `executed`, so a replayed node (LangGraph re-runs a node after a resume
or a crash) cannot execute twice.

Execution is **simulated**: it records the action in the audit log and does not change MES
tables, so evals stay reproducible (docs/open-questions.md, 2026-11-11).
"""

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

import psycopg

from fabops.authz.scope import Scope
from fabops.mcp_server.store import MesStore

# action -> (what the target id names, Chinese label)
ACTIONS: dict[str, tuple[str, str]] = {
    "hold_lot": ("lot_id", "hold 批號"),
    "inhibit_chamber": ("chamber_id", "暫停腔體派貨"),
    "request_pm": ("chamber_id", "開立保養工單"),
}
Status = Literal["pending", "approved", "rejected", "executed"]
SCHEMA = Path(__file__).with_name("schema.sql")


@dataclass(frozen=True)
class Proposal:
    proposal_id: str
    idempotency_key: str
    thread_id: str
    requester: str
    action: str
    target_id: str
    reason: str
    status: Status = "pending"
    approver: str | None = None
    note: str = ""


@dataclass(frozen=True)
class AuditEntry:
    proposal_id: str
    event: str  # proposed | approved | rejected | executed | denied
    actor: str
    detail: dict[str, Any] = field(default_factory=dict)
    ts: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


def idempotency_key(thread_id: str, action: str, target_id: str) -> str:
    raw = json.dumps([thread_id, action, target_id], ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


class ProposalStore(Protocol):
    def create(
        self, thread_id: str, requester: str, action: str, target_id: str, reason: str
    ) -> tuple[Proposal, bool]:
        """Return (proposal, created). An existing proposal with the same key is returned as is."""
        ...

    def get(self, proposal_id: str) -> Proposal | None: ...

    def decide(self, proposal_id: str, approved: bool, approver: str, note: str = "") -> Proposal:
        """pending -> approved/rejected. Deciding twice returns the first decision unchanged."""
        ...

    def execute_once(self, proposal_id: str) -> tuple[Proposal, bool]:
        """approved -> executed. Returns (proposal, executed_now)."""
        ...

    def deny(self, proposal_id: str, actor: str, reason: str) -> None:
        """Audit a refused decision attempt; the proposal stays as it is."""
        ...

    def audit(self, proposal_id: str | None = None) -> list[AuditEntry]: ...


def _check_action(action: str) -> None:
    if action not in ACTIONS:
        raise ValueError(f"unknown action {action!r}")


class InMemoryProposalStore:
    """Same contract as `PgProposalStore`, for unit tests and runs without Postgres."""

    def __init__(self) -> None:
        self._by_id: dict[str, Proposal] = {}
        self._by_key: dict[str, str] = {}
        self._audit: list[AuditEntry] = []
        self._lock = threading.Lock()

    def create(self, thread_id, requester, action, target_id, reason):
        _check_action(action)
        key = idempotency_key(thread_id, action, target_id)
        with self._lock:
            if key in self._by_key:
                return self._by_id[self._by_key[key]], False
            p = Proposal(
                uuid.uuid4().hex[:12], key, thread_id, requester, action, target_id, reason
            )
            self._by_id[p.proposal_id], self._by_key[key] = p, p.proposal_id
            self._audit.append(AuditEntry(p.proposal_id, "proposed", requester, {"action": action}))
            return p, True

    def get(self, proposal_id):
        return self._by_id.get(proposal_id)

    def decide(self, proposal_id, approved, approver, note=""):
        with self._lock:
            p = self._by_id[proposal_id]
            if p.status != "pending":
                return p
            p = replace(
                p, status="approved" if approved else "rejected", approver=approver, note=note
            )
            self._by_id[proposal_id] = p
            self._audit.append(AuditEntry(proposal_id, p.status, approver, {"note": note}))
            return p

    def execute_once(self, proposal_id):
        with self._lock:
            p = self._by_id[proposal_id]
            if p.status != "approved":
                return p, False
            p = replace(p, status="executed")
            self._by_id[proposal_id] = p
            self._audit.append(AuditEntry(proposal_id, "executed", "system", {"simulated": True}))
            return p, True

    def deny(self, proposal_id, actor, reason):
        with self._lock:
            self._audit.append(AuditEntry(proposal_id, "denied", actor, {"reason": reason}))

    def audit(self, proposal_id=None):
        return [a for a in self._audit if proposal_id in (None, a.proposal_id)]


class PgProposalStore:
    def __init__(self, connect: Callable[[], psycopg.Connection]):
        self.connect = connect
        with self.connect() as conn:
            conn.execute(SCHEMA.read_text(encoding="utf-8"))

    _COLS = (
        "proposal_id, idempotency_key, thread_id, requester, action, target_id, reason, "
        "status, approver, note"
    )

    @staticmethod
    def _row(r) -> Proposal:
        return Proposal(*r)

    def _audit_row(self, cur, proposal_id: str, event: str, actor: str, detail: dict) -> None:
        cur.execute(
            "INSERT INTO agent_audit_log (proposal_id, event, actor, detail) "
            "VALUES (%s, %s, %s, %s)",
            (proposal_id, event, actor, json.dumps(detail, ensure_ascii=False)),
        )

    def create(self, thread_id, requester, action, target_id, reason):
        _check_action(action)
        key = idempotency_key(thread_id, action, target_id)
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO agent_proposals (proposal_id, idempotency_key, thread_id, requester, "
                "action, target_id, reason) VALUES (%s, %s, %s, %s, %s, %s, %s) "
                f"ON CONFLICT (idempotency_key) DO NOTHING RETURNING {self._COLS}",
                (uuid.uuid4().hex[:12], key, thread_id, requester, action, target_id, reason),
            )
            row = cur.fetchone()
            if row is not None:
                p = self._row(row)
                self._audit_row(cur, p.proposal_id, "proposed", requester, {"action": action})
                return p, True
            cur.execute(
                f"SELECT {self._COLS} FROM agent_proposals WHERE idempotency_key = %s", (key,)
            )
            return self._row(cur.fetchone()), False

    def get(self, proposal_id):
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT {self._COLS} FROM agent_proposals WHERE proposal_id = %s", (proposal_id,)
            )
            row = cur.fetchone()
        return self._row(row) if row else None

    def decide(self, proposal_id, approved, approver, note=""):
        status = "approved" if approved else "rejected"
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE agent_proposals SET status = %s, approver = %s, note = %s, "
                "decided_at = now() WHERE proposal_id = %s AND status = 'pending' "
                f"RETURNING {self._COLS}",
                (status, approver, note, proposal_id),
            )
            row = cur.fetchone()
            if row is not None:
                self._audit_row(cur, proposal_id, status, approver, {"note": note})
                return self._row(row)
        p = self.get(proposal_id)
        if p is None:
            raise KeyError(proposal_id)
        return p

    def execute_once(self, proposal_id):
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE agent_proposals SET status = 'executed', executed_at = now() "
                f"WHERE proposal_id = %s AND status = 'approved' RETURNING {self._COLS}",
                (proposal_id,),
            )
            row = cur.fetchone()
            if row is not None:
                self._audit_row(cur, proposal_id, "executed", "system", {"simulated": True})
                return self._row(row), True
        p = self.get(proposal_id)
        if p is None:
            raise KeyError(proposal_id)
        return p, False

    def deny(self, proposal_id, actor, reason):
        with self.connect() as conn, conn.cursor() as cur:
            self._audit_row(cur, proposal_id, "denied", actor, {"reason": reason})

    def audit(self, proposal_id=None):
        sql = "SELECT proposal_id, event, actor, detail, ts FROM agent_audit_log"
        params: tuple = ()
        if proposal_id is not None:
            sql += " WHERE proposal_id = %s"
            params = (proposal_id,)
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(sql + " ORDER BY audit_id", params)
            return [AuditEntry(p, e, a, d, ts.isoformat()) for p, e, a, d, ts in cur]


def as_dict(p: Proposal) -> dict[str, Any]:
    return asdict(p)


# ---------------------------------------------------------------- who may decide

APPROVER_MIN_CLEARANCE = 2  # confidential (planner decision 2026-11-11, ADR-0006 revision)


class ApprovalDenied(PermissionError):
    """A decision attempt that breaks the approver rules; it is audited and not applied."""


def target_visible(mes: MesStore | None, scope: Scope, action: str, target_id: str) -> bool:
    """Can `scope` see the proposal's target (a lot or a chamber) in MES?"""
    if mes is None:
        return False  # cannot verify -> not allowed
    kind = ACTIONS[action][0]
    view = "lots" if kind == "lot_id" else "chambers"
    return bool(mes.select(view, scope, {kind: target_id}))


def approval_problem(
    proposal: Proposal | dict[str, Any],
    approver: str,
    approver_scope: Scope | None,
    mes: MesStore | None,
) -> str | None:
    """None if `approver` may approve or reject `proposal`, else the reason (ADR-0006 revision).

    Rules: not the requester; clearance >= confidential; the target is visible to the approver.
    """
    p = proposal if isinstance(proposal, dict) else asdict(proposal)
    if not approver or approver_scope is None:
        return "unknown approver"
    if approver == p["requester"]:
        return "the requester cannot decide their own proposal"
    if approver_scope.clearance < APPROVER_MIN_CLEARANCE:
        return "approver clearance below confidential"
    if not target_visible(mes, approver_scope, p["action"], p["target_id"]):
        return "approver cannot see the target"
    return None
