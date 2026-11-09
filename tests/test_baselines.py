from pathlib import Path

from evals.baselines import NaiveQuestionCache, UnfilteredRetriever
from evals.schema import SystemOutput
from fabops.authz.scope import Scope
from fabops.rag.retrieve import RetrievalConfig

SRC = Path(__file__).resolve().parents[1] / "src"


def test_production_code_never_imports_the_unsafe_baselines():
    offenders = [
        p.relative_to(SRC).as_posix()
        for p in SRC.rglob("*.py")
        if "baselines" in p.read_text(encoding="utf-8")
    ]
    assert offenders == []


class Echo:
    name = "echo"

    def __init__(self):
        self.calls = []

    def answer(self, question, scope):
        self.calls.append(scope)
        return SystemOutput(answer=f"for {scope.key()}", citations=["SECRET-DOC"])


def test_naive_cache_serves_the_first_askers_output_to_anyone():
    inner = Echo()
    sys_ = NaiveQuestionCache(inner, "x-naivecache")
    insider, outsider = Scope.of(["FX1"], ["etch"], 3), Scope.of(["FX2"], ["litho"], 0)
    first = sys_.answer("同一題", insider)
    second = sys_.answer("同一題", outsider)
    assert second.answer == first.answer and second.citations == ["SECRET-DOC"]
    assert inner.calls == [insider] and sys_.hits == 1


def test_naive_cache_does_not_store_errors():
    class Failing(Echo):
        def answer(self, question, scope):
            self.calls.append(scope)
            return SystemOutput(answer="", error="boom")

    inner = Failing()
    sys_ = NaiveQuestionCache(inner, "x")
    sys_.answer("q", Scope.of(["FX1"], ["etch"], 1))
    sys_.answer("q", Scope.of(["FX1"], ["etch"], 1))
    assert len(inner.calls) == 2


def test_unfiltered_retriever_drops_the_permission_condition():
    r = UnfilteredRetriever(lambda: None, encoder=object(), config=RetrievalConfig())
    cond, params = r._where(Scope.of(["FX1"], ["etch"], 0))
    assert cond == "TRUE AND d.superseded_by IS NULL" and params == {}
