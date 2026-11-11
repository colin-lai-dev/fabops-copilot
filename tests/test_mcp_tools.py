"""Agent tools: permission filtering, exit checks, and identity at the MCP boundary (ADR-0001)."""

from __future__ import annotations

import asyncio
import json
import time

import jwt
import pytest

from fabops.agent.gateway import McpGateway
from fabops.authz.policy import scope_of_user
from fabops.authz.token import ALGORITHM, AUDIENCE, ISSUER, issue_token, verify_token
from fabops.authz.trace import Tracer
from fabops.data.world import DEMO_USERS
from fabops.mcp_server.server import build_server, demo_scope_resolver
from fabops.mcp_server.store import JsonlMesStore
from fabops.mcp_server.tools import NOT_FOUND, TOOL_NAMES, MesTools
from fabops.rag.retrieve import Hit, Retrieval

SECRET = "test-secret-" + "x" * 32
SCOPES = {
    u: scope_of_user({"fabs": f, "departments": d, "clearance": c}) for u, _, f, d, c in DEMO_USERS
}
STORE = JsonlMesStore()


class FakeSearcher:
    """Returns fixed hits regardless of scope: the tool's own exit check must filter them."""

    def __init__(self, hits):
        self.hits = hits

    def search(self, query, scope, doc_type=None):
        return Retrieval([h for h in self.hits if h.doc_type == doc_type], {})


HITS = [
    Hit("c1", "SOP-FX1-ETC-PRS-0412-v2", "FX1 蝕刻 SOP", "FX1", "etch", 1, 1.0, {}, "sop"),
    Hit("c2", "SOP-FX2-LIT-OVL-0322-v1", "FX2 黃光 SOP", "FX2", "litho", 1, 0.9, {}, "sop"),
    Hit("c3", "INC-2026-0001", "受限異常報告", "FX1", "etch", 3, 0.8, {}, "incident"),
]


@pytest.fixture
def tools(tmp_path):
    return MesTools(STORE, FakeSearcher(HITS), Tracer(tmp_path / "traces.jsonl"))


def first(view, **where):
    return (
        STORE.views[view][0]
        if not where
        else next(r for r in STORE.views[view] if all(r[k] == v for k, v in where.items()))
    )


# ---------------------------------------------------------------- tools (no MCP)


def test_equipment_visible_in_own_fab_and_department(tools):
    eq = first("equipment", fab="FX1", department="etch")
    r = tools.get_equipment_status(SCOPES["eng_fx1_etch"], eq["equipment_id"])
    assert r["found"] and r["equipment"]["equipment_id"] == eq["equipment_id"]
    assert r["chambers"] and all(c["equipment_id"] == eq["equipment_id"] for c in r["chambers"])
    assert "clearance" not in r["equipment"] and "department" not in r["equipment"]


@pytest.mark.parametrize(
    ("user", "fab", "dept"),
    [
        ("eng_fx2_litho", "FX1", "etch"),  # cross-fab
        ("eng_fx1_etch", "FX1", "litho"),  # cross-department
    ],
)
def test_invisible_equipment_looks_like_missing(tools, user, fab, dept):
    eq = first("equipment", fab=fab, department=dept)
    hidden = tools.get_equipment_status(SCOPES[user], eq["equipment_id"])
    missing = tools.get_equipment_status(SCOPES[user], "FX9-NOPE-01")
    assert hidden == missing == {"found": False, "message": NOT_FOUND, "n": 0}


def test_equipment_status_accepts_a_chamber_id(tools):
    eq = first("equipment", fab="FX1", department="etch")["equipment_id"]
    r = tools.get_equipment_status(SCOPES["eng_fx1_etch"], f"{eq}-CHA")
    assert r["found"] and r["equipment"]["equipment_id"] == eq


def test_operators_see_their_own_mes_rows(tools):
    """MES rows are public (MES_CLEARANCE = 0, handoff 008); documents keep their levels."""
    eq = first("equipment", fab="FX1", department="etch")["equipment_id"]
    assert tools.get_equipment_status(SCOPES["op_fx1_etch"], eq)["found"] is True
    other = first("equipment", fab="FX1", department="litho")["equipment_id"]
    assert tools.get_equipment_status(SCOPES["op_fx1_etch"], other)["found"] is False


def test_lot_history_only_shows_visible_departments(tools):
    scope = SCOPES["lead_fx1_multi"]  # FX1; etch, thinfilm, cmp
    eq_dept = {e["equipment_id"]: e["department"] for e in STORE.views["equipment"]}
    lot = next(
        lot["lot_id"]
        for lot in STORE.views["lots"]
        if lot["fab"] == "FX1"
        and {
            eq_dept[d["equipment_id"]]
            for d in STORE.views["dispatch_log"]
            if d["lot_id"] == lot["lot_id"]
        }
        - set(scope.departments)
    )
    r = tools.get_lot_history(scope, lot, limit=20)
    assert r["found"]
    assert {eq_dept[d["equipment_id"]] for d in r["dispatches"]} <= set(scope.departments)
    full = tools.get_lot_history(SCOPES["admin_all"], lot, limit=20)
    assert len(full["dispatches"]) >= len(r["dispatches"])


def test_dispatch_log_newest_first_and_limited(tools):
    eq = first("equipment", fab="FX2", department="litho")["equipment_id"]
    r = tools.get_dispatch_log(SCOPES["eng_fx2_litho"], eq, limit=5)
    times = [d["dispatched_at"] for d in r["dispatches"]]
    assert len(times) == 5 and times == sorted(times, reverse=True)


def test_search_tools_drop_hits_the_caller_cannot_see(tools, tmp_path):
    r = tools.search_sop(SCOPES["eng_fx1_etch"], "壓力異常")
    assert [d["doc_id"] for d in r["documents"]] == ["SOP-FX1-ETC-PRS-0412-v2"]
    inc = tools.search_similar_incidents(SCOPES["eng_fx1_etch"], "壓力異常")
    assert inc["found"] is False  # the only incident hit is restricted
    events = [json.loads(x) for x in (tmp_path / "traces.jsonl").read_text("utf-8").splitlines()]
    assert [e["dropped_rows"] for e in events] == [1, 1]


def test_exit_check_catches_a_store_that_leaks(tmp_path):
    class LeakyStore(JsonlMesStore):
        def _visible(self, scope, row):
            return True  # simulates a broken pre-filter

    t = MesTools(LeakyStore(), None, Tracer(tmp_path / "t.jsonl"))
    eq = first("equipment", fab="FX1", department="etch")["equipment_id"]
    assert t.get_equipment_status(SCOPES["eng_fx2_litho"], eq)["found"] is False
    unsafe = MesTools(LeakyStore(), None, Tracer(tmp_path / "u.jsonl"), exit_checks=False)
    assert unsafe.get_equipment_status(SCOPES["eng_fx2_litho"], eq)["found"] is True


def test_trace_has_no_content(tools, tmp_path):
    eq = first("equipment", fab="FX1", department="etch")["equipment_id"]
    tools.get_equipment_status(SCOPES["eng_fx1_etch"], eq)
    tools.search_sop(SCOPES["eng_fx1_etch"], "腔體壓力異常怎麼處理")
    raw = (tmp_path / "traces.jsonl").read_text("utf-8")
    assert "FX1 蝕刻 SOP" not in raw and "腔體壓力" not in raw and eq not in raw
    assert "dropped_fields" not in raw


def test_invalid_ids_are_rejected(tools):
    from fabops.mcp_server.tools import ToolInputError

    with pytest.raises(ToolInputError):
        tools.get_lot_history(SCOPES["admin_all"], "FX1L00001'; DROP TABLE lots;--")
    with pytest.raises(ToolInputError):
        tools.get_dispatch_log(SCOPES["admin_all"], "FX1-ETCHER-01", limit=500)


# ---------------------------------------------------------------- tokens


def test_token_round_trip_and_rejections():
    assert verify_token(issue_token("eng_fx1_etch", SECRET), SECRET) == "eng_fx1_etch"
    with pytest.raises(jwt.InvalidTokenError):
        verify_token(issue_token("eng_fx1_etch", SECRET), "other-" + SECRET)
    expired = jwt.encode(
        {"sub": "admin_all", "iss": ISSUER, "aud": AUDIENCE, "exp": int(time.time()) - 5},
        SECRET,
        algorithm=ALGORITHM,
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        verify_token(expired, SECRET)
    with pytest.raises(ValueError):
        issue_token("admin_all", "short")


# ---------------------------------------------------------------- MCP boundary


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def app(tools):
    return build_server(tools, demo_scope_resolver(), SECRET).http_app()


IDENTITY_WORDS = {"user", "user_id", "role", "scope", "token", "clearance", "identity", "as_user"}


def test_tool_signatures_have_no_identity(app):
    async def go():
        async with McpGateway.in_process(app, issue_token("admin_all", SECRET)) as gw:
            return await gw.list_tools()

    listed = run(go())
    assert sorted(t["name"] for t in listed) == sorted(TOOL_NAMES)
    for t in listed:
        assert not set(t["parameters"].get("properties", {})) & IDENTITY_WORDS, t["name"]


def test_identity_comes_from_the_token(app):
    eq = first("equipment", fab="FX1", department="etch")["equipment_id"]

    async def as_user(user):
        async with McpGateway.in_process(app, issue_token(user, SECRET)) as gw:
            return await gw.call("get_equipment_status", {"equipment_id": eq})

    assert run(as_user("eng_fx1_etch")).data["found"] is True
    assert run(as_user("eng_fx2_litho")).data["found"] is False
    unknown = run(as_user("nobody"))
    assert not unknown.ok and "未授權" in unknown.error


def test_identity_argument_cannot_escalate(app):
    """An injected `user_id`/`role` argument is rejected, never honoured."""
    eq = first("equipment", fab="FX1", department="etch")["equipment_id"]

    async def go():
        async with McpGateway.in_process(app, issue_token("eng_fx2_litho", SECRET)) as gw:
            return await gw.call(
                "get_equipment_status", {"equipment_id": eq, "user_id": "admin_all"}
            )

    r = run(go())
    assert not (r.ok and r.data.get("found"))


@pytest.mark.parametrize("token", ["", "not-a-jwt", "forged"])
def test_bad_tokens_are_refused_before_any_tool(app, token):
    if token == "forged":
        token = issue_token("admin_all", "attacker-" + SECRET)

    async def go():
        async with McpGateway.in_process(app, token) as gw:
            return await gw.list_tools()

    with pytest.raises(Exception):  # noqa: B017 - 401 surfaces as a client error
        run(go())
