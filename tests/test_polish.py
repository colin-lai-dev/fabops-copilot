from fabops.data.polish import join_sections, polish_doc, split_sections, verify
from fabops.llm.client import Completion, LLMClient

ORIGINAL = "機台 FX1-ETCHER-02 的 FX1-ETCHER-02-CHB 量測值 49.1 mTorr，停機 116 分鐘。"
DOC = {
    "doc_id": "INC-2026-0001",
    "doc_type": "incident",
    "source": "template",
    "body_md": f"# 異常報告\n\n## 現象描述\n{ORIGINAL}\n\n## 根本原因\nO-ring 老化\n",
}


class Fake:
    name = "ollama"

    def __init__(self, reply):
        self.reply = reply

    def complete(self, messages, model, temperature, max_tokens):
        return Completion(self.reply, 10, 10)


def client(tmp_path, reply):
    return LLMClient(Fake(reply), "qwen3:8b", tmp_path / "c", tmp_path / "u.jsonl")


def test_verify_requires_all_ids_and_numbers():
    assert verify(ORIGINAL, "FX1-ETCHER-02-CHB（FX1-ETCHER-02）壓力 49.1 mTorr，停了 116 分鐘")
    assert not verify(ORIGINAL, "FX1-ETCHER-02-CHB 壓力 49 mTorr，停了 116 分鐘")
    assert not verify(ORIGINAL, "")


def test_sections_round_trip():
    assert join_sections(split_sections(DOC["body_md"])) == DOC["body_md"]


def test_polish_keeps_template_when_facts_drift(tmp_path):
    doc, ok = polish_doc(client(tmp_path, "壓力有點高，修好了"), DOC)
    assert not ok
    assert doc == DOC


def test_polish_replaces_only_narrative(tmp_path):
    reply = (
        "<think>...</think>巡機時看到 FX1-ETCHER-02 的 FX1-ETCHER-02-CHB "
        "壓力衝到 49.1 mTorr，前後停機 116 分鐘。"
    )
    doc, ok = polish_doc(client(tmp_path, reply), DOC)
    assert ok and doc["source"] == "polished"
    assert "巡機時看到" in doc["body_md"]
    assert "<think>" not in doc["body_md"]
    assert "## 根本原因\nO-ring 老化" in doc["body_md"]
