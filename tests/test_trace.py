import json

from fabops.authz.trace import Tracer, digest, mask

SECRET = "復機首批可套用補償值 +9%（chamber pressure），僅限 4 批內使用。"


def test_texts_become_digests_and_unknown_fields_are_dropped():
    out = mask({"event": "x", "doc_ids": ["D1"], "prompt": SECRET}, {"answer": SECRET})
    assert out["answer_digest"] == digest(SECRET)
    assert "prompt" not in out and out["dropped_fields"] == ["prompt"]
    assert SECRET not in json.dumps(out, ensure_ascii=False)


def test_exported_trace_never_contains_content(tmp_path):
    t = Tracer(tmp_path / "traces.jsonl")
    t.event("retrieval", texts={"query": "補償值是多少", "chunk": SECRET}, doc_ids=["D1"])
    t.event("answer", texts={"answer": SECRET}, cited=["D1"], body=SECRET)
    raw = (tmp_path / "traces.jsonl").read_text(encoding="utf-8")
    assert SECRET not in raw and "補償值是多少" not in raw
    assert "+9%" not in raw


def test_debug_mode_keeps_content_local_only(tmp_path):
    t = Tracer(tmp_path / "traces.jsonl", tmp_path / "debug")
    t.event("answer", texts={"answer": SECRET})
    assert SECRET not in (tmp_path / "traces.jsonl").read_text(encoding="utf-8")
    assert SECRET in (tmp_path / "debug" / "debug.jsonl").read_text(encoding="utf-8")


def test_unsafe_baseline_is_explicitly_unmasked(tmp_path):
    t = Tracer(tmp_path / "traces.jsonl", unsafe_unmasked=True)
    t.event("answer", texts={"answer": SECRET})
    assert SECRET in (tmp_path / "traces.jsonl").read_text(encoding="utf-8")
