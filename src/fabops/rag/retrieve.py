"""Retrieval: permission pre-filter -> dense + lexical -> RRF fusion -> optional rerank.

ADR-0003: every candidate set is restricted by `authz.policy.sql_filter` *before* ranking;
dense similarity is exact (no ANN index). The scope comes from the server (ADR-0001) and is
never derived from the query text.

Superseded SOP versions are excluded by default ("優先最新版"), so an old version can
neither be retrieved nor cited; `include_superseded=True` turns this off.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

import psycopg

from fabops.authz.policy import sql_filter
from fabops.authz.scope import Scope
from fabops.rag.index import vector_literal
from fabops.rag.lexical import bm25_scores, sparse_scores, tokenize
from fabops.rag.models import Encoder, Reranker

Lexical = Literal["bm25", "sparse", "none"]


@dataclass(frozen=True)
class RetrievalConfig:
    dense: bool = True
    lexical: Lexical = "bm25"
    candidates: int = 50  # per ranker, before fusion
    rrf_k: int = 60
    rerank: bool = True
    rerank_top: int = 20
    k: int = 8  # chunks returned
    include_superseded: bool = False


@dataclass
class Hit:
    chunk_id: str
    doc_id: str
    text: str
    clearance: int
    score: float
    ranks: dict[str, int] = field(default_factory=dict)  # per-ranker rank, 1-based


@dataclass
class Retrieval:
    hits: list[Hit]
    timings_ms: dict[str, float]

    def doc_ids(self) -> list[str]:
        """Documents in rank order, de-duplicated (what Recall@k / MRR are computed on)."""
        seen: dict[str, None] = {}
        for h in self.hits:
            seen.setdefault(h.doc_id, None)
        return list(seen)


def rrf(rankings: dict[str, list[str]], k: int) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranking in rankings.values():
        for rank, cid in enumerate(ranking, 1):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
    return scores


class Retriever:
    def __init__(
        self,
        connect: Callable[[], psycopg.Connection],
        encoder: Encoder,
        reranker: Reranker | None = None,
        config: RetrievalConfig | None = None,
    ):
        config = config or RetrievalConfig()
        if config.rerank and reranker is None:
            raise ValueError("config.rerank=True needs a reranker")
        if not config.dense and config.lexical == "none":
            raise ValueError("at least one ranker is required")
        self.connect, self.encoder, self.reranker, self.cfg = connect, encoder, reranker, config

    def _where(self, scope: Scope) -> tuple[str, dict[str, Any]]:
        cond, params = sql_filter(scope, alias="c.")
        if not self.cfg.include_superseded:
            cond += " AND d.superseded_by IS NULL"
        return cond, params

    def search(self, query: str, scope: Scope) -> Retrieval:
        cfg, t = self.cfg, {}
        t0 = time.perf_counter()
        enc = self.encoder.encode([query])
        t["encode"] = time.perf_counter() - t0
        cond, params = self._where(scope)
        rankings: dict[str, list[str]] = {}
        rows: dict[str, dict[str, Any]] = {}
        with self.connect() as conn, conn.cursor() as cur:
            t0 = time.perf_counter()
            if cfg.dense:
                cur.execute(
                    "SELECT c.chunk_id, c.doc_id, c.text, c.clearance FROM chunks c "
                    f"JOIN documents d USING (doc_id) WHERE {cond} "
                    "ORDER BY c.embedding <=> %(q)s::vector LIMIT %(n)s",
                    {**params, "q": vector_literal(enc.dense[0]), "n": cfg.candidates},
                )
                for cid, did, text, cl in cur:
                    rows[cid] = {"doc_id": did, "text": text, "clearance": cl}
                    rankings.setdefault("dense", []).append(cid)
            t["dense"] = time.perf_counter() - t0
            t0 = time.perf_counter()
            if cfg.lexical != "none":
                col = "c.tokens" if cfg.lexical == "bm25" else "c.sparse"
                cur.execute(
                    f"SELECT c.chunk_id, c.doc_id, c.text, c.clearance, {col} FROM chunks c "
                    f"JOIN documents d USING (doc_id) WHERE {cond}",
                    params,
                )
                cand = cur.fetchall()
                if cfg.lexical == "bm25":
                    scores = bm25_scores(tokenize(query), [r[4] for r in cand])
                else:
                    docs = [r[4] if isinstance(r[4], dict) else json.loads(r[4]) for r in cand]
                    scores = sparse_scores(enc.sparse[0], docs)
                ranked = sorted(zip(scores, cand, strict=True), key=lambda x: -x[0])
                for s, (cid, did, text, cl, _) in ranked[: cfg.candidates]:
                    if s <= 0:
                        break
                    rows.setdefault(cid, {"doc_id": did, "text": text, "clearance": cl})
                    rankings.setdefault("lexical", []).append(cid)
            t["lexical"] = time.perf_counter() - t0

        fused = rrf(rankings, cfg.rrf_k)
        order = sorted(fused, key=lambda c: -fused[c])
        hits = [
            Hit(
                c,
                rows[c]["doc_id"],
                rows[c]["text"],
                rows[c]["clearance"],
                fused[c],
                {name: r.index(c) + 1 for name, r in rankings.items() if c in r},
            )
            for c in order
        ]
        t0 = time.perf_counter()
        if cfg.rerank and hits:
            top = hits[: cfg.rerank_top]
            scores = self.reranker.score(query, [h.text for h in top])  # type: ignore[union-attr]
            for h, s in zip(top, scores, strict=True):
                h.score = s
            hits = sorted(top, key=lambda h: -h.score)
        t["rerank"] = time.perf_counter() - t0
        return Retrieval(hits[: cfg.k], {k: round(v * 1000, 1) for k, v in t.items()})
