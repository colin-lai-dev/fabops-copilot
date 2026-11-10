"""Build the retrieval index: chunk documents from the DB, embed, store in `chunks`.

    python -m fabops.rag.index [--strategy section|doc] [--incident-split]

Rebuilds the table from scratch each run (it is derived data). Prints chunk count and timing
for docs/experiments.md.
"""

from __future__ import annotations

import argparse
import json
import time
from typing import Any

import psycopg

from fabops.config import get_settings
from fabops.rag.chunk import Chunk, chunk_corpus
from fabops.rag.lexical import tokenize
from fabops.rag.models import Encoder, default_encoder

DOC_FIELDS = [
    "doc_id",
    "doc_type",
    "title",
    "fab",
    "department",
    "clearance",
    "version",
    "body_md",
    "superseded_by",
]


def vector_literal(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.7g}" for x in v) + "]"


def load_documents(conn: psycopg.Connection) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT {', '.join(DOC_FIELDS)} FROM documents ORDER BY doc_id")
        return [dict(zip(DOC_FIELDS, r, strict=True)) for r in cur]


def build(
    conn: psycopg.Connection, encoder: Encoder, *, batch: int = 64, **chunk_kw: Any
) -> dict[str, Any]:
    t0 = time.perf_counter()
    chunks: list[Chunk] = chunk_corpus(load_documents(conn), **chunk_kw)
    t_chunk = time.perf_counter()
    rows = []
    for i in range(0, len(chunks), batch):
        part = chunks[i : i + batch]
        enc = encoder.encode([c.text for c in part])
        for c, dense, sparse in zip(part, enc.dense, enc.sparse, strict=True):
            rows.append(
                (
                    c.chunk_id,
                    c.doc_id,
                    c.seq,
                    c.section,
                    c.text,
                    c.fab,
                    c.department,
                    c.clearance,
                    vector_literal(dense),
                    json.dumps(sparse),
                    tokenize(c.text),
                )
            )
    t_embed = time.perf_counter()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM chunks")
        cur.executemany(
            "INSERT INTO chunks (chunk_id, doc_id, seq, section, text, fab, department, "
            "clearance, embedding, sparse, tokens) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::vector, %s::jsonb, %s)",
            rows,
        )
    conn.commit()
    return {
        "chunks": len(rows),
        "chunk_s": round(t_chunk - t0, 2),
        "embed_s": round(t_embed - t_chunk, 1),
        "total_s": round(time.perf_counter() - t0, 1),
        **chunk_kw,
    }


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--strategy", default="section", choices=["section", "doc"])
    p.add_argument("--max-chars", type=int, default=800)
    p.add_argument("--incident-split", action="store_true", help="split incidents by section")
    a = p.parse_args(argv)
    cfg = get_settings()
    t0 = time.perf_counter()
    encoder = default_encoder()
    load_s = round(time.perf_counter() - t0, 1)
    with psycopg.connect(cfg.database_url) as conn:
        stats = build(
            conn,
            encoder,
            strategy=a.strategy,
            max_chars=a.max_chars,
            incident_whole=not a.incident_split,
        )
    print(
        json.dumps(
            {**stats, "model_load_s": load_s, "model": cfg.embed_model, "device": cfg.embed_device},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
