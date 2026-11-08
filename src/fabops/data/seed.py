"""Load the schema and generated synthetic data into Postgres.

Run: `python -m fabops.data.seed` (uses DATABASE_URL).
"""

from __future__ import annotations

import json
from pathlib import Path

import psycopg

from fabops.config import get_settings

DATA_DIR = Path("data/generated")
SCHEMA = Path(__file__).with_name("schema.sql")

# Load order respects foreign keys. Documents need two passes for superseded_by.
TABLES = ["users", "equipment", "chambers", "lots", "dispatch_log", "alarms", "maintenance"]
DOC_COLUMNS = [
    "doc_id",
    "doc_type",
    "title",
    "fab",
    "department",
    "clearance",
    "sop_key",
    "version",
    "effective_date",
    "source",
    "body_md",
]


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _insert(cur: psycopg.Cursor, table: str, rows: list[dict], columns: list[str]) -> None:
    cols = ", ".join(columns)
    with cur.copy(f"COPY {table} ({cols}) FROM STDIN") as copy:
        for row in rows:
            copy.write_row([row.get(c) for c in columns])


def seed(database_url: str, data_dir: Path = DATA_DIR) -> dict[str, int]:
    counts: dict[str, int] = {}
    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute(SCHEMA.read_text(encoding="utf-8"))
        for table in TABLES:
            rows = read_jsonl(data_dir / f"{table}.jsonl")
            _insert(cur, table, rows, list(rows[0].keys()))
            counts[table] = len(rows)

        docs = read_jsonl(data_dir / "documents.jsonl")
        _insert(cur, "documents", docs, DOC_COLUMNS)
        cur.executemany(
            "UPDATE documents SET superseded_by = %s WHERE doc_id = %s",
            [(d["superseded_by"], d["doc_id"]) for d in docs if d["superseded_by"]],
        )
        counts["documents"] = len(docs)
    return counts


def main() -> None:
    for table, n in seed(get_settings().database_url).items():
        print(f"{table:14s} {n:>6d}")


if __name__ == "__main__":
    main()
