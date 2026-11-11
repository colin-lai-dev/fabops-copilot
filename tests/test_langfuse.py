"""Langfuse export (ADR-0007): only masked fields leave the process; off by default."""

import json

import httpx

from fabops.authz.langfuse import LangfuseExporter, exporter_from_settings
from fabops.authz.trace import Tracer

SECRET_TEXT = "腔體壓力 45 mTorr 的受限補償值 +9%"


def capture():
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append({"url": str(request.url), "auth": request.headers.get("authorization"),
                     "body": json.loads(request.content)})  # fmt: skip
        return httpx.Response(207, json={"successes": [], "errors": []})

    return sent, httpx.Client(transport=httpx.MockTransport(handler))


def attrs(span):
    out = {}
    for a in span["attributes"]:
        v = a["value"]
        out[a["key"].removeprefix("fabops.")] = (
            int(v["intValue"]) if "intValue" in v else next(iter(v.values()))
        )
    return out


def test_payload_is_exactly_the_masked_record(tmp_path):
    sent, client = capture()
    exp = LangfuseExporter("https://lf.example", "pk", "sk", client=client, batch=1)
    tracer = Tracer(tmp_path / "t.jsonl", exporter=exp)
    record = tracer.event(
        "answer", texts={"answer": SECRET_TEXT, "query": "壓力怎麼處理"}, scope="abc",
        doc_ids=["SOP-1"], thread_id="th1", user_id="eng_fx1_etch", body=SECRET_TEXT,
    )  # fmt: skip
    assert len(sent) == 1 and sent[0]["url"] == "https://lf.example/api/public/otel/v1/traces"
    span = sent[0]["body"]["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    assert span["name"] == "answer" and len(span["traceId"]) == 32
    got = attrs(span)
    assert set(got) == set(record)  # nothing beyond the masked record
    assert json.loads(got["doc_ids"]) == ["SOP-1"] and got["scope"] == "abc"
    raw = json.dumps(sent, ensure_ascii=False)
    for text in (SECRET_TEXT, "壓力怎麼處理", "eng_fx1_etch", "+9%"):
        assert text not in raw
    assert "dropped_fields" in got  # user_id/body were dropped, visibly


def test_events_of_one_run_share_a_trace():
    a = LangfuseExporter.to_span({"event": "tool", "thread_id": "t1"})
    b = LangfuseExporter.to_span({"event": "agent_done", "thread_id": "t1"})
    c = LangfuseExporter.to_span({"event": "tool", "thread_id": "t2"})
    assert a["traceId"] == b["traceId"] != c["traceId"]


def test_http_errors_count_as_failures(tmp_path):
    def reject(request):
        return httpx.Response(400, json={"error": "bad"})

    client = httpx.Client(transport=httpx.MockTransport(reject))
    exp = LangfuseExporter("https://lf.example", "pk", "sk", client=client, batch=1)
    Tracer(tmp_path / "t.jsonl", exporter=exp).event("x")
    assert (exp.sent, exp.failures) == (0, 1)


def test_unsafe_tracer_never_exports(tmp_path):
    sent, client = capture()
    exp = LangfuseExporter("https://lf.example", "pk", "sk", client=client, batch=1)
    Tracer(tmp_path / "u.jsonl", unsafe_unmasked=True, exporter=exp).event("x", texts={"a": "b"})
    assert sent == []


def test_failures_do_not_raise(tmp_path):
    def boom(request):
        raise httpx.ConnectError("down")

    exp = LangfuseExporter(
        "https://lf.example", "pk", "sk", client=httpx.Client(transport=httpx.MockTransport(boom)),
        batch=1,
    )  # fmt: skip
    Tracer(tmp_path / "t.jsonl", exporter=exp).event("x")
    assert exp.failures == 1


def test_switch_and_keys_are_both_required(monkeypatch):
    from fabops.config import get_settings

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    for switch, expected in (("0", False), ("1", True)):
        monkeypatch.setenv("FABOPS_LANGFUSE", switch)
        get_settings.cache_clear()
        assert (exporter_from_settings() is not None) is expected
    monkeypatch.setenv("FABOPS_LANGFUSE", "1")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")
    get_settings.cache_clear()
    assert exporter_from_settings() is None
    get_settings.cache_clear()
