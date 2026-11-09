from collections import Counter

import pytest

from evals.corpus import load_corpus
from evals.gen_leak_cases import (
    BOUNDARIES,
    PATHS,
    PER_CELL,
    USERS,
    failed_conditions,
    generate,
    insider_order,
    table,
)
from evals.leak import check_leak_cases, contains_any
from evals.run import load_scopes
from evals.schema import LeakPath
from fabops.authz.policy import visible
from fabops.authz.scope import Scope
from fabops.data.seed import read_jsonl


@pytest.fixture(scope="module")
def world():
    docs, scopes = load_corpus(), load_scopes()
    return docs, scopes, generate(docs, scopes, insider_order(list(read_jsonl(USERS))))


def _boundary(case) -> str:
    return case.notes.split("boundary=")[1].split(";")[0]


def _outsider(case) -> str:
    return case.notes.split("outsider=")[1]


def test_failed_conditions():
    doc = {"fab": "FX1", "department": "etch", "clearance": 2}
    assert failed_conditions(Scope.of(["FX1"], ["etch"], 2), doc) == set()
    assert failed_conditions(Scope.of(["FX2"], ["etch"], 2), doc) == {"cross_fab"}
    assert failed_conditions(Scope.of(["FX1"], ["litho"], 2), doc) == {"cross_dept"}
    assert failed_conditions(Scope.of(["FX1"], ["etch"], 1), doc) == {"clearance"}
    shared = {**doc, "department": "shared"}
    assert failed_conditions(Scope.of(["FX1"], ["litho"], 2), shared) == set()


def test_deterministic(world):
    docs, scopes, cases = world
    assert generate(docs, scopes, insider_order(list(read_jsonl(USERS)))) == cases


def test_every_cell_is_filled(world):
    _, _, cases = world
    assert table(cases) == Counter({(b, p.value): PER_CELL for b in BOUNDARIES for p in PATHS})


def test_cases_pass_the_corpus_check(world):
    docs, scopes, cases = world
    res = check_leak_cases(cases, docs, scopes)
    assert res.errors == [] and res.warnings == []


def test_outsider_fails_exactly_the_named_condition(world):
    docs, scopes, cases = world
    for c in cases:
        doc = docs[c.target_doc_ids[0]]
        assert failed_conditions(scopes[_outsider(c)], doc) == {_boundary(c)}, c.cid
        if c.path is not LeakPath.TRACE:
            assert c.asker_user_id == _outsider(c)


def test_forbidden_strings_are_distinctive(world):
    docs, scopes, cases = world
    for c in cases:
        outsider = scopes[_outsider(c)]
        others = "".join(
            d["body_md"]
            for d in docs.values()
            if d["doc_id"] not in c.target_doc_ids and visible(outsider, d)
        )
        assert not contains_any(others, c.forbidden_strings), c.cid
        assert not contains_any(c.question, c.forbidden_strings), c.cid


def test_no_superseded_targets(world):
    docs, _, cases = world
    assert not [c.cid for c in cases if docs[c.target_doc_ids[0]].get("superseded_by")]
