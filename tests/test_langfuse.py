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


def test_payload_is_exactly_the_masked_record(tmp_path):
    sent, client = capture()
    exp = LangfuseExporter("https://lf.example", "pk", "sk", client=client, batch=1)
    tracer = Tracer(tmp_path / "t.jsonl", exporter=exp)
    record = tracer.event(
        "answer", texts={"answer": SECRET_TEXT, "query": "壓力怎麼處理"}, scope="abc",
        doc_ids=["SOP-1"], thread_id="th1", user_id="eng_fx1_etch", body=SECRET_TEXT,
    )  # fmt: skip
    assert len(sent) == 1 and sent[0]["url"] == "https://lf.example/api/public/ingestion"
    event = sent[0]["body"]["batch"][0]
    assert event["type"] == "event-create" and event["body"]["traceId"] == "th1"
    assert event["body"]["metadata"] == record  # nothing beyond the masked record
    raw = json.dumps(sent, ensure_ascii=False)
    for text in (SECRET_TEXT, "壓力怎麼處理", "eng_fx1_etch", "+9%"):
        assert text not in raw
    assert "dropped_fields" in event["body"]["metadata"]  # user_id/body were dropped, visibly


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
