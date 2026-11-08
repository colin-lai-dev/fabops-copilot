import json
from datetime import datetime

import pytest

from fabops.data import generate, world


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    d = tmp_path_factory.mktemp("gen")
    generate.generate(d)
    return d


def _rows(d, name):
    return [json.loads(x) for x in (d / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()]


def test_generation_is_deterministic(out, tmp_path):
    generate.generate(tmp_path)
    for f in out.iterdir():
        assert f.read_bytes() == (tmp_path / f.name).read_bytes(), f.name


def test_no_dispatch_ok_during_pm(out):
    windows = {}
    for m in _rows(out, "maintenance"):
        windows.setdefault(m["chamber_id"], []).append(
            (datetime.fromisoformat(m["start_at"]), datetime.fromisoformat(m["end_at"]))
        )
    rejected = 0
    for d in _rows(out, "dispatch_log"):
        t = datetime.fromisoformat(d["dispatched_at"])
        in_pm = any(s <= t < e for s, e in windows.get(d["chamber_id"], []))
        if in_pm:
            assert d["result"] == "rejected"
            rejected += 1
    assert rejected > 0, "rule should be exercised at least once"


def test_document_counts_and_permissions(out):
    docs = _rows(out, "documents")
    sops = [d for d in docs if d["doc_type"] == "sop"]
    incidents = [d for d in docs if d["doc_type"] == "incident"]
    assert 40 <= len(sops) <= 45
    assert len(incidents) == 150
    for d in docs:
        assert d["fab"] in world.FABS
        assert d["department"] in {*world.DEPARTMENTS, world.SHARED_DEPARTMENT}
        assert d["clearance"] in world.CLEARANCE
    assert {d["clearance"] for d in docs} == {0, 1, 2, 3}


def test_old_versions_point_to_current(out):
    docs = {d["doc_id"]: d for d in _rows(out, "documents")}
    old = [d for d in docs.values() if d["superseded_by"]]
    assert len(old) == 8
    for d in old:
        new = docs[d["superseded_by"]]
        assert new["sop_key"] == d["sop_key"]
        assert new["version"] > d["version"]


def test_facts_appear_in_document_text(out):
    docs = {d["doc_id"]: d for d in _rows(out, "documents")}
    facts = json.loads((out / "facts.json").read_text(encoding="utf-8"))
    for doc_id, entry in facts.items():
        body, f = docs[doc_id]["body_md"], entry["facts"]
        if docs[doc_id]["doc_type"] == "incident":
            for key in ("alarm_code", "equipment_id", "chamber_id", "root_cause", "sop_key"):
                assert str(f[key]) in body, (doc_id, key)
        elif "wait_min" in f:
            assert f"等待 {f['wait_min']} 分鐘" in body, doc_id
            assert str(f["limit_high"]) in body, doc_id


def test_dirty_data_present(out):
    facts = json.loads((out / "facts.json").read_text(encoding="utf-8"))
    tags = {t for v in facts.values() for t in v["dirty_tags"]}
    assert {"abbreviation", "typo", "colloquial", "old_version", "html_table"} <= tags


def test_restricted_content_only_in_high_clearance_sops(out):
    for d in _rows(out, "documents"):
        if "製程補償參數" in d["body_md"]:
            assert d["clearance"] >= 2, d["doc_id"]
