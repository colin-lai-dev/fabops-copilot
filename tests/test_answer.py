import json

from fabops.authz.scope import Scope
from fabops.authz.trace import Tracer
from fabops.llm.client import Completion, LLMClient
from fabops.rag.answer import REFUSAL_TEXT, Answerer
from fabops.rag.retrieve import Hit, Retrieval

ENG = Scope.of(["FX1"], ["etch"], 1)
OP = Scope.of(["FX1"], ["etch"], 0)
SECRET = "限授權人員：補償值 +9%"


def hit(doc_id="SOP-A-v2", text="等待 5 分鐘後重新量測", **kw):
    base = {"fab": "FX1", "department": "etch", "clearance": 1, "score": 1.0}
    return Hit(f"{doc_id}#00", doc_id, text, **{**base, **kw})


class FakeRetriever:
    def __init__(self, hits):
        self.hits = hits

    def search(self, query, scope):
        return Retrieval(list(self.hits), {"encode": 1.0})


class FakeProvider:
    name = "ollama"

    def __init__(self, replies):
        self.replies, self.messages = list(replies), []

    def complete(self, messages, model, temperature, max_tokens):
        self.messages.append(messages)
        return Completion(self.replies.pop(0), 100, 20)


def make(tmp_path, hits, replies, **kw):
    provider = FakeProvider([json.dumps(r, ensure_ascii=False) for r in replies])
    client = LLMClient(
        provider,
        "qwen3:8b",
        tmp_path / "cache",
        tmp_path / "usage.jsonl",
        **{k: kw.pop(k) for k in list(kw) if k.startswith("unsafe")},
    )
    tracer = Tracer(tmp_path / "traces.jsonl", unsafe_unmasked=not kw.get("exit_checks", True))
    return Answerer(FakeRetriever(hits), client, tracer, **kw), provider


def test_no_hits_refuses_without_calling_the_llm(tmp_path):
    a, provider = make(tmp_path, [], [])
    out = a.answer("FX3 的上限？", ENG)
    assert out.refused and out.text == REFUSAL_TEXT and provider.messages == []


def test_grounded_answer_with_citation(tmp_path):
    a, provider = make(tmp_path, [hit()], [{"answer": "5 分鐘", "citations": ["SOP-A-v2"]}])
    out = a.answer("等多久？", ENG)
    assert (out.text, out.citations, out.refused) == ("5 分鐘", ["SOP-A-v2"], False)
    prompt = provider.messages[0][-1]["content"]
    assert '<文件 doc_id="SOP-A-v2">' in prompt and "問題：等多久？" in prompt


def test_citations_outside_the_retrieved_and_visible_set_are_dropped(tmp_path):
    hits = [hit(), hit("SOP-B-v1", clearance=2)]  # second is above ENG's clearance
    reply = {"answer": "x", "citations": ["SOP-A-v2", "SOP-B-v1", "SOP-INVENTED-v9"]}
    a, _ = make(tmp_path, hits, [reply])
    out = a.answer("q", ENG)
    assert out.citations == ["SOP-A-v2"]
    assert out.dropped_citations == ["SOP-B-v1", "SOP-INVENTED-v9"]


def test_model_refusal_clears_citations(tmp_path):
    a, _ = make(tmp_path, [hit()], [{"answer": "", "citations": ["SOP-A-v2"], "refused": True}])
    out = a.answer("q", ENG)
    assert out.refused and out.citations == [] and out.text == REFUSAL_TEXT


def test_invalid_json_twice_becomes_a_refusal_with_error(tmp_path):
    provider = FakeProvider(["nope", "still nope"])
    client = LLMClient(provider, "m", tmp_path / "c", tmp_path / "u.jsonl")
    a = Answerer(FakeRetriever([hit()]), client, Tracer(tmp_path / "t.jsonl"))
    out = a.answer("q", ENG)
    assert out.refused and out.error


def test_trace_carries_no_content(tmp_path):
    a, _ = make(tmp_path, [hit(text=SECRET)], [{"answer": SECRET, "citations": ["SOP-A-v2"]}])
    a.answer("補償值是多少？", ENG)
    raw = (tmp_path / "traces.jsonl").read_text(encoding="utf-8")
    assert SECRET not in raw and "補償值是多少" not in raw and "SOP-A-v2" in raw


def test_cache_does_not_cross_scopes(tmp_path):
    """Same question and context for two scopes: the second must not get a cached answer."""
    r = [{"answer": "a1", "citations": []}, {"answer": "a2", "citations": []}]
    a, provider = make(tmp_path, [hit(clearance=0)], r)
    assert a.answer("q", ENG).text == "a1"
    assert a.answer("q", OP).text == "a2"
    assert len(provider.messages) == 2


def test_no_exit_checks_baseline_leaks_by_design(tmp_path):
    """The baseline exists to measure leaks: shared cache, unfiltered citations, raw trace."""
    r = [{"answer": SECRET, "citations": ["SOP-B-v1"]}]
    a, provider = make(
        tmp_path,
        [hit("SOP-B-v1", text=SECRET, clearance=0)],
        r,
        exit_checks=False,
        unsafe_share_cache_across_scopes=True,
    )
    a.answer("q", ENG)
    leaked = a.answer("q", OP)
    assert leaked.text == SECRET and len(provider.messages) == 1  # served from shared cache
    assert SECRET in (tmp_path / "traces.jsonl").read_text(encoding="utf-8")
