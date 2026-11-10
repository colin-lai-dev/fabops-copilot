from pathlib import Path

import pytest

from fabops.data.seed import read_jsonl
from fabops.rag.chunk import chunk_corpus, chunk_document, flatten_html_tables

DOCS = read_jsonl(Path("data/generated/documents.jsonl"))


def sop():
    return next(d for d in DOCS if d["doc_type"] == "sop" and "<table>" in d["body_md"])


def incident():
    return next(d for d in DOCS if d["doc_type"] == "incident")


def test_html_table_is_flattened():
    out = flatten_html_tables("<table><tr><th>版次</th></tr><tr><td>1</td></tr></table>")
    assert out == "| 版次 |\n| 1 |"
    assert all("<table" not in c.text for c in chunk_document(sop()))


def test_sop_chunks_follow_sections_and_carry_header():
    d = sop()
    chunks = chunk_document(d)
    assert len(chunks) == d["body_md"].count("\n## ")
    for c in chunks:
        assert c.text.startswith(f"[{d['doc_id']}] SOP：{d['title']}（第 {d['version']} 版）")
        assert c.section and c.section in c.text
    assert [c.seq for c in chunks] == list(range(len(chunks)))


def test_chunks_inherit_document_permissions():
    for c in chunk_corpus(DOCS):
        d = next(x for x in DOCS if x["doc_id"] == c.doc_id)
        assert (c.fab, c.department, c.clearance) == (d["fab"], d["department"], d["clearance"])


def test_incident_kept_whole_by_default():
    d = incident()
    (c,) = chunk_document(d)
    assert d["doc_id"] in c.text and "## 根本原因" in c.text
    assert len(chunk_document(d, incident_whole=False)) > 1


def test_every_body_line_survives_chunking():
    for d in DOCS[:20]:
        text = "\n".join(c.text for c in chunk_document(d))
        for line in flatten_html_tables(d["body_md"]).splitlines():
            if line.strip() and not line.startswith("#"):
                assert line.strip() in text, (d["doc_id"], line)


def test_long_sections_are_split():
    d = {**sop(), "body_md": "# t\n\n## A\n" + "\n\n".join(["段落" * 100] * 3)}
    assert len(chunk_document(d, max_chars=300)) == 3


def test_unknown_strategy():
    with pytest.raises(ValueError):
        chunk_document(sop(), strategy="nope")
