from collections import Counter

import pytest

from evals.corpus import check_questions
from evals.gen_rule_questions import generate, load_ctx
from evals.schema import QType
from fabops.authz.policy import visible


@pytest.fixture(scope="module")
def ctx():
    return load_ctx()


@pytest.fixture(scope="module")
def questions(ctx):
    return generate(ctx)


def test_deterministic(ctx, questions):
    assert generate(ctx) == questions


def test_every_key_fact_is_in_an_expected_document(ctx, questions):
    res = check_questions(questions, ctx.docs, ctx.scopes)
    assert res.errors == [] and res.warnings == []


def test_counts_cover_every_qtype_except_open(questions):
    counts = Counter(q.qtype for q in questions)
    assert set(counts) == set(QType) - {QType.OPEN}
    assert len(questions) >= 150


def test_no_fact_asked_twice(questions):
    """Each (document, field) is asked once, including the SOP side of cross-doc questions.

    Old-version questions deliberately ask the same latest-version fact twice (two phrasings).
    """
    asked = []
    for q in questions:
        if q.should_refuse or q.qtype is QType.OLD_VERSION:
            continue
        field = q.notes.removeprefix("field=")
        asked += [(doc_id, field) for doc_id in q.expected_doc_ids if doc_id.startswith("SOP")]
        asked += [(doc_id, field) for doc_id in q.expected_doc_ids if doc_id.startswith("INC")]
    old = {(q.expected_doc_ids[0], "wait_min") for q in questions if q.qtype is QType.OLD_VERSION}
    assert len(asked) == len(set(asked))
    assert not set(asked) & old


def test_restricted_compensation_values_are_never_asked(ctx, questions):
    comp = {f["facts"]["comp_value"] for f in ctx.facts.values() if "comp_value" in f["facts"]}
    assert not any(fact in comp for q in questions for fact in q.key_facts)
    assert not any("補償" in q.question for q in questions)


def test_asker_is_least_privileged_visible_user(ctx, questions):
    for q in questions:
        if q.should_refuse:
            assert q.user_id == "admin_all"
            continue
        order = ctx.users_by_privilege
        can = [
            u for u in order if all(visible(ctx.scopes[u], ctx.docs[d]) for d in q.expected_doc_ids)
        ]
        assert q.user_id == can[0]


def test_old_version_questions_target_latest(ctx, questions):
    for q in questions:
        if q.qtype is QType.OLD_VERSION:
            (doc_id,) = q.expected_doc_ids
            assert ctx.docs[doc_id]["superseded_by"] is None and ctx.docs[doc_id]["version"] > 1


def test_identity_never_in_question_text(ctx, questions):
    assert not any(uid in q.question for q in questions for uid in ctx.scopes)
