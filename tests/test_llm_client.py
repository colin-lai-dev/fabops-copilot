import json

import pytest

from fabops.authz.scope import Scope
from fabops.llm.client import Completion, LLMClient, extract_json
from fabops.llm.examples import AlarmEvent, parse_alarm


class FakeProvider:
    def __init__(self, name="anthropic", replies=None):
        self.name = name
        self.replies = list(replies or ["hello"])
        self.calls = 0

    def complete(self, messages, model, temperature, max_tokens):
        self.calls += 1
        return Completion(self.replies.pop(0), 1000, 200)


@pytest.fixture
def make_client(tmp_path):
    def _make(provider, model="claude-haiku-5-5"):
        return LLMClient(provider, model, tmp_path / "cache", tmp_path / "usage.jsonl")

    return _make


LOW = Scope.of(["FX1"], ["etch"], 0)
HIGH = Scope.of(["FX1"], ["etch"], 3)
MSG = [{"role": "user", "content": "q"}]


def test_cache_hit_within_same_scope(make_client):
    p = FakeProvider(replies=["a"])
    c = make_client(p)
    first, second = c.chat(MSG, LOW), c.chat(MSG, LOW)
    assert (first.cached, second.cached) == (False, True)
    assert second.text == "a"
    assert p.calls == 1


def test_cache_never_shared_across_scopes(make_client):
    p = FakeProvider(replies=["secret answer", "public answer"])
    c = make_client(p)
    c.chat(MSG, HIGH)
    low = c.chat(MSG, LOW)
    assert low.cached is False
    assert low.text == "public answer"
    assert p.calls == 2


def test_scope_key_ignores_order_and_duplicates():
    a = Scope.of(["FX2", "FX1"], ["cmp", "etch", "etch"], 2)
    b = Scope.of(["FX1", "FX2"], ["etch", "cmp"], 2)
    assert a.key() == b.key()


def test_usage_log_has_cost_and_no_text(make_client, tmp_path):
    c = make_client(FakeProvider(replies=["機密內容"]))
    c.chat(MSG, LOW)
    rows = [json.loads(x) for x in (tmp_path / "usage.jsonl").read_text().splitlines()]
    assert rows[0]["cost_usd"] == pytest.approx((1000 * 0.10 + 200 * 0.50) / 1e6)
    assert "機密內容" not in (tmp_path / "usage.jsonl").read_text(encoding="utf-8")


def test_local_provider_is_free(make_client):
    r = make_client(FakeProvider(name="ollama"), model="qwen3:8b").chat(MSG, LOW)
    assert r.cost_usd == 0.0


def test_extract_json_handles_fences_and_think():
    assert extract_json('<think>{"x": 0}</think>```json\n{"a": 1}\n```') == '{"a": 1}'
    assert json.loads(extract_json('結果如下 {"a": {"b": 2}} 謝謝')) == {"a": {"b": 2}}
    with pytest.raises(ValueError):
        extract_json("no json")


def test_structured_output_repairs_once(make_client):
    good = {
        "equipment_id": "FX1-ETCHER-02",
        "chamber_id": "FX1-ETCHER-02-CHB",
        "alarm_code": "ETC-PRS-0412",
        "parameter": "chamber pressure",
        "value": 52.3,
        "unit": "mTorr",
        "limit": 45,
    }
    p = FakeProvider(replies=['{"equipment_id": "FX1"}', json.dumps(good)])
    event = parse_alarm(make_client(p), "FX1-ETCHER-02-CHB ...")
    assert isinstance(event, AlarmEvent)
    assert event.value == 52.3
    assert p.calls == 2


def test_structured_output_gives_up_after_retry(make_client):
    p = FakeProvider(replies=["nope", "still nope"])
    with pytest.raises(ValueError):
        parse_alarm(make_client(p), "x")


def test_cache_entry_is_only_served_to_its_own_scope(make_client, tmp_path):
    """Exit check: even a planted/copied entry under the LOW key is refused if it says HIGH."""
    p = FakeProvider(replies=["secret", "fresh"])
    c = make_client(p)
    c.chat(MSG, HIGH)
    high_file = next((tmp_path / "cache").glob("*.json"))
    low_key = c.cache_key(MSG, LOW, 0.0, 1024)
    (tmp_path / "cache" / f"{low_key}.json").write_text(
        high_file.read_text(encoding="utf-8"), encoding="utf-8"
    )
    r = c.chat(MSG, LOW)
    assert (r.text, r.cached, p.calls) == ("fresh", False, 2)


def test_reasoning_effort_is_part_of_the_cache_key(make_client):
    p = FakeProvider(name="ollama")
    c = make_client(p, model="qwen3:8b")
    before = c.cache_key(MSG, LOW, 0.0, 10)
    p.reasoning_effort = "none"
    assert c.cache_key(MSG, LOW, 0.0, 10) != before


def test_anthropic_request_has_no_sampling_params_and_maps_no_think():
    from fabops.llm.client import AnthropicProvider

    p = AnthropicProvider(api_key="test-not-a-key", reasoning_effort="none")
    kw = p.request_kwargs(
        [{"role": "system", "content": "S"}, {"role": "user", "content": "Q"}], "m", 64
    )
    assert kw == {
        "model": "m",
        "messages": [{"role": "user", "content": "Q"}],
        "max_tokens": 64,
        "system": "S",
        "thinking": {"type": "disabled"},
    }
    default = AnthropicProvider(api_key="test-not-a-key").request_kwargs(
        [{"role": "user", "content": "Q"}], "m", 64
    )
    assert "thinking" not in default and "temperature" not in default
