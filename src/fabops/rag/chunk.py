"""Chunking (PLAN Phase 1: by SOP section).

Every chunk starts with a context header — doc id, title, fab, version, section — so a short
section such as an incident's "根本原因" is still findable by its incident id. HTML tables
(a dirty-data type) are flattened to pipe rows; nothing else is parsed.

Strategies (tuned on dev only):
- `section`: one chunk per `## ` section; sections longer than `max_chars` are split on blank
  lines. Incident reports are short, so `incident_whole=True` keeps each as one chunk.
- `doc`: one chunk per document (baseline for the chunking experiment).
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any

_TABLE = re.compile(r"<table>.*?</table>", re.S | re.I)
_ROW = re.compile(r"<tr>(.*?)</tr>", re.S | re.I)
_CELL = re.compile(r"<t[hd]>(.*?)</t[hd]>", re.S | re.I)


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    seq: int
    section: str
    text: str
    fab: str
    department: str
    clearance: int


def flatten_html_tables(text: str) -> str:
    def table(m: re.Match[str]) -> str:
        rows = []
        for row in _ROW.findall(m.group(0)):
            cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in _CELL.findall(row)]
            rows.append("| " + " | ".join(cells) + " |")
        return "\n".join(rows)

    return _TABLE.sub(table, text)


def split_sections(body: str) -> list[tuple[str, str]]:
    """(heading, content) pairs for `## ` sections; the `# ` title line is dropped."""
    out: list[tuple[str, str]] = []
    heading, buf = "", []
    for line in body.split("\n"):
        if line.startswith("## "):
            out.append((heading, "\n".join(buf).strip()))
            heading, buf = line[3:].strip(), []
        elif not line.startswith("# "):
            buf.append(line)
    out.append((heading, "\n".join(buf).strip()))
    return [(h, c) for h, c in out if c]


def header(doc: dict[str, Any], section: str) -> str:
    kind = "SOP" if doc["doc_type"] == "sop" else "異常報告"
    version = f"（第 {doc['version']} 版）" if doc["doc_type"] == "sop" else ""
    head = f"[{doc['doc_id']}] {kind}：{doc['title']}{version}"
    return f"{head}\n{section}" if section else head


def _pieces(content: str, max_chars: int) -> list[str]:
    if len(content) <= max_chars:
        return [content]
    pieces, cur = [], ""
    for para in content.split("\n\n"):
        if cur and len(cur) + len(para) + 2 > max_chars:
            pieces.append(cur)
            cur = para
        else:
            cur = f"{cur}\n\n{para}" if cur else para
    return [*pieces, cur] if cur else pieces


def chunk_document(
    doc: dict[str, Any],
    *,
    strategy: str = "section",
    max_chars: int = 800,
    incident_whole: bool = True,
) -> list[Chunk]:
    body = flatten_html_tables(doc["body_md"])
    if strategy == "doc" or (incident_whole and doc["doc_type"] == "incident"):
        content = "\n\n".join(f"## {h}\n{c}" if h else c for h, c in split_sections(body))
        parts = [("", content)]
    elif strategy == "section":
        parts = [(h, p) for h, c in split_sections(body) for p in _pieces(c, max_chars)]
    else:
        raise ValueError(f"unknown chunking strategy {strategy!r}")
    return [
        Chunk(
            chunk_id=f"{doc['doc_id']}#{i:02d}",
            doc_id=doc["doc_id"],
            seq=i,
            section=section,
            text=f"{header(doc, section)}\n{content}",
            fab=doc["fab"],
            department=doc["department"],
            clearance=int(doc["clearance"]),
        )
        for i, (section, content) in enumerate(parts)
    ]


def chunk_corpus(docs: list[dict[str, Any]], **kw: Any) -> list[Chunk]:
    return [c for d in docs for c in chunk_document(d, **kw)]
