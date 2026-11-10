"""Systems under test. A system answers one question for one already-resolved scope.

The scope is injected by the runner from the question's `user_id` (ADR-0001); a system must
never read identity from the question text.

Select with `--system NAME` (registered below), `--system ret-<preset>[-rerank]` for
retrieval-only runs, or `--system package.module:factory`, where
the factory takes no arguments and returns an object with `name` and `answer()`.
"""

from __future__ import annotations

import importlib
import re
from collections.abc import Callable
from typing import Protocol

from evals.baselines import UNSAFE_SUFFIXES, NaiveQuestionCache
from evals.schema import SystemOutput
from fabops.authz.scope import Scope


class System(Protocol):
    name: str

    def answer(self, question: str, scope: Scope) -> SystemOutput: ...


class RefuseAll:
    """Floor baseline: always refuses. Checks the harness and anchors refusal metrics."""

    name = "refuse_all"

    def answer(self, question: str, scope: Scope) -> SystemOutput:
        return SystemOutput(answer="查無可用資料，無法回答。", refused=True, latency_ms=0.0)


REGISTRY: dict[str, Callable[[], System]] = {"refuse_all": RefuseAll}


# ---------------------------------------------------------------- retrieval only (no LLM)

# The SOP boost (ADR-0010) is part of the default system only; the other presets are
# baselines and earlier experiments, kept at 1.0 so their numbers stay comparable.
RETRIEVAL_PRESETS = {
    "dense": {"dense": True, "lexical": "none", "sop_boost": 1.0},
    "bm25": {"dense": False, "lexical": "bm25", "sop_boost": 1.0},
    "sparse": {"dense": False, "lexical": "sparse", "sop_boost": 1.0},
    "hybrid-bm25": {"dense": True, "lexical": "bm25"},  # RetrievalConfig default: 1.2
    "hybrid-sparse": {"dense": True, "lexical": "sparse", "sop_boost": 1.0},
}


def make_retriever(*, unfiltered: bool = False, **overrides):
    """Retriever wired to the DB and the default models (lazy imports keep tests light).

    `unfiltered=True` is the eval-only no-pre-filter leak baseline (`evals/baselines.py`).
    """
    import psycopg

    from evals.baselines import UnfilteredRetriever
    from fabops.config import get_settings
    from fabops.rag.models import default_encoder, default_reranker
    from fabops.rag.retrieve import RetrievalConfig, Retriever

    cfg = RetrievalConfig(**overrides)
    url = get_settings().database_url
    cls = UnfilteredRetriever if unfiltered else Retriever
    return cls(
        lambda: psycopg.connect(url),
        default_encoder(),
        default_reranker() if cfg.rerank else None,
        cfg,
    )


class RetrievalOnly:
    """Returns the ranked documents and no answer: for Recall@k / MRR without LLM cost."""

    def __init__(self, name: str, retriever):
        self.name, self.retriever = name, retriever

    def answer(self, question: str, scope: Scope) -> SystemOutput:
        r = self.retriever.search(question, scope)
        return SystemOutput(answer="", retrieved=r.doc_ids(), latency_ms=sum(r.timings_ms.values()))


_SOP = re.compile(r"-sop(\d+(?:\.\d+)?)")


def split_sop_boost(spec: str) -> tuple[str, dict[str, float]]:
    """Remove a `-sopW` suffix (SOP boost for disposal questions, ADR-0010) from a spec.

    Returns the remaining spec and the retriever override (`{}` = the preset's default).
    `-sop1` turns the boost off, e.g. to compare against the default.
    """
    m = _SOP.search(spec)
    if not m:
        return spec, {}
    return spec[: m.start()] + spec[m.end() :], {"sop_boost": float(m.group(1))}


def retrieval_system(spec: str) -> System:
    """`ret-<preset>[-rerank][-sopW]`, e.g. `ret-dense`, `ret-hybrid-bm25-rerank`."""
    base, sop = split_sop_boost(spec)
    body = base.removeprefix("ret-")
    rerank = body.endswith("-rerank")
    preset = body.removesuffix("-rerank")
    if preset not in RETRIEVAL_PRESETS:
        raise ValueError(f"unknown retrieval preset {preset!r}; one of {sorted(RETRIEVAL_PRESETS)}")
    # k=20 chunks so that at least 5 distinct documents are usually ranked.
    retriever = make_retriever(**{**RETRIEVAL_PRESETS[preset], **sop}, rerank=rerank, k=20)
    return RetrievalOnly(spec, retriever)


# ---------------------------------------------------------------- full RAG (LLM)


class RagSystem:
    def __init__(self, name: str, answerer):
        self.name, self.answerer = name, answerer

    def answer(self, question: str, scope: Scope) -> SystemOutput:
        a = self.answerer.answer(question, scope)
        return SystemOutput(
            answer=a.text,
            citations=a.citations,
            retrieved=a.retrieved,
            refused=a.refused,
            latency_ms=a.latency_ms,
            input_tokens=a.input_tokens,
            output_tokens=a.output_tokens,
            cost_usd=a.cost_usd,
            error=a.error,
        )


_CTX = re.compile(r"-ctx(\d+)$")


def parse_rag_spec(spec: str) -> tuple[str, bool, bool, int]:
    """`rag-<preset>[-rerank][-noexit][-ctxN]` -> (preset, rerank, exit_checks, context_chunks).

    `-ctxN` sets how many chunks go to the LLM (default 8), for the tuning experiment.
    """
    body = spec.removeprefix("rag-")
    context_chunks = 8
    if m := _CTX.search(body):
        context_chunks = int(m.group(1))
        body = body[: m.start()]
    exit_checks = not body.endswith("-noexit")
    body = body.removesuffix("-noexit")
    rerank = body.endswith("-rerank")
    preset = body.removesuffix("-rerank")
    if preset not in RETRIEVAL_PRESETS:
        raise ValueError(f"unknown retrieval preset {preset!r}; one of {sorted(RETRIEVAL_PRESETS)}")
    if context_chunks < 1:
        raise ValueError("-ctxN needs N >= 1")
    return preset, rerank, exit_checks, context_chunks


def rag_system(spec: str) -> System:
    """`rag-<preset>[-rerank][-noexit][-ctxN][-sopW][-noprefilter|-naivecache]`, e.g. `rag-dense`
    (PLAN baseline: vector only,
    no rerank) or `rag-hybrid-bm25-rerank`. `-noexit` is the no-exit-checks leak baseline."""
    from fabops.authz.trace import Tracer
    from fabops.config import get_settings
    from fabops.llm.client import LLMClient
    from fabops.rag.answer import Answerer

    # eval-only unsafe baselines (evals/baselines.py): strip their suffix first
    unsafe = next((s for s in UNSAFE_SUFFIXES if spec.endswith(s)), None)
    base = spec.removesuffix(unsafe) if unsafe else spec
    base, sop = split_sop_boost(base)
    preset, rerank, exit_checks, context_chunks = parse_rag_spec(base)
    retriever = make_retriever(
        **{**RETRIEVAL_PRESETS[preset], **sop},
        rerank=rerank,
        k=20,
        unfiltered=unsafe == "-noprefilter",
    )
    client = LLMClient.from_env()
    if not exit_checks:
        client.unsafe_share_cache = True
    tracer = (
        Tracer.from_env()
        if exit_checks
        else Tracer(
            f"{get_settings().fabops_cache_dir}/../traces-unmasked.jsonl", unsafe_unmasked=True
        )
    )
    system = RagSystem(
        spec,
        Answerer(retriever, client, tracer, context_chunks=context_chunks, exit_checks=exit_checks),
    )
    if unsafe == "-naivecache":
        return NaiveQuestionCache(system, spec)
    return system


def load_system(spec: str) -> System:
    if spec in REGISTRY:
        return REGISTRY[spec]()
    if spec.startswith("ret-"):
        return retrieval_system(spec)
    if spec.startswith("rag-"):
        return rag_system(spec)
    module, sep, attr = spec.partition(":")
    if not sep:
        raise ValueError(f"unknown system {spec!r}; registered: {sorted(REGISTRY)}")
    return getattr(importlib.import_module(module), attr)()
