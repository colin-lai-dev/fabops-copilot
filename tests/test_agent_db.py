"""Postgres proposal store and checkpoints (ADR-0006): same contract as the in-memory store,
and a run paused for approval can be resumed by a new service instance."""

from __future__ import annotations

import asyncio
import json
import sys
import uuid

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from fabops.agent.proposals import PgProposalStore
from fabops.config import get_settings

pytestmark = pytest.mark.db


def _test_db_url() -> str:
    """A separate `<db>_test` database, so test proposals never enter the dev audit log."""
    url = get_settings().database_url
    name = conninfo_to_dict(url)["dbname"] + "_test"
    with psycopg.connect(url, autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", [name]).fetchone():
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    return make_conninfo(url, dbname=name)


URL: str = ""  # set by the module fixture (needs Postgres, so not at import time)


def run(coro):
    if sys.platform == "win32":  # psycopg async needs a selector loop on Windows
        return asyncio.run(coro, loop_factory=asyncio.SelectorEventLoop)
    return asyncio.run(coro)


@pytest.fixture(scope="module", autouse=True)
def _url():
    global URL
    URL = _test_db_url()
    yield


@pytest.fixture
def store():
    return PgProposalStore(lambda: psycopg.connect(URL))


def test_pg_store_idempotency_and_single_execution(store):
    thread = uuid.uuid4().hex
    p, created = store.create(thread, "eng_fx1_etch", "hold_lot", "FX1L00003", "測試")
    again, created_again = store.create(thread, "eng_fx1_etch", "hold_lot", "FX1L00003", "再一次")
    assert created and not created_again and again.proposal_id == p.proposal_id
    assert store.execute_once(p.proposal_id) == (p, False)  # not approved yet
    d = store.decide(p.proposal_id, True, "lead_fx1_multi")
    assert d.status == "approved"
    assert store.decide(p.proposal_id, False, "someone").status == "approved"  # first decision wins
    e, now = store.execute_once(p.proposal_id)
    e2, now2 = store.execute_once(p.proposal_id)
    assert (e.status, now, now2) == ("executed", True, False)
    assert [a.event for a in store.audit(p.proposal_id)] == ["proposed", "approved", "executed"]


def test_unknown_action_is_rejected_by_code_and_schema(store):
    with pytest.raises(ValueError):
        store.create("t", "u", "drop_table", "x", "r")
    with psycopg.connect(URL) as conn, pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "INSERT INTO agent_proposals (proposal_id, idempotency_key, thread_id, requester, "
            "action, target_id, reason) VALUES ('x', %s, 't', 'u', 'drop_table', 'x', 'r')",
            (uuid.uuid4().hex,),
        )


def test_resume_from_postgres_checkpoint_in_a_new_service(store, tmp_path):
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    from fabops.agent.service import AgentService, postgres_checkpointer
    from fabops.authz.trace import Tracer
    from fabops.llm.client import Completion, LLMClient
    from tests.test_agent_graph import EQ, SCOPES, SECRET, FakeSearcher, call

    class Scripted:
        name = "fake"

        def __init__(self, replies):
            self.replies = list(replies)

        def complete(self, messages, model, temperature, max_tokens):
            return Completion(json.dumps(self.replies.pop(0), ensure_ascii=False), 10, 5)

    from fabops.agent.gateway import McpGateway
    from fabops.authz.token import issue_token
    from fabops.mcp_server.server import build_server, demo_scope_resolver
    from fabops.mcp_server.store import JsonlMesStore
    from fabops.mcp_server.tools import MesTools

    tracer = Tracer(tmp_path / "t.jsonl")
    app = build_server(
        MesTools(JsonlMesStore(), FakeSearcher(), tracer), demo_scope_resolver(), SECRET
    ).http_app()
    replies = [
        call("get_equipment_status", equipment_id=EQ),
        {
            "action": "propose",
            "proposal": {"action": "inhibit_chamber", "target_id": f"{EQ}-CHA", "reason": "r"},
            "answer": "建議暫停派貨",
        },
    ]
    llm = LLMClient(Scripted(replies), "fake-pg", tmp_path / "c", tmp_path / "u.jsonl")

    async def first() -> str:
        async with postgres_checkpointer(URL) as saver:
            svc = AgentService(llm, store, saver, tracer)
            async with McpGateway.in_process(app, issue_token("eng_fx1_etch", SECRET)) as gw:
                r = await svc.ask(
                    f"{EQ} 壓力異常", user_id="eng_fx1_etch", scope=SCOPES["eng_fx1_etch"],
                    gateway=gw,
                )  # fmt: skip
            assert r.status == "awaiting_approval"
            return r.thread_id

    async def second(thread_id: str):
        async with AsyncPostgresSaver.from_conn_string(URL) as saver:  # a fresh connection
            svc = AgentService(llm, store, saver, tracer)
            return await svc.decide(thread_id, approved=True, approver="lead_fx1_multi")

    thread_id = run(first())
    done = run(second(thread_id))
    assert done.status == "executed"
    assert [a.event for a in store.audit(done.proposal["proposal_id"])] == [
        "proposed",
        "approved",
        "executed",
    ]
