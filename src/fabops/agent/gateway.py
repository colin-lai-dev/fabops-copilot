"""The agent's side of the MCP boundary: call tools with the user's bearer token.

The token is held here, in memory, and sent as an HTTP header (ADR-0001). It is not part of
the graph state, the checkpoint, the prompt or the trace.

`McpGateway.connect(url, token)` talks to a running server; `McpGateway.in_process(app, token)`
serves the same FastMCP ASGI app inside this process. Both go through HTTP and the JWT
verifier, so tests and evals exercise the real identity boundary.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol

import httpx2
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport


@dataclass
class ToolResult:
    ok: bool
    data: Any = None
    error: str | None = None


class ToolGateway(Protocol):
    async def list_tools(self) -> list[dict[str, Any]]: ...

    async def call(self, name: str, args: dict[str, Any]) -> ToolResult: ...


class McpGateway:
    def __init__(self, client: Client):
        self._client = client

    @classmethod
    @contextlib.asynccontextmanager
    async def connect(cls, url: str, token: str) -> AsyncIterator[McpGateway]:
        async with Client(StreamableHttpTransport(url, auth=token)) as c:
            yield cls(c)

    @classmethod
    @contextlib.asynccontextmanager
    async def in_process(cls, app: Any, token: str) -> AsyncIterator[McpGateway]:
        """`app` is `FastMCP.http_app()`; its lifespan runs for the duration of the block."""

        def factory(**kwargs: Any) -> httpx2.AsyncClient:
            kwargs.pop("timeout", None)
            return httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=app),
                base_url="http://mcp.local",
                timeout=httpx2.Timeout(60.0),
                **kwargs,
            )

        transport = StreamableHttpTransport(
            "http://mcp.local/mcp", auth=token, httpx_client_factory=factory
        )
        async with app.router.lifespan_context(app), Client(transport) as c:
            yield cls(c)

    async def list_tools(self) -> list[dict[str, Any]]:
        return [
            {"name": t.name, "description": t.description or "", "parameters": t.input_schema}
            for t in await self._client.list_tools()
        ]

    async def call(self, name: str, args: dict[str, Any]) -> ToolResult:
        try:
            r = await self._client.call_tool(name, args, raise_on_error=False)
        except Exception as e:  # transport failure, unknown tool, schema error
            return ToolResult(False, error=f"{type(e).__name__}: {str(e)[:200]}")
        if r.is_error:
            text = " ".join(getattr(c, "text", "") for c in r.content).strip()
            return ToolResult(False, error=text[:300] or "tool error")
        if r.data is not None:
            return ToolResult(True, r.data)
        if r.structured_content is not None:
            return ToolResult(True, r.structured_content)
        text = " ".join(getattr(c, "text", "") for c in r.content)
        try:
            return ToolResult(True, json.loads(text))
        except ValueError:
            return ToolResult(True, text)
