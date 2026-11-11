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
    assert codes == [403, 200]
