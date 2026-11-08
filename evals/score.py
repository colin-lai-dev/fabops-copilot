"""Scoring logic (ADR-0005). **[Colin] 親手撰寫** — everything below is an interface stub.

`evals/run.py` calls `score_question` for every record and `aggregate` once per run; until
these are implemented the runner still saves raw outputs and skips the metrics.
`tests/test_score.py` holds the expected behaviour as xfail tests: once a function is
implemented its tests must pass (a wrong result fails; only NotImplementedError is tolerated).

Signatures and the `QuestionScore` fields are a starting point; change them freely and
adjust `run.py` / the tests to match.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel

from evals.schema import Question, SystemOutput


class QuestionScore(BaseModel):
    qid: str
    qtype: str
    facts_found: int | None = None  # key facts present in the answer
    facts_total: int | None = None
    refusal_ok: bool | None = None  # refused iff should_refuse
    leaked: bool | None = None  # any forbidden fact in the answer
    citation_ok: bool | None = None
    recall_at_5: float | None = None
    reciprocal_rank: float | None = None
    judge_score: float | None = None  # open questions only, filled by the judge step


def contains_fact(answer: str, fact: str, synonyms: Mapping[str, Sequence[str]]) -> bool:
    """Whether `answer` states `fact`, allowing the synonym/abbreviation table."""
    raise NotImplementedError


def is_refusal(output: SystemOutput) -> bool:
    """Whether the system declined to answer."""
    raise NotImplementedError


def recall_at_k(retrieved: Sequence[str], expected: Sequence[str], k: int = 5) -> float:
    raise NotImplementedError


def reciprocal_rank(retrieved: Sequence[str], expected: Sequence[str]) -> float:
    raise NotImplementedError


def score_question(
    q: Question, output: SystemOutput, synonyms: Mapping[str, Sequence[str]]
) -> QuestionScore:
    raise NotImplementedError


def aggregate(scores: Sequence[QuestionScore]) -> dict[str, Any]:
    """Run-level metrics, overall and per qtype. Every number must carry its n."""
    raise NotImplementedError
