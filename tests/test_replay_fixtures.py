"""Replay fixtures for the static demo site: synthetic data only, no secrets or local details."""

import json
import re
from pathlib import Path

from fabops.data.world import DEMO_USERS

FIXTURE = Path(__file__).resolve().parents[1] / "web" / "public" / "replay" / "scenes.json"
RAW = FIXTURE.read_text(encoding="utf-8")
DATA = json.loads(RAW)

FORBIDDEN = [
    re.compile(p, re.I)
    for p in (
        r"sk-[a-z0-9_-]{8,}", r"sk-ant", r"pk-lf", r"AIza[0-9a-z_-]{10}", r"gh[pousr]_[a-z0-9]{10}",
        r"eyJ[a-z0-9_-]{10,}\.",  # JWT
        r"[a-z]:\\\\", r"\\users\\\\", r"/home/", r"/users/", r"localhost", r"127\.0\.0\.1",
        r"postgres(ql)?://", r"[\w.+-]+@[\w-]+\.[\w.]+",  # e-mail
        r"\bAUO\b", r"友達", r"colin",
    )
]  # fmt: skip


def test_no_secrets_paths_or_personal_info():
    for pat in FORBIDDEN:
        assert not pat.search(RAW), pat.pattern


def test_only_demo_users_and_fictional_fab():
    ids = {u for u, *_ in DEMO_USERS}
    assert {u["user_id"] for u in DATA["users"]} <= ids
    assert all(s["user"] in ids for s in DATA["scenes"])
    assert "synthetic" in DATA["note"].lower()


def test_every_scene_has_a_recorded_response():
    for s in DATA["scenes"]:
        r = s["response"]
        assert r["answer"] and "status" in r, s["id"]
        assert s["caption_zh"] and s["caption_en"]
    triage = next(s for s in DATA["scenes"] if s["id"] == "triage-approval")
    codes = [st.get("status_code") for st in triage["approval_steps"] if st["kind"] == "decision"]
    assert codes == [403, 403, 200]  # requester, cannot see target, admin


def _visible_ids(user):
    return {DATA["docs"][i]["doc_id"] for i in DATA["visible_by_user"][user]}


def test_citations_and_opened_documents_are_visible_to_the_asker():
    for s in DATA["scenes"]:
        seen = _visible_ids(s["user"])
        assert set(s["response"]["citations"]) <= seen | {"INJ-2026-0001"}, s["id"]
        assert set(s.get("cited_docs", {})) <= seen, s["id"]  # no locked text in the fixture
        for doc_id, doc in s.get("cited_docs", {}).items():
            assert doc["doc_id"] == doc_id and doc["sections"], s["id"]


def test_permission_scenes_block_what_they_should():
    by_id = {s["id"]: s for s in DATA["scenes"]}
    comp = "SOP-FX1-ETC-PRS-0412-v1"
    assert comp in by_id["comp-lead"]["response"]["citations"]
    assert by_id["comp-eng"]["response"]["refused"] and comp not in _visible_ids("eng_fx1_etch")
    assert by_id["litho-other-fab"]["response"]["refused"]
    other = by_id["litho-other-fab"]["response"]["retrieved"]
    assert not any(d.startswith("SOP-FX1") for d in other)
    two = by_id["admin-two-fabs"]["response"]["citations"]
    assert {"INC-2026-0006", "INC-2026-0036"} <= set(two)


def test_six_identity_groups_and_free_exploration():
    users = [u["user_id"] for u in DATA["users"]]
    by_id = {s["id"]: s for s in DATA["scenes"]}
    assert len(DATA["groups"]) >= 2
    for g in DATA["groups"]:
        if g.get("unavailable"):  # shown with its reason in the UI, never silently hidden
            assert not g["scenes"] and g["unavailable"] == "answer_cut_off", g["id"]
            continue
        members = [by_id[i] for i in g["scenes"]]
        assert sorted(m["user"] for m in members) == sorted(users), g["id"]
        assert {m["question"] for m in members} == {g["question"]}
    for u in users:  # every identity has at least two recorded questions to pick from
        assert sum(s["user"] == u for s in DATA["scenes"]) >= 2, u


def test_every_recorded_question_has_six_identities_or_a_reason():
    asked = {(s["question"], s["mode"]) for s in DATA["scenes"]}
    covered = {(g["question"], g["mode"]) for g in DATA["groups"] if g["scenes"]}
    explained = {(s["question"], s["mode"]) for s in DATA["scenes"] if s.get("six_unavailable")}
    assert asked <= covered | explained


def test_group_only_scenes_carry_no_approval_flow():
    for s in DATA["scenes"]:
        if s["id"].startswith("six-"):
            assert not s.get("approval_steps"), s["id"]
