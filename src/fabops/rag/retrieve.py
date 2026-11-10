"""Retrieval: permission pre-filter -> dense + lexical -> RRF fusion -> optional rerank.

ADR-0003: every candidate set is restricted by `authz.policy.sql_filter` *before* ranking;
dense similarity is exact (no ANN index). The scope comes from the server (ADR-0001) and is
never derived from the query text.

Superseded SOP versions are excluded by default ("優先最新版"), so an old version can
neither be retrieved nor cited; `include_superseded=True` turns this off.

SOP boost for "how do I handle it" questions (ADR-0010): when the query asks for a procedure
(`is_disposal_query`), the fused score of SOP chunks is multiplied by `sop_boost` before the
top chunks are cut, so the SOP's steps reach the LLM instead of incident-report summaries.
It reads only the query text, never the user's identity, and runs after the permission
pre-filter, so it cannot surface anything the scope may not see.

SOP section expansion (small-to-big, ADR-0010 revision): for disposal questions, the
highest-ranked SOP among the context chunks is expanded to all of its sections
(`expand_context`), so the steps and the escalation rule arrive together. The extra sections
are fetched through the same permission filter as every other candidate.
"""

from __future__ import annotations

import json
import re
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

# Questions that ask how to handle an alarm, i.e. want the SOP's procedure (ADR-0010).
DISPOSAL_QUERY = re.compile(
    r"怎麼處理|如何處理|怎麼處置|如何處置|要怎麼處|該怎麼辦|怎麼辦|處置步驟|處置方式|處置程序"
)


def is_disposal_query(query: str) -> bool:
    return DISPOSAL_QUERY.search(query) is not None


@dataclass(frozen=True)
class RetrievalConfig:
    dense: bool = True
    lexical: Lexical = "bm25"
    candidates: int = 50  # per ranker, before fusion
    rrf_k: int = 60
    # Off by default: on dev it did not improve hybrid Recall@5 and costs ~25 s/query on CPU
    # (docs/experiments.md, 2026-11-08). Revisit with GPU rerank.
    rerank: bool = False
    rerank_top: int = 20
    k: int = 8  # chunks returned
    include_superseded: bool = False
    # Multiplier on the fused score of SOP chunks for disposal questions; 1.0 = off.
    # 1.2 is the smallest value that put every open question's SOP steps into the 8 context
    # chunks on dev + calibration (docs/experiments.md, 2026-11-10; ADR-0010).
    sop_boost: float = 1.2
    # Expand the top SOP in the context to all its sections for disposal questions.
    expand_sop: bool = False


@dataclass
class Hit:
    chunk_id: str
    doc_id: str
    text: str
    fab: str
    department: str
    clearance: int
    score: float
    ranks: dict[str, int] = field(default_factory=dict)  # per-ranker rank, 1-based
    doc_type: str = ""  # "sop" / "incident"


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


def boost_sop(scores: dict[str, float], doc_types: dict[str, str], w: float) -> dict[str, float]:
    """Multiply the score of SOP chunks by `w` (ADR-0010)."""
    return {c: s * w if doc_types.get(c) == "sop" else s for c, s in scores.items()}


def merge_sections(hits: list[Hit], doc_id: str, sections: list[Hit]) -> list[Hit]:
    """Put `sections` (one document, in order) where `doc_id` first appears in `hits`."""
    if not sections:
        return hits
    out: list[Hit] = []
    for h in hits:
        if h.doc_id != doc_id:
            out.append(h)
        elif not any(x.doc_id == doc_id for x in out):
            out.extend(sections)
    return out


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

    def expand_context(self, query: str, hits: list[Hit], scope: Scope) -> list[Hit]:
        """Replace the top SOP's chunks in `hits` with all its visible sections, in order.

        Only for disposal questions with `expand_sop` on; other hits keep their order.
        """
        if not self.cfg.expand_sop or not is_disposal_query(query):
            return hits
        top = next((h for h in hits if h.doc_type == "sop"), None)
        if top is None:
            return hits
        cond, params = self._where(scope)
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT c.chunk_id, c.doc_id, c.text, c.fab, c.department, c.clearance, "
                "d.doc_type FROM chunks c "
                f"JOIN documents d USING (doc_id) WHERE {cond} AND c.doc_id = %(doc)s "
                "ORDER BY c.seq",
                {**params, "doc": top.doc_id},
            )
            sections = [
                Hit(cid, did, text, fab, dept, cl, top.score, {}, dtype)
                for cid, did, text, fab, dept, cl, dtype in cur
            ]
        return merge_sections(hits, top.doc_id, sections)

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
                    "SELECT c.chunk_id, c.doc_id, c.text, c.fab, c.department, c.clearance, "
                    "d.doc_type FROM chunks c "
                    f"JOIN documents d USING (doc_id) WHERE {cond} "
                    "ORDER BY c.embedding <=> %(q)s::vector LIMIT %(n)s",
                    {**params, "q": vector_literal(enc.dense[0]), "n": cfg.candidates},
                )
                for cid, did, text, fab, dept, cl, dtype in cur:
                    rows[cid] = {
                        "doc_id": did,
                        "text": text,
                        "fab": fab,
                        "department": dept,
                        "clearance": cl,
                        "doc_type": dtype,
                    }
                    rankings.setdefault("dense", []).append(cid)
            t["dense"] = time.perf_counter() - t0
            t0 = time.perf_counter()
            if cfg.lexical != "none":
                col = "c.tokens" if cfg.lexical == "bm25" else "c.sparse"
                cur.execute(
                    "SELECT c.chunk_id, c.doc_id, c.text, c.fab, c.department, c.clearance, "
                    f"d.doc_type, {col} "
                    "FROM chunks c "
                    f"JOIN documents d USING (doc_id) WHERE {cond}",
                    params,
                )
                cand = cur.fetchall()
                if cfg.lexical == "bm25":
                    scores = bm25_scores(tokenize(query), [r[7] for r in cand])
                else:
                    docs = [r[7] if isinstance(r[7], dict) else json.loads(r[7]) for r in cand]
                    scores = sparse_scores(enc.sparse[0], docs)
                ranked = sorted(zip(scores, cand, strict=True), key=lambda x: -x[0])
                for s, (cid, did, text, fab, dept, cl, dtype, _) in ranked[: cfg.candidates]:
                    if s <= 0:
                        break
                    rows.setdefault(
                        cid,
                        {
                            "doc_id": did,
                            "text": text,
                            "fab": fab,
                            "department": dept,
                            "clearance": cl,
                            "doc_type": dtype,
                        },
                    )
                    rankings.setdefault("lexical", []).append(cid)
            t["lexical"] = time.perf_counter() - t0

        fused = rrf(rankings, cfg.rrf_k)
        if cfg.sop_boost != 1.0 and is_disposal_query(query):
            fused = boost_sop(fused, {c: rows[c]["doc_type"] for c in fused}, cfg.sop_boost)
        order = sorted(fused, key=lambda c: -fused[c])
        hits = [
            Hit(
                c,
                rows[c]["doc_id"],
                rows[c]["text"],
                rows[c]["fab"],
                rows[c]["department"],
                rows[c]["clearance"],
                fused[c],
                {name: r.index(c) + 1 for name, r in rankings.items() if c in r},
                rows[c]["doc_type"],
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
