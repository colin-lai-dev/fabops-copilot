"""Langfuse exporter for masked trace events (ADR-0007; PLAN Phase 2).

What leaves the process is exactly what `authz/trace.py:mask()` returned: ids, clearance levels,
hashes and lengths, tool names, steps, tokens, latency, cost. The exporter never sees the
unmasked fields, and a tracer in the unsafe (leak-baseline) mode never exports.

It posts to Langfuse's public ingestion API (`POST {host}/api/public/ingestion`, basic auth with
the project's public/secret key), one `event-create` per trace event, grouped into a trace by
`trace_id` or the agent's `thread_id`. Off unless `FABOPS_LANGFUSE=1` and both keys are set.
The free cloud plan is acceptable only because all data is synthetic (README, limitations).
"""

from __future__ import annotations

import atexit
import uuid
from typing import Any

import httpx

BATCH = 20


class LangfuseExporter:
    def __init__(
        self,
        host: str,
        public_key: str,
        secret_key: str,
        *,
        client: httpx.Client | None = None,
        batch: int = BATCH,
    ):
        if not (host and public_key and secret_key):
            raise ValueError("Langfuse needs host, public key and secret key")
        self.url = host.rstrip("/") + "/api/public/ingestion"
        self.client = client or httpx.Client(timeout=5.0)
        self.auth = (public_key, secret_key)
        self.batch = batch
        self.buffer: list[dict[str, Any]] = []
        self.sent = 0
        self.failures = 0
        atexit.register(self.flush)

    @staticmethod
    def to_event(record: dict[str, Any]) -> dict[str, Any]:
        """One masked tracer record -> one Langfuse ingestion event (metadata = the record)."""
        trace_id = str(record.get("trace_id") or record.get("thread_id") or uuid.uuid4().hex)
        return {
            "id": uuid.uuid4().hex,
            "timestamp": record.get("ts"),
            "type": "event-create",
            "body": {
                "id": uuid.uuid4().hex,
                "traceId": trace_id,
                "name": str(record.get("event", "event")),
                "startTime": record.get("ts"),
                "metadata": record,
            },
        }

    def export(self, masked_record: dict[str, Any]) -> None:
        self.buffer.append(self.to_event(masked_record))
        if len(self.buffer) >= self.batch:
            self.flush()

    def flush(self) -> None:
        if not self.buffer:
            return
        batch, self.buffer = self.buffer, []
        try:
            r = self.client.post(self.url, json={"batch": batch}, auth=self.auth)
            r.raise_for_status()
            self.sent += len(batch)
        except httpx.HTTPError:
            self.failures += len(batch)  # tracing must never break a request


def exporter_from_settings() -> LangfuseExporter | None:
    from fabops.config import get_settings

    cfg = get_settings()
    public = cfg.langfuse_public_key.get_secret_value() if cfg.langfuse_public_key else ""
    secret = cfg.langfuse_secret_key.get_secret_value() if cfg.langfuse_secret_key else ""
    if not (cfg.fabops_langfuse and public and secret and cfg.langfuse_host):
        return None
    return LangfuseExporter(cfg.langfuse_host, public, secret)
