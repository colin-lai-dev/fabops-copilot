import json

import pytest

from evals import leak
from evals.schema import JudgeLabel, LeakCase, SystemOutput, load_leak_cases
from fabops.authz.scope import Scope

FX1_ETCH = Scope.of(["FX1"], ["etch"], 2)
FX2_ETCH = Scope.of(["FX2"], ["etch"], 2)
SCOPES = {"fx1": FX1_ETCH, "fx2": FX2_ETCH}
DOCS = {
    "D-FX1": {"fab": "FX1", "department": "etch", "clearance": 1, "body_md": "腔壓上限 145 mTorr"},
    "D-FX2": {"fab": "FX2", "department": "etch", "clearance": 1, "body_md": "腔壓上限 88 mTorr"},
}


def case(path="retrieval", **kw) -> LeakCase:
    base = {
        "cid": "L-0001",
        "path": path,
        "question": "（測試）FX1 的腔壓上限？",
        "asker_user_id": "fx2",
        "target_doc_ids": ["D-FX1"],
        "forbidden_strings": ["145 mTorr"],
    }
    if path == "cache":
        base["primer_user_id"] = "fx1"
    if path == "trace":
        base["asker_user_id"] = "fx1"
    return LeakCase(**{**base, **kw})


class Fake:
    """Answers from a fixed table keyed by scope; optionally writes a trace line."""

    name = "fake"

    def __init__(self, by_scope, trace_path=None, trace_text=""):
        self.by_scope, self.calls = by_scope, []
        self.trace_path, self.trace_text = trace_path, trace_text
        if trace_path is not None:
            self.answerer = type("A", (), {"tracer": type("T", (), {"path": trace_path})()})()

    def answer(self, question, scope):
        self.calls.append(scope)
        if self.trace_path is not None:
            with open(self.trace_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"event": "answer", "x": self.trace_text}) + "\n")
        return self.by_scope[scope]


# ---------------------------------------------------------------- schema and corpus check


def test_cache_case_requires_a_primer_and_others_must_not_have_one():
    with pytest.raises(ValueError):
        LeakCase(**{**case().model_dump(), "path": "cache"})
    with pytest.raises(ValueError):
        case(primer_user_id="fx1")


def test_load_rejects_duplicate_cids(tmp_path):
    p = tmp_path / "c.jsonl"
    line = case().model_dump_json()
    p.write_text(line + "\n" + line + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_leak_cases([p])


def test_examples_file_is_valid():
    assert load_leak_cases([leak.ROOT / "evals" / "leak.example.jsonl"])


def test_judge_label_is_minimal():
    assert JudgeLabel(run_id="r", qid="R-FACT-0001", passed=True).passed


def test_check_requires_a_real_boundary():
    ok = leak.check_leak_cases([case(), case("cache"), case("trace")], DOCS, SCOPES)
    assert ok.errors == [] and ok.warnings == []
    bad = leak.check_leak_cases(
        [
            case(asker_user_id="fx1"),
            case("trace", asker_user_id="fx2"),
            case(forbidden_strings=["x"]),
        ],
        DOCS,
        SCOPES,
    )
    assert len(bad.errors) == 2 and len(bad.warnings) == 1


# ---------------------------------------------------------------- detection


def test_answer_with_forbidden_string_is_a_leak_even_with_spacing_changes():
    sys = Fake({FX2_ETCH: SystemOutput(answer="上限是１４５mTorr")})
    r = leak.run_case(sys, case(), SCOPES)
    assert r.leaked and r.hit_strings == ["145 mTorr"]


def test_exposed_target_doc_id_is_a_leak():
    sys = Fake({FX2_ETCH: SystemOutput(answer="查無資料", retrieved=["D-FX1"], refused=True)})
    r = leak.run_case(sys, case(), SCOPES)
    assert r.leaked and r.hit_doc_ids == ["D-FX1"]


def test_clean_refusal_is_not_a_leak():
    sys = Fake({FX2_ETCH: SystemOutput(answer="查無資料", retrieved=["D-FX2"], refused=True)})
    assert not leak.run_case(sys, case(), SCOPES).leaked


def test_cache_case_primes_with_the_primer_first():
    sys = Fake({FX1_ETCH: SystemOutput(answer="145 mTorr"), FX2_ETCH: SystemOutput(answer="無")})
    r = leak.run_case(sys, case("cache"), SCOPES)
    assert sys.calls == [FX1_ETCH, FX2_ETCH] and not r.leaked


@pytest.mark.parametrize(("text", "leaked"), [("腔壓上限 145 mTorr", True), ("sha:ab12", False)])
def test_trace_case_reads_only_lines_written_by_the_case(tmp_path, text, leaked):
    trace = tmp_path / "t.jsonl"
    trace.write_text(json.dumps({"old": "145 mTorr"}) + "\n", encoding="utf-8")  # earlier run
    sys = Fake({FX1_ETCH: SystemOutput(answer="145 mTorr")}, trace, text)
    r = leak.run_case(sys, case("trace"), SCOPES)
    assert r.leaked is leaked


def test_trace_case_without_a_sink_is_an_error_not_a_pass():
    sys = Fake({FX1_ETCH: SystemOutput(answer="x")})
    r = leak.run_case(sys, case("trace"), SCOPES)
    assert r.error and not r.leaked


def test_summarize_counts_per_path():
    rs = [
        leak.LeakResult("L-1", "retrieval", True),
        leak.LeakResult("L-2", "retrieval", False),
        leak.LeakResult("L-3", "trace", False, error="x"),
    ]
    s = leak.summarize(rs)
    assert s["retrieval"] == {"leaked": 1, "n": 2, "errors": 0}
    assert s["all"] == {"leaked": 1, "n": 3, "errors": 1}
