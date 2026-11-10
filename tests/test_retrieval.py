import hashlib
import random

import psycopg
import pytest

from fabops.authz.policy import scope_of_user, visible
from fabops.config import get_settings
from fabops.rag.lexical import bm25_scores, sparse_scores, tokenize
from fabops.rag.models import Encoded
from fabops.rag.retrieve import RetrievalConfig, Retriever, rrf

# ---------------------------------------------------------------- unit


def test_codes_stay_whole_tokens():
    toks = tokenize("FX1-ETCHER-02 跳 ETC-PRS-0412，見 INC-2026-0001")
    assert {"fx1-etcher-02", "etc-prs-0412", "inc-2026-0001"} <= set(toks)


def test_domain_words_are_kept():
    assert "腔體壓力異常" in tokenize("發生腔體壓力異常時")


def test_bm25_prefers_matching_and_rarer_terms():
    docs = [["壓力", "上限"], ["溫度", "上限"], ["溫度", "下限"]]
    s = bm25_scores(["壓力", "上限"], docs)
    assert s[0] > s[1] > s[2] == 0.0
    assert bm25_scores(["x"], []) == []


def test_sparse_scores_are_weight_products():
    assert sparse_scores({"1": 0.5, "2": 1.0}, [{"1": 0.2}, {"3": 9.0}]) == [0.1, 0.0]


def test_rrf_rewards_agreement():
    s = rrf({"a": ["x", "y"], "b": ["y", "z"]}, k=60)
    assert s["y"] > s["x"] > s["z"]


def test_config_validation():
    with pytest.raises(ValueError):
        Retriever(lambda: None, None, None, RetrievalConfig(rerank=True))
    with pytest.raises(ValueError):
        Retriever(
            lambda: None, None, None, RetrievalConfig(dense=False, lexical="none", rerank=False)
        )


# ---------------------------------------------------------------- DB (needs `make index`)


class FakeEncoder:
    """Deterministic pseudo-embeddings: enough to exercise filtering, not relevance."""

    def encode(self, texts):
        dense = []
        for t in texts:
            rng = random.Random(hashlib.sha256(t.encode()).digest())
            dense.append([rng.uniform(-1, 1) for _ in range(1024)])
        return Encoded(dense=dense, sparse=[{} for _ in texts])


class FakeReranker:
    def score(self, query, texts):
        return [float(len(t)) for t in texts]


@pytest.fixture(scope="module")
def db():
    url = get_settings().database_url
    with psycopg.connect(url) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM chunks WHERE embedding IS NOT NULL")
        if cur.fetchone()[0] == 0:
            pytest.skip("chunks not indexed (python -m fabops.rag.index)")
        cur.execute("SELECT user_id, fabs, departments, clearance FROM users")
        users = [
            dict(zip(("user_id", "fabs", "departments", "clearance"), r, strict=True)) for r in cur
        ]
        cur.execute("SELECT doc_id, fab, department, clearance, superseded_by FROM documents")
        docs = {
            r[0]: dict(zip(("fab", "department", "clearance", "superseded_by"), r[1:], strict=True))
            for r in cur
        }
    return url, users, docs


@pytest.mark.db
@pytest.mark.parametrize("lexical", ["bm25", "none"])
def test_no_hit_outside_scope_and_no_superseded(db, lexical):
    url, users, docs = db
    cfg = RetrievalConfig(lexical=lexical, rerank=True, k=50, candidates=200, rerank_top=200)
    r = Retriever(lambda: psycopg.connect(url), FakeEncoder(), FakeReranker(), cfg)
    for u in users:
        scope = scope_of_user(u)
        for query in ["腔體壓力上限", "INC-2026-0001 根本原因", "補償參數"]:
            for h in r.search(query, scope).hits:
                assert visible(scope, docs[h.doc_id]), (u["user_id"], h.doc_id)
                assert docs[h.doc_id]["superseded_by"] is None


@pytest.mark.db
def test_superseded_can_be_included_explicitly(db):
    url, users, docs = db
    admin = scope_of_user(next(u for u in users if u["user_id"] == "admin_all"))
    cfg = RetrievalConfig(
        lexical="bm25", rerank=False, k=500, candidates=500, include_superseded=True
    )
    r = Retriever(lambda: psycopg.connect(url), FakeEncoder(), None, cfg)
    got = {h.doc_id for h in r.search("處置程序 等待 重新量測", admin).hits}
    assert any(docs[d]["superseded_by"] for d in got)


def test_disposal_query_detection():
    from fabops.rag.retrieve import is_disposal_query

    assert is_disposal_query("FX1 的 ETCHER CHC 剛跳「終點偵測逾時」，我現在該怎麼處理？")
    assert is_disposal_query("FX3 廠的蝕刻機台壓力異常要怎麼處理？")
    assert not is_disposal_query("SOP-FX1-ETC-EPD-0118 的上限是多少？")


def test_boost_sop_only_touches_sop_chunks():
    from fabops.rag.retrieve import boost_sop

    got = boost_sop({"s": 1.0, "i": 1.1}, {"s": "sop", "i": "incident"}, 1.2)
    assert got == {"s": 1.2, "i": 1.1}
    assert boost_sop({"s": 1.0}, {"s": "sop"}, 1.0) == {"s": 1.0}


@pytest.mark.db
def test_sop_boost_keeps_the_permission_filter(db):
    url, users, docs = db
    cfg = RetrievalConfig(lexical="bm25", k=50, candidates=200, sop_boost=2.0)
    r = Retriever(lambda: psycopg.connect(url), FakeEncoder(), None, cfg)
    for u in users:
        scope = scope_of_user(u)
        for h in r.search("腔體壓力異常要怎麼處理？", scope).hits:
            assert visible(scope, docs[h.doc_id]), (u["user_id"], h.doc_id)
            assert h.doc_type in ("sop", "incident")


def _h(cid, doc, dtype="sop"):
    from fabops.rag.retrieve import Hit

    return Hit(cid, doc, cid, "FX1", "etch", 1, 1.0, {}, dtype)


def test_merge_sections_puts_the_whole_sop_at_its_first_position():
    from fabops.rag.retrieve import merge_sections

    hits = [_h("INC-1#00", "INC-1", "incident"), _h("S#03", "S"), _h("T#01", "T"), _h("S#02", "S")]
    sections = [_h(f"S#0{i}", "S") for i in range(5)]
    got = [h.chunk_id for h in merge_sections(hits, "S", sections)]
    assert got == ["INC-1#00", "S#00", "S#01", "S#02", "S#03", "S#04", "T#01"]
    assert merge_sections(hits, "S", []) == hits


def test_expand_context_is_off_for_other_questions():
    cfg = RetrievalConfig(expand_sop=True)
    r = Retriever(lambda: None, None, None, cfg)  # would fail if it touched the DB
    hits = [_h("S#03", "S")]
    assert r.expand_context("SOP 的上限是多少？", hits, None) == hits
    off = Retriever(lambda: None, None, None, RetrievalConfig(expand_sop=False))
    assert off.expand_context("要怎麼處理？", hits, None) == hits


@pytest.mark.db
def test_expand_context_respects_the_permission_filter(db):
    url, users, docs = db
    cfg = RetrievalConfig(lexical="bm25", k=8, candidates=200, expand_sop=True)
    r = Retriever(lambda: psycopg.connect(url), FakeEncoder(), None, cfg)
    for u in users:
        scope = scope_of_user(u)
        q = "腔體壓力異常要怎麼處理？"
        hits = r.expand_context(q, r.search(q, scope).hits, scope)
        for h in hits:
            assert visible(scope, docs[h.doc_id]), (u["user_id"], h.doc_id)
        sops = [h.doc_id for h in hits if h.doc_type == "sop"]
        if sops:  # the top SOP's sections are contiguous and unique
            top = [h.chunk_id for h in hits if h.doc_id == sops[0]]
            assert top == sorted(set(top))
