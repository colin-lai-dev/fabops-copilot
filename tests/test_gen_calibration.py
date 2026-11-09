import json
from pathlib import Path

import pytest

from evals.corpus import check_questions, load_corpus
from evals.gen_calibration import HANDWRITTEN, generate, parse_sop
from evals.gen_leak_cases import USERS, insider_order
from evals.run import load_scopes
from evals.schema import QType, load_questions
from fabops.data.seed import read_jsonl

FACTS = Path(__file__).resolve().parents[1] / "data" / "generated" / "facts.json"


@pytest.fixture(scope="module")
def world():
    docs, scopes = load_corpus(), load_scopes()
    hand = load_questions([HANDWRITTEN])
    exclude = {d for q in hand if q.qtype is QType.OPEN for d in q.expected_doc_ids}
    qs = generate(docs, scopes, insider_order(list(read_jsonl(USERS))), exclude)
    return docs, scopes, exclude, qs


def test_one_open_question_per_unused_current_sop(world):
    docs, _, exclude, qs = world
    targets = [q.expected_doc_ids[0] for q in qs]
    assert len(targets) == len(set(targets)) == 22
    assert not set(targets) & exclude
    assert all(q.qtype is QType.OPEN and q.rubric for q in qs)
    assert not [t for t in targets if docs[t].get("superseded_by")]


def test_questions_pass_the_corpus_check(world):
    docs, scopes, _, qs = world
    assert check_questions(qs, docs, scopes).errors == []


def test_parsed_values_match_the_skeleton_facts(world):
    docs, _, _, qs = world
    facts = json.loads(FACTS.read_text(encoding="utf-8"))
    for q in qs:
        doc_id = q.expected_doc_ids[0]
        f, want = parse_sop(docs[doc_id]), facts[doc_id]["facts"]
        assert int(f["wait"]) == want["wait_min"], doc_id
        assert int(f["consecutive"]) == want["consecutive"], doc_id
        assert f["notify"] == want["notify_role"], doc_id
        assert f["pm"] == want["pm_type"], doc_id
        assert int(f["wafers"]) == want["monitor_wafers"], doc_id
        assert int(f["esc_hours"]) == want["escalate_hours"], doc_id
        assert float(q.question.split("量到 ")[1].split(" ")[0]) > want["limit_high"], doc_id
