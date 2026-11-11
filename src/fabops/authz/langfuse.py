"""Langfuse exporter for masked trace events (ADR-0007; PLAN Phase 2).

What leaves the process is exactly what `authz/trace.py:mask()` returned: ids, clearance levels,
hashes and lengths, tool names, steps, tokens, latency, cost. The exporter never sees the
unmasked fields, and a tracer in the unsafe (leak-baseline) mode never exports.

Transport: OpenTelemetry (OTLP/HTTP JSON) to `POST {host}/api/public/otel/v1/traces` with basic
auth (public/secret key). Langfuse Cloud stopped accepting trace writes on its older ingestion
API for this project and shuts it down on 2026-11-16 (found 2026-11-11, handoff 013), so each
tracer event becomes one OTLP span whose attributes are the masked fields (`fabops.<field>`).
Events of one request share a trace (by `trace_id`, or the agent's `thread_id`).
Off unless `FABOPS_LANGFUSE=1` and both keys are set. Read back with
`GET /api/public/v2/observations` (`scripts/langfuse_check.py`).
"""

from __future__ import annotations

import atexit
import hashlib
import json
import time
import uuid
from typing import Any

import httpx

BATCH = 20
SERVICE = "fabops-copilot"
PREFIX = "fabops."


def _value(v: Any) -> dict[str, Any]:
    if isinstance(v, bool):
        return {"boolValue": v}
    if isinstance(v, int):
        return {"intValue": str(v)}
    if isinstance(v, float):
        return {"doubleValue": v}
    if isinstance(v, str):
        return {"stringValue": v}
    return {"stringValue": json.dumps(v, ensure_ascii=False, default=str)}


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
        self.url = host.rstrip("/") + "/api/public/otel/v1/traces"
        self.client = client or httpx.Client(timeout=10.0)
        self.auth = (public_key, secret_key)
        self.batch = batch
        self.buffer: list[dict[str, Any]] = []
        self.sent = 0
        self.failures = 0
        atexit.register(self.flush)

    @staticmethod
    def to_span(record: dict[str, Any]) -> dict[str, Any]:
        """One masked tracer record -> one OTLP span (attributes = the record's fields)."""
        key = str(record.get("trace_id") or record.get("thread_id") or uuid.uuid4().hex)
        now = time.time_ns()
        return {
            "traceId": hashlib.sha256(key.encode()).hexdigest()[:32],
            "spanId": uuid.uuid4().hex[:16],
            "name": str(record.get("event", "event")),
            "kind": 1,
            "startTimeUnixNano": str(now),
            "endTimeUnixNano": str(now),
            "attributes": [
                {"key": PREFIX + k, "value": _value(v)} for k, v in record.items() if v is not None
            ],
        }

    def payload(self, spans: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [{"key": "service.name", "value": {"stringValue": SERVICE}}]
                    },
                    "scopeSpans": [{"scope": {"name": "fabops.trace"}, "spans": spans}],
                }
            ]
        }

    def export(self, masked_record: dict[str, Any]) -> None:
        self.buffer.append(self.to_span(masked_record))
        if len(self.buffer) >= self.batch:
            self.flush()

    def flush(self) -> None:
        if not self.buffer:
            return
        spans, self.buffer = self.buffer, []
        try:
            r = self.client.post(self.url, json=self.payload(spans), auth=self.auth)
            r.raise_for_status()
            self.sent += len(spans)
        except httpx.HTTPError:
            self.failures += len(spans)  # tracing must never break a request


def exporter_from_settings() -> LangfuseExporter | None:
    from fabops.config import get_settings

    cfg = get_settings()
    public = cfg.langfuse_public_key.get_secret_value() if cfg.langfuse_public_key else ""
    secret = cfg.langfuse_secret_key.get_secret_value() if cfg.langfuse_secret_key else ""
    if not (cfg.fabops_langfuse and public and secret and cfg.langfuse_host):
        return None
    return LangfuseExporter(cfg.langfuse_host, public, secret)
