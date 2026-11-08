"""Check questions against the corpus and the permission policy before they are split.

Errors (the question is unusable): unknown user, unknown document, or an answerable
question whose asker cannot see an expected document (that would be a leak test, which
belongs in the leakage set, not the QA set).
Warnings: a key fact that does not appear literally (ignoring whitespace) in any expected
document — fine for hand-written facts phrased differently, suspicious for rule questions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evals.schema import Question
from fabops.authz.policy import visible
from fabops.authz.scope import Scope
from fabops.data.seed import read_jsonl

DOCS = Path(__file__).resolve().parents[1] / "data" / "generated" / "documents.jsonl"
_WS = re.compile(r"\s+")


def load_corpus(path: Path = DOCS) -> dict[str, dict[str, Any]]:
    return {d["doc_id"]: d for d in read_jsonl(path)}


def _norm(text: str) -> str:
    return _WS.sub("", text)


@dataclass
class CheckResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def check_questions(
    questions: list[Question], docs: dict[str, dict[str, Any]], scopes: dict[str, Scope]
) -> CheckResult:
    res = CheckResult()
    for q in questions:
        scope = scopes.get(q.user_id)
        if scope is None:
            res.errors.append(f"{q.qid}: unknown user_id {q.user_id!r}")
            continue
        missing = [d for d in q.expected_doc_ids if d not in docs]
        if missing:
            res.errors.append(f"{q.qid}: unknown doc ids {missing}")
            continue
        if not q.should_refuse:
            hidden = [d for d in q.expected_doc_ids if not visible(scope, docs[d])]
            if hidden:
                res.errors.append(f"{q.qid}: {q.user_id} cannot see {hidden}")
        bodies = [_norm(docs[d]["body_md"]) for d in q.expected_doc_ids]
        for fact in q.key_facts:
            if not any(_norm(fact) in b for b in bodies):
                res.warnings.append(f"{q.qid}: key fact {fact!r} not found literally")
    return res
