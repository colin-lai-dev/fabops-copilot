"""Systems under test. A system answers one question for one already-resolved scope.

The scope is injected by the runner from the question's `user_id` (ADR-0001); a system must
never read identity from the question text.

Select with `--system NAME` (registered below), `--system ret-<preset>[-rerank]` for
retrieval-only runs, or `--system package.module:factory`, where
the factory takes no arguments and returns an object with `name` and `answer()`.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Protocol

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

RETRIEVAL_PRESETS = {
    "dense": {"dense": True, "lexical": "none"},
    "bm25": {"dense": False, "lexical": "bm25"},
    "sparse": {"dense": False, "lexical": "sparse"},
    "hybrid-bm25": {"dense": True, "lexical": "bm25"},
    "hybrid-sparse": {"dense": True, "lexical": "sparse"},
}


def make_retriever(**overrides):
    """Retriever wired to the DB and the default models (lazy imports keep tests light)."""
    import psycopg

    from fabops.config import get_settings
    from fabops.rag.models import default_encoder, default_reranker
    from fabops.rag.retrieve import RetrievalConfig, Retriever

    cfg = RetrievalConfig(**overrides)
    url = get_settings().database_url
    return Retriever(
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


def retrieval_system(spec: str) -> System:
    """`ret-<preset>[-rerank]`, e.g. `ret-dense`, `ret-hybrid-bm25-rerank`."""
    body = spec.removeprefix("ret-")
    rerank = body.endswith("-rerank")
    preset = body.removesuffix("-rerank")
    if preset not in RETRIEVAL_PRESETS:
        raise ValueError(f"unknown retrieval preset {preset!r}; one of {sorted(RETRIEVAL_PRESETS)}")
    # k=20 chunks so that at least 5 distinct documents are usually ranked.
    retriever = make_retriever(**RETRIEVAL_PRESETS[preset], rerank=rerank, k=20)
    return RetrievalOnly(spec, retriever)


def load_system(spec: str) -> System:
    if spec in REGISTRY:
        return REGISTRY[spec]()
    if spec.startswith("ret-"):
        return retrieval_system(spec)
    module, sep, attr = spec.partition(":")
    if not sep:
        raise ValueError(f"unknown system {spec!r}; registered: {sorted(REGISTRY)}")
    return getattr(importlib.import_module(module), attr)()
