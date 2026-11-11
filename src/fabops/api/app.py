"""FastAPI backend for the demo UI (PLAN Phase 2): ask, role switch, agent trace, approvals.

Identity (ADR-0001): there is no password login. `POST /api/session` picks a demo user and
returns a short-lived signed token; every other call sends it as `Authorization: Bearer …`.
The server verifies it, resolves the scope from the users table, and for agent runs signs a
separate token for the MCP boundary. The user id never comes from the request body, the LLM
or a tool argument.

Approvals (ADR-0006 revision): the approver is the session user; `AgentService.decide()`
enforces the rules (not the requester, clearance >= confidential, can see the target) and
audits refused attempts.

Run: `python -m fabops.api.app` (Postgres, Ollama or a paid model per `.env`). With `web/dist`
built, the UI is served at `/`.
"""

from __future__ import annotations

import asyncio
import contextlib
import secrets
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from fabops.agent.gateway import McpGateway
from fabops.agent.proposals import ApprovalDenied, ProposalStore, approval_problem, target_visible
from fabops.agent.service import AgentService, postgres_checkpointer
from fabops.authz.policy import scope_of_user
from fabops.authz.scope import Scope
from fabops.authz.token import issue_token, verify_token
from fabops.authz.trace import Tracer
from fabops.config import get_settings

WEB_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"
PREVIEW_CHARS = 600  # tool results shown in the UI trace


class SessionIn(BaseModel):
    user_id: str


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    mode: Literal["agent", "fixed", "rag"] = "agent"


class DecisionIn(BaseModel):
    approved: bool
    note: str = Field(default="", max_length=300)


class State:
    """Process-wide components, built in the lifespan."""

    secret: str
    connect: Any
    users: dict[str, dict[str, Any]]
    service: AgentService
    proposals: ProposalStore
    mcp_app: Any
    answerer: Any
    mes: Any


def build_app(prebuilt: State | None = None) -> FastAPI:
    """`prebuilt` (tests) skips the real wiring: Postgres, models, LLM, checkpointer."""
    st = prebuilt or State()

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        if prebuilt is not None:
            yield
            return
        import psycopg

        from fabops.llm.client import LLMClient
        from fabops.mcp_server.server import build_server, pg_scope_resolver
        from fabops.mcp_server.store import PgMesStore
        from fabops.mcp_server.tools import MesTools
        from fabops.rag.answer import Answerer
        from fabops.rag.models import default_encoder
        from fabops.rag.retrieve import Retriever

        cfg = get_settings()
        if cfg.fabops_jwt_secret is not None:
            st.secret = cfg.fabops_jwt_secret.get_secret_value()
        else:  # demo fallback: tokens die with the process
            st.secret = secrets.token_urlsafe(48)
            print("FABOPS_JWT_SECRET not set: using an ephemeral secret", file=sys.stderr)

        def connect():
            return psycopg.connect(cfg.database_url)

        st.connect = connect
        with connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT user_id, display_name, fabs, departments, clearance FROM users")
            cols = ("user_id", "display_name", "fabs", "departments", "clearance")
            st.users = {r[0]: dict(zip(cols, r, strict=True)) for r in cur}
        tracer = Tracer.from_env()
        retriever = Retriever(connect, default_encoder())
        st.mes = PgMesStore(connect)
        st.mcp_app = build_server(
            MesTools(st.mes, retriever, tracer), pg_scope_resolver(connect), st.secret
        ).http_app()
        from fabops.agent.proposals import PgProposalStore

        st.proposals = PgProposalStore(connect)
        llm = LLMClient.from_env()
        st.answerer = Answerer(retriever, llm, tracer)
        async with postgres_checkpointer(cfg.database_url) as saver:
            st.service = AgentService(
                llm, st.proposals, saver, tracer, resolve_scope=scope_of, mes=st.mes
            )
            yield

    def scope_of(user_id: str) -> Scope | None:
        u = st.users.get(user_id)
        return scope_of_user(u) if u else None

    def current_user(authorization: str = Header(default="")) -> str:
        token = authorization.removeprefix("Bearer ").strip()
        try:
            user_id = verify_token(token, st.secret)
        except (jwt.InvalidTokenError, ValueError) as e:
            raise HTTPException(401, "invalid or expired session") from e
        if user_id not in st.users:
            raise HTTPException(401, "unknown user")
        return user_id

    app = FastAPI(title="FabOps Copilot (synthetic data)", lifespan=lifespan)

    @app.get("/api/users")
    def users() -> list[dict[str, Any]]:
        return list(st.users.values())

    @app.post("/api/session")
    def session(body: SessionIn) -> dict[str, Any]:
        """Demo login: pick a demo user, get a short-lived token (switching re-issues it)."""
        if body.user_id not in st.users:
            raise HTTPException(404, "unknown demo user")
        return {"token": issue_token(body.user_id, st.secret), "user": st.users[body.user_id]}

    @app.get("/api/me")
    def me(user_id: str = Depends(current_user)) -> dict[str, Any]:
        return st.users[user_id]

    @app.post("/api/ask")
    async def ask(body: AskIn, user_id: str = Depends(current_user)) -> dict[str, Any]:
        scope = scope_of(user_id)
        assert scope is not None
        if body.mode == "rag":
            a = await asyncio.to_thread(st.answerer.answer, body.question, scope)
            return {
                "mode": "rag", "status": "done", "answer": a.text, "citations": a.citations,
                "refused": a.refused, "steps": 0, "calls": [], "proposal": None,
                "usage": {"input_tokens": a.input_tokens, "output_tokens": a.output_tokens,
                          "cost_usd": a.cost_usd, "llm_calls": 1},
            }  # fmt: skip
        mcp_token = issue_token(user_id, st.secret)  # separate token for the MCP boundary
        async with McpGateway.in_process(st.mcp_app, mcp_token) as gw:
            run = await st.service.ask(
                body.question, user_id=user_id, scope=scope, gateway=gw, mode=body.mode
            )
        out = asdict(run)
        out.pop("tool_results", None)
        for c in out["calls"]:
            full = c.pop("full", None)
            if full is not None:
                c["preview"] = full[:PREVIEW_CHARS] + ("…" if len(full) > PREVIEW_CHARS else "")
        return out

    @app.get("/api/proposals")
    def pending(user_id: str = Depends(current_user)) -> list[dict[str, Any]]:
        """Pending proposals whose target this user can see, with whether they may decide."""
        scope = scope_of(user_id)
        out = []
        for p in st.proposals.pending():
            if scope is None or not target_visible(st.mes, scope, p.action, p.target_id):
                continue  # not even listed
            problem = approval_problem(p, user_id, scope, st.mes)
            out.append({**asdict(p), "can_decide": problem is None, "why_not": problem})
        return out

    @app.post("/api/proposals/{proposal_id}/decision")
    async def decide(
        proposal_id: str, body: DecisionIn, user_id: str = Depends(current_user)
    ) -> dict[str, Any]:
        p = st.proposals.get(proposal_id)
        if p is None or p.status != "pending":
            raise HTTPException(404, "no pending proposal with this id")
        try:
            run = await st.service.decide(
                p.thread_id, approved=body.approved, approver=user_id, note=body.note
            )
        except ApprovalDenied as e:
            raise HTTPException(403, str(e)) from e
        except ValueError as e:
            raise HTTPException(409, str(e)) from e
        out = asdict(run)
        out.pop("tool_results", None)
        for c in out["calls"]:
            c.pop("full", None)
        return out

    @app.get("/api/audit/{proposal_id}")
    def audit(proposal_id: str, user_id: str = Depends(current_user)) -> list[dict[str, Any]]:
        p = st.proposals.get(proposal_id)
        scope = scope_of(user_id)
        if (
            p is None
            or scope is None
            or not (p.requester == user_id or target_visible(st.mes, scope, p.action, p.target_id))
        ):
            raise HTTPException(404, "not found")
        return [asdict(a) for a in st.proposals.audit(proposal_id)]

    if WEB_DIST.exists():
        app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
    return app


def main() -> None:  # pragma: no cover - wiring only
    import argparse

    import uvicorn

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    server = uvicorn.Server(
        uvicorn.Config(build_app(), host=args.host, port=args.port, loop="none")
    )
    if sys.platform == "win32":  # psycopg async (checkpoints) needs a selector loop on Windows
        asyncio.run(server.serve(), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(server.serve())


if __name__ == "__main__":
    main()
