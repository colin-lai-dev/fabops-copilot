"""Send a few dev traces to Langfuse and verify what arrived (handoff 013 D, ADR-0007).

1. Runs 2 dev RAG questions and 1 dev agent scenario (local model by default) with the normal
   tracer, which exports masked events to Langfuse when FABOPS_LANGFUSE=1 and keys are set.
2. Reads the events back through the Langfuse public API and checks, programmatically, that
   each payload carries only allowed fields (ids, clearance levels, hashes/lengths, tool names,
   steps, tokens, latency, cost) and none of the question, answer or document texts.

    uv run python scripts/langfuse_check.py

Keys are read by the settings loader and never printed.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evals.run import RESULTS, load_scopes  # noqa: E402
from evals.schema import load_agent_scenarios, load_questions  # noqa: E402
from fabops.authz.trace import ALLOWED  # noqa: E402
from fabops.config import get_settings  # noqa: E402

ALLOWED_EXTRA = {"dropped_fields"}


def walk_strings(x, out):
    if isinstance(x, dict):
        for v in x.values():
            walk_strings(v, out)
    elif isinstance(x, list):
        for v in x:
            walk_strings(v, out)
    elif isinstance(x, str):
        out.append(x)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    cfg = get_settings()
    if not (cfg.fabops_langfuse and cfg.langfuse_public_key and cfg.langfuse_secret_key):
        print("Langfuse is off or keys are missing; nothing sent.")
        return 1
    started = datetime.now(UTC)

    # ---- 1. send: 2 RAG questions + 1 agent scenario from dev
    from evals.agent_eval import Runner
    from evals.systems import load_system

    questions = load_questions([ROOT / "evals" / "dev" / "rule.jsonl"])[:2]
    scopes = load_scopes()
    rag = load_system("rag-hybrid-bm25")
    texts: list[str] = []
    for q in questions:
        out = rag.answer(q.question, scopes[q.user_id])
        texts += [q.question, out.answer]
    scenario = load_agent_scenarios([ROOT / "evals" / "agent" / "dev" / "scenarios.jsonl"])[0]
    runner = Runner()
    o = asyncio.run(runner.graph(scenario, "agent"))
    texts += [scenario.question, o.answer, *o.seen.split("\n")]
    # flush every exporter the tracers created
    import gc

    from fabops.authz.langfuse import LangfuseExporter

    exporters = [x for x in gc.get_objects() if isinstance(x, LangfuseExporter)]
    for e in exporters:
        e.flush()
    sent = sum(e.sent for e in exporters)
    failed = sum(e.failures for e in exporters)
    print(f"exported events: sent={sent} failed={failed}")

    # ---- 2. read back
    auth = (cfg.langfuse_public_key.get_secret_value(), cfg.langfuse_secret_key.get_secret_value())
    url = cfg.langfuse_host.rstrip("/") + "/api/public/v2/observations"
    got: list[dict] = []
    for _ in range(12):  # ingestion is asynchronous
        time.sleep(5)
        params = {
            "fromStartTime": started.isoformat(),
            "toStartTime": datetime.now(UTC).isoformat(),
            "fields": "core,basic,io,metadata",
            "limit": 100,
        }
        r = httpx.get(url, params=params, auth=auth, timeout=30)
        r.raise_for_status()
        got = [
            o for o in r.json().get("data", [])
            if (o.get("metadata") or {}).get("resourceAttributes.service.name") == "fabops-copilot"
        ]  # fmt: skip
        if len(got) >= sent:
            break
    print(f"read back: {len(got)} events")

    # ---- 3. verify
    violations = []
    keys_seen: set[str] = set()
    needles = [t for t in texts if t and len(t) >= 8]
    for ev in got:
        if ev.get("input") or ev.get("output"):
            violations.append(f"{ev['id']}: input/output is not empty")
        meta = ev.get("metadata") or {}
        for k in meta:
            if k in ("scope.name", "resourceAttributes.service.name"):
                continue  # added by the OTLP envelope
            field = k.removeprefix("attributes.fabops.")
            keys_seen.add(field)
            if (
                field not in ALLOWED
                and field not in ALLOWED_EXTRA
                and not field.endswith("_digest")
            ):
                violations.append(f"{ev['id']}: field {k!r} is not allowed")
        strings: list[str] = []
        walk_strings(meta, strings)
        blob = "\n".join(strings)
        for t in needles:
            if t in blob or (len(t) > 30 and t[:30] in blob):
                violations.append(f"{ev['id']}: contains text from a question/answer/document")
                break
    summary = {
        "checked_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "host": cfg.langfuse_host,
        "model": f"{cfg.llm_provider}/{cfg.llm_model}",
        "sent": sent,
        "failed": failed,
        "read_back": len(got),
        "fields_seen": sorted(keys_seen),
        "texts_checked": len(needles),
        "violations": violations,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"{started:%Y%m%dT%H%M%SZ}-langfuse-check.summary.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "violations"}, ensure_ascii=False))
    print("violations:", len(violations), violations[:5])
    return 0 if got and not violations else 1


if __name__ == "__main__":
    raise SystemExit(main())
