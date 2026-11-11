"""API: session tokens, identity from the token only, ask, pending list, approver rules."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from fabops.agent.proposals import InMemoryProposalStore
from fabops.agent.service import AgentService
from fabops.api.app import State, build_app
from fabops.authz.policy import scope_of_user
from fabops.authz.token import issue_token
from fabops.authz.trace import Tracer
from fabops.data.world import DEMO_USERS
from fabops.llm.client import LLMClient
from fabops.mcp_server.server import build_server, demo_scope_resolver
from fabops.mcp_server.store import JsonlMesStore
from fabops.mcp_server.tools import MesTools
from tests.test_agent_graph import EQ, SECRET, FakeSearcher, Scripted, _propose, call

USERS = {
    u: {"user_id": u, "display_name": n, "fabs": f, "departments": d, "clearance": c}
    for u, n, f, d, c in DEMO_USERS
}


@pytest.fixture
def client(tmp_path):
    def make(replies):
        st = State()
        st.secret = SECRET
        st.users = USERS
        st.mes = JsonlMesStore()
        tracer = Tracer(tmp_path / "t.jsonl")
        st.mcp_app = build_server(
            MesTools(st.mes, FakeSearcher(), tracer), demo_scope_resolver(), SECRET
        ).http_app()
        st.proposals = InMemoryProposalStore()
        llm = LLMClient(Scripted(replies), "fake", tmp_path / "c", tmp_path / "u.jsonl")
        st.service = AgentService(
            llm, st.proposals, InMemorySaver(), tracer,
            resolve_scope=lambda u: scope_of_user(USERS[u]) if u in USERS else None, mes=st.mes,
        )  # fmt: skip
        return TestClient(build_app(st))

    return make


def login(c, user):
    r = c.post("/api/session", json={"user_id": user})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_requests_need_a_valid_token(client):
    c = client([])
    assert c.get("/api/me").status_code == 401
    forged = issue_token("admin_all", "attacker-" + SECRET)
    assert c.get("/api/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    assert c.post("/api/session", json={"user_id": "root"}).status_code == 404
    assert c.get("/api/me", headers=login(c, "eng_fx1_etch")).json()["user_id"] == "eng_fx1_etch"


def test_ask_body_cannot_carry_identity(client):
    c = client(
        [call("get_equipment_status", equipment_id=EQ), {"action": "finish", "answer": "ok"}]
    )
    r = c.post(
        "/api/ask",
        json={"question": "狀態？", "mode": "agent", "user_id": "admin_all"},
        headers=login(c, "eng_fx2_litho"),
    )
    assert r.status_code == 200
    body = r.json()
    assert json.loads(body["calls"][0]["preview"])["found"] is False  # FX2 user, FX1 equipment


def test_full_approval_flow_with_rules(client):
    c = client([call("get_equipment_status", equipment_id=EQ), _propose(f"{EQ}-CHA")])
    run = c.post(
        "/api/ask", json={"question": f"{EQ} 壓力異常，請依 SOP 處理"},
        headers=login(c, "eng_fx1_etch"),
    ).json()  # fmt: skip
    assert run["status"] == "awaiting_approval"
    pid = run["proposal"]["proposal_id"]

    own = c.get("/api/proposals", headers=login(c, "eng_fx1_etch")).json()
    assert own[0]["can_decide"] is False and "requester" in own[0]["why_not"]
    assert c.get("/api/proposals", headers=login(c, "mgr_fx2_all")).json() == []  # cannot see

    denied = c.post(f"/api/proposals/{pid}/decision", json={"approved": True},
                    headers=login(c, "eng_fx1_etch"))  # fmt: skip
    assert denied.status_code == 403

    lead = login(c, "lead_fx1_multi")
    ok = c.post(f"/api/proposals/{pid}/decision", json={"approved": True}, headers=lead)
    assert ok.status_code == 200 and ok.json()["status"] == "executed"
    events = [a["event"] for a in c.get(f"/api/audit/{pid}", headers=lead).json()]
    assert events == ["proposed", "denied", "approved", "executed"]
    assert c.get(f"/api/audit/{pid}", headers=login(c, "mgr_fx2_all")).status_code == 404
