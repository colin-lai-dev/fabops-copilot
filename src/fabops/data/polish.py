"""Polish stage of ADR-0004: rewrite narrative prose with a local LLM, then verify facts.

Only free-text sections are rewritten (incident "現象描述" / "處理經過", SOP "目的").
Tables, steps and thresholds are never sent for rewriting. If any ID or number from the
original section is missing after rewriting, the template version is kept.

Run (needs Ollama): `python -m fabops.data.polish`
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from fabops.authz.scope import SYSTEM_SCOPE
from fabops.data.seed import read_jsonl
from fabops.llm.client import LLMClient

DATA_DIR = Path("data/generated")
POLISH_SECTIONS = {"incident": ["現象描述", "處理經過"], "sop": ["1. 目的"]}
PROMPT = (
    "你是晶圓廠的資深工程師。請把下面這段文字改寫成自然、口語的工作紀錄，"
    "可以調整語序與用詞，但所有編號、代碼、數字與單位必須原樣保留，不可新增事實。"
    "只輸出改寫後的段落。\n\n{text}"
)
_TOKENS = re.compile(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+|\d+(?:\.\d+)?")


def protected_tokens(text: str) -> set[str]:
    """IDs, codes and numbers that must survive rewriting."""
    return set(_TOKENS.findall(text))


def verify(original: str, polished: str) -> bool:
    return bool(polished.strip()) and protected_tokens(original) <= protected_tokens(polished)


def split_sections(body: str) -> list[tuple[str, str]]:
    """Split markdown into (heading, content) pairs; heading '' for the preamble."""
    parts, heading, buf = [], "", []
    for line in body.split("\n"):
        if line.startswith("## "):
            parts.append((heading, "\n".join(buf)))
            heading, buf = line[3:].strip(), []
        else:
            buf.append(line)
    parts.append((heading, "\n".join(buf)))
    return parts


def join_sections(parts: list[tuple[str, str]]) -> str:
    out = []
    for heading, content in parts:
        out.append(f"## {heading}\n{content}" if heading else content)
    return "\n".join(out)


def polish_doc(client: LLMClient, doc: dict) -> tuple[dict, bool]:
    targets = POLISH_SECTIONS[doc["doc_type"]]
    parts = split_sections(doc["body_md"])
    changed, ok = False, True
    for i, (heading, content) in enumerate(parts):
        if heading not in targets:
            continue
        text = content.strip()
        r = client.chat(
            [{"role": "user", "content": PROMPT.format(text=text)}],
            SYSTEM_SCOPE,
            temperature=0.7,
            max_tokens=600,
            purpose="polish",
        )
        polished = re.sub(r"<think>.*?</think>", "", r.text, flags=re.S).strip()
        if verify(text, polished):
            parts[i] = (heading, f"{polished}\n")
            changed = True
        else:
            ok = False
    if changed and ok:
        return {**doc, "body_md": join_sections(parts), "source": "polished"}, True
    return doc, False


def main(data_dir: Path = DATA_DIR) -> None:
    client = LLMClient.from_env()
    docs = read_jsonl(data_dir / "documents.jsonl")
    out, passed = [], 0
    for doc in docs:
        new, ok = polish_doc(client, doc)
        out.append(new)
        passed += ok
    with (data_dir / "documents.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for d in out:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"polished {passed}/{len(docs)}; the rest kept their template text")


if __name__ == "__main__":
    main()
