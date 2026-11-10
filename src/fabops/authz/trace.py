"""Trace exit check (ADR-0007): what leaves the process carries no content.

Allowed: ids, clearance levels, content hashes and lengths, step names, tokens, latency,
cost. Every text — question, chunk, answer — is reduced to `{"sha256": …, "len": …}`.
Fields outside the allowlist are dropped (their names are recorded so a mistake is visible).

Until Langfuse arrives (Phase 2) the sink is `.cache/traces.jsonl`; the Langfuse exporter
must send exactly what `mask()` returns. With `FABOPS_DEBUG_TRACE=1` the unmasked event is
also written to `.cache/debug-traces/` (gitignored), which is never exported.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

ALLOWED = frozenset(
    {
        "event", "ts", "trace_id", "step", "scope", "model", "provider", "tool",
        "doc_ids", "chunk_ids", "clearances", "n_hits", "cited", "dropped_citations",
        "refused", "cached", "input_tokens", "output_tokens", "cost_usd", "latency_ms",
        "timings_ms", "error_type", "config",
    }
)  # fmt: skip


def digest(text: str) -> dict[str, Any]:
    return {"sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], "len": len(text)}


def mask(fields: dict[str, Any], texts: dict[str, str] | None = None) -> dict[str, Any]:
    out = {k: v for k, v in fields.items() if k in ALLOWED}
    dropped = sorted(set(fields) - ALLOWED)
    if dropped:
        out["dropped_fields"] = dropped
    for name, text in (texts or {}).items():
        out[f"{name}_digest"] = digest(text)
    return out


class Tracer:
    def __init__(
        self,
        path: str | Path = ".cache/traces.jsonl",
        debug_dir: str | Path | None = None,
        *,
        unsafe_unmasked: bool = False,
    ):
        """`unsafe_unmasked=True` exists only for the "no exit checks" leak-test baseline."""
        self.path = Path(path)
        self.debug_dir = Path(debug_dir) if debug_dir else None
        self.unsafe_unmasked = unsafe_unmasked

    @classmethod
    def from_env(cls) -> Tracer:
        from fabops.config import get_settings

        cfg = get_settings()
        cache = Path(cfg.fabops_cache_dir).parent
        debug = cache / "debug-traces" if cfg.fabops_debug_trace else None
        return cls(cache / "traces.jsonl", debug)

    def event(self, name: str, texts: dict[str, str] | None = None, **fields: Any) -> dict:
        fields = {"event": name, "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **fields}
        record = {**fields, **(texts or {})} if self.unsafe_unmasked else mask(fields, texts)
        self._append(self.path, record)
        if self.debug_dir is not None:
            self._append(self.debug_dir / "debug.jsonl", {**fields, **(texts or {})})
        return record

    @staticmethod
    def _append(path: Path, record: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
