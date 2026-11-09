"""Data formats of the eval: questions, system outputs, run records (ADR-0005).

Question files are JSONL, one `Question` per line, under `evals/dev/` and `evals/test/`.
The asker's identity is `user_id`: the runner looks the user up and passes the scope to the
system as a separate argument. It never appears in the question text (ADR-0001).
"""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class QType(StrEnum):
    FACT = "fact"  # 單一文件中的事實
    PARAPHRASE = "paraphrase"  # 換句話說：問法和文件用詞不同
    CROSS_DOC = "cross_doc"  # 需要兩份以上文件
    DIRTY = "dirty"  # 問題本身含錯字或縮寫
    OLD_VERSION = "old_version"  # 問到有新舊版的 SOP，應以最新版回答
    REFUSE = "refuse"  # 應拒答（資料庫中沒有答案）
    OPEN = "open"  # 開放題，由 LLM judge 依 rubric 評分


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    qid: str = Field(pattern=r"^[A-Z]+-[A-Z_]+-\d{4}$|^H-\d{4}$")
    qtype: QType
    source: Literal["rule", "handwritten"]
    question: str = Field(min_length=1)
    user_id: str
    # Every key fact must appear in the answer (the scorer may accept synonyms).
    key_facts: list[str] = []
    # Documents the answer should be grounded in and cite; also the retrieval targets.
    expected_doc_ids: list[str] = []
    should_refuse: bool = False
    # Strings that must never appear in the answer for this user (e.g. restricted content).
    forbidden_facts: list[str] = []
    # Only for qtype=open: grading criteria for the judge.
    rubric: str | None = None
    notes: str = ""

    @model_validator(mode="after")
    def _consistent(self) -> Question:
        if self.qtype is QType.REFUSE and not self.should_refuse:
            raise ValueError("qtype=refuse requires should_refuse=true")
        if self.should_refuse:
            if self.key_facts:
                raise ValueError("a question that should be refused has no key facts")
        elif not self.expected_doc_ids:
            raise ValueError("an answerable question needs expected_doc_ids")
        if self.qtype is QType.OPEN and not self.rubric:
            raise ValueError("qtype=open requires a rubric")
        if self.qtype is not QType.OPEN and not self.should_refuse and not self.key_facts:
            raise ValueError("non-open answerable questions need key_facts")
        if self.qtype is QType.CROSS_DOC and len(self.expected_doc_ids) < 2:
            raise ValueError("qtype=cross_doc needs at least two expected_doc_ids")
        return self


class SystemOutput(BaseModel):
    """What a system under test returns for one question."""

    model_config = ConfigDict(extra="forbid")

    answer: str
    citations: list[str] = []  # doc ids the answer cites
    retrieved: list[str] = []  # ranked, de-duplicated doc ids (for Recall@k / MRR)
    refused: bool = False  # the system's own claim; the scorer decides independently
    latency_ms: float | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    error: str | None = None


class RunRecord(BaseModel):
    """One line of `evals/results/<run_id>.jsonl`."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    qid: str
    output: SystemOutput


def load_questions(paths: list[Path]) -> list[Question]:
    questions: list[Question] = []
    for path in paths:
        with path.open(encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    questions.append(Question.model_validate_json(line))
                except ValueError as e:
                    raise ValueError(f"{path}:{lineno}: {e}") from e
    qids = [q.qid for q in questions]
    dupes = sorted({q for q in qids if qids.count(q) > 1})
    if dupes:
        raise ValueError(f"duplicate qids: {dupes[:5]}")
    return questions


def dump_questions(questions: list[Question], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for q in questions:
            f.write(json.dumps(q.model_dump(mode="json"), ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- leak test set (rule-generated)


class LeakPath(StrEnum):
    RETRIEVAL = "retrieval"  # the asker cannot see the target and asks for it directly
    CACHE = "cache"  # a primer who can see the target asks first; then the asker asks
    TRACE = "trace"  # the asker can see the target; its content must not reach the trace log


class LeakCase(BaseModel):
    """One permission-leak test (PLAN Phase 1). Cases come from `evals/gen_leak_cases.py`.

    A case leaks when, for the retrieval and cache paths, any `forbidden_strings` appears in
    the asker's answer or any `target_doc_ids` appears in its citations or retrieved list; for
    the trace path, when any `forbidden_strings` appears in the trace lines the case wrote.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    cid: str = Field(pattern=r"^L-\d{4}$")
    path: LeakPath
    question: str = Field(min_length=1)
    asker_user_id: str
    primer_user_id: str | None = None  # required for path=cache
    target_doc_ids: list[str] = Field(min_length=1)
    forbidden_strings: list[str] = Field(min_length=1)
    notes: str = ""

    @model_validator(mode="after")
    def _consistent(self) -> LeakCase:
        if (self.path is LeakPath.CACHE) != (self.primer_user_id is not None):
            raise ValueError("primer_user_id is required for path=cache and only for it")
        if self.primer_user_id == self.asker_user_id:
            raise ValueError("primer and asker must be different users")
        return self


def load_leak_cases(paths: list[Path]) -> list[LeakCase]:
    cases = [
        LeakCase.model_validate_json(line)
        for path in paths
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    cids = [c.cid for c in cases]
    dupes = sorted({c for c in cids if cids.count(c) > 1})
    if dupes:
        raise ValueError(f"duplicate cids: {dupes[:5]}")
    return cases


# ---------------------------------------------------------------- judge calibration labels


class JudgeLabel(BaseModel):
    """One human label of a saved system answer (the 50 labels Colin writes, ADR-0005/0008).

    The judge experiment compares judge verdicts with these labels by (run_id, qid) and
    reports the agreement rate on `passed`. Minimal on purpose: Colin may add a graded score.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    qid: str
    passed: bool  # the answer meets the question's rubric / key facts (strict: 部分 = False)
    partial: bool = False  # Colin marked it 部分; counted as passed only in the lenient rate
    notes: str = ""

    @model_validator(mode="after")
    def _partial_is_not_passed(self) -> JudgeLabel:
        if self.partial and self.passed:
            raise ValueError("a partial label is not passed (ADR-0005 rule 6)")
        return self
