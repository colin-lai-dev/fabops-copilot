import json

import pytest

from evals import run as runner
from evals.schema import QType, Question, SystemOutput, dump_questions, load_questions
from evals.split import split_pool, stratified_split
from fabops.authz.scope import Scope


def q(qid="R-FACT-0001", qtype="fact", **kw):
    base = {
        "qid": qid,
        "qtype": qtype,
        "source": "rule",
        "question": "（測試）問題",
        "user_id": "eng_fx1_etch",
        "key_facts": ["10 分鐘"],
        "expected_doc_ids": ["SOP-FX1-ETC-PRS-0412-v1"],
    }
    return Question(**{**base, **kw})


# ---------------------------------------------------------------- schema


def test_refuse_question_needs_no_docs_or_facts():
    r = q("R-REFUSE-0001", "refuse", should_refuse=True, key_facts=[], expected_doc_ids=[])
    assert r.should_refuse


@pytest.mark.parametrize(
    "kw",
    [
        {"qtype": "refuse"},  # refuse without should_refuse
        {"should_refuse": True},  # refusal with key facts
        {"expected_doc_ids": []},  # answerable without a target document
        {"key_facts": []},  # factual question without facts
        {"qtype": "open", "key_facts": []},  # open without rubric
        {"qtype": "cross_doc"},  # cross_doc with a single document
        {"identity": "admin_all"},  # unknown field
        {"qid": "bad id"},
    ],
)
def test_inconsistent_questions_are_rejected(kw):
    with pytest.raises(ValueError):
        q(**kw)


def test_open_question_with_rubric():
    assert q("H-0001", "open", source="handwritten", key_facts=[], rubric="說明處置順序").rubric


def test_roundtrip_and_duplicate_detection(tmp_path):
    path = tmp_path / "pool.jsonl"
    dump_questions([q(), q("R-FACT-0002")], path)
    assert [x.qid for x in load_questions([path])] == ["R-FACT-0001", "R-FACT-0002"]
    dump_questions([q(), q()], path)
    with pytest.raises(ValueError, match="duplicate"):
        load_questions([path])


def test_example_file_is_valid():
    examples = load_questions([runner.EVALS / "questions.example.jsonl"])
    assert {e.qtype for e in examples} == set(QType)


# ---------------------------------------------------------------- split


def pool(n_per_type=10):
    out = []
    for t in ("fact", "paraphrase"):
        for i in range(n_per_type):
            out.append(q(f"R-{t.upper()}-{i:04d}", t))
    return out


def test_split_is_stratified_40_60_and_deterministic():
    dev, test = stratified_split(pool())
    assert len(dev) == 8 and len(test) == 12
    assert sum(x.qtype is QType.FACT for x in dev) == 4
    assert not {x.qid for x in dev} & {x.qid for x in test}
    assert stratified_split(pool()) == (dev, test)


def test_split_never_overwrites_frozen_test(tmp_path):
    src = tmp_path / "rule.jsonl"
    dump_questions(pool(), src)
    assert split_pool(src, evals_dir=tmp_path) == {"dev": 8, "test": 12}
    with pytest.raises(FileExistsError):
        split_pool(src, evals_dir=tmp_path)


# ---------------------------------------------------------------- runner


@pytest.fixture
def eval_dirs(tmp_path):
    (tmp_path / "dev").mkdir()
    (tmp_path / "test").mkdir()
    dump_questions([q(), q("R-FACT-0002", user_id="op_fx1_etch")], tmp_path / "dev" / "a.jsonl")
    dump_questions([q("R-FACT-0003")], tmp_path / "test" / "a.jsonl")
    users = tmp_path / "users.jsonl"
    users.write_text(
        "\n".join(
            json.dumps(u)
            for u in [
                {
                    "user_id": "eng_fx1_etch",
                    "fabs": ["FX1"],
                    "departments": ["etch"],
                    "clearance": 1,
                },
                {
                    "user_id": "op_fx1_etch",
                    "fabs": ["FX1"],
                    "departments": ["etch"],
                    "clearance": 0,
                },
            ]
        ),
        encoding="utf-8",
    )
    return {"evals_dir": tmp_path, "results_dir": tmp_path / "results", "users_path": users}


def test_test_split_is_locked_without_flag(eval_dirs):
    with pytest.raises(runner.TestSplitLocked):
        runner.run("test", "refuse_all", **eval_dirs)


def test_dev_run_saves_outputs_and_summary(eval_dirs):
    s = runner.run("dev", "refuse_all", **eval_dirs)
    assert s["n"] == 2 and s["errors"] == 0 and s["n_by_qtype"] == {"fact": 2}
    assert s["metrics"] is None  # score.py is still a stub
    raw = (eval_dirs["results_dir"] / f"{s['run_id']}.jsonl").read_text(encoding="utf-8")
    assert len(raw.splitlines()) == 2
    assert "（測試）問題" not in raw  # outputs store qids, not question text


class RecordingSystem:
    name = "recording"

    def __init__(self):
        self.calls = []

    def answer(self, question, scope):
        self.calls.append((question, scope))
        if scope.clearance == 0:
            raise RuntimeError("boom")
        return SystemOutput(answer="ok")


def test_identity_is_injected_as_scope_not_text(eval_dirs, monkeypatch):
    system = RecordingSystem()
    monkeypatch.setattr(runner, "load_system", lambda spec: system)
    s = runner.run("dev", "x", **eval_dirs)
    (text1, scope1), (_, scope2) = system.calls
    assert "eng_fx1_etch" not in text1
    assert scope1 == Scope.of(["FX1"], ["etch"], 1) and scope2.clearance == 0
    assert s["errors"] == 1  # a failing question is recorded, not fatal


def test_unknown_user_is_rejected(eval_dirs):
    dump_questions([q(user_id="ghost")], eval_dirs["evals_dir"] / "dev" / "a.jsonl")
    with pytest.raises(ValueError, match="ghost"):
        runner.run("dev", "refuse_all", **eval_dirs)


# ---------------------------------------------------------------- corpus check


def test_corpus_check_rejects_unknown_and_invisible_docs():
    from evals.corpus import check_questions

    docs = {"D1": {"fab": "FX2", "department": "etch", "clearance": 1, "body_md": "等待 10 分鐘"}}
    scopes = {"eng_fx1_etch": Scope.of(["FX1"], ["etch"], 1)}
    res = check_questions(
        [q(expected_doc_ids=["D1"]), q("R-FACT-0002", expected_doc_ids=["NOPE"])], docs, scopes
    )
    assert any("cannot see" in e for e in res.errors)  # cross-fab: belongs in the leakage set
    assert any("unknown doc" in e for e in res.errors)
    assert res.warnings == []  # "10 分鐘" found literally
