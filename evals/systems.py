"""Systems under test. A system answers one question for one already-resolved scope.

The scope is injected by the runner from the question's `user_id` (ADR-0001); a system must
never read identity from the question text.

Select with `--system NAME` (registered below) or `--system package.module:factory`, where
the factory takes no arguments and returns an object with `name` and `answer()`.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Protocol

from evals.schema import SystemOutput
from fabops.authz.scope import Scope


class System(Protocol):
    name: str

    def answer(self, question: str, scope: Scope) -> SystemOutput: ...


class RefuseAll:
    """Floor baseline: always refuses. Checks the harness and anchors refusal metrics."""

    name = "refuse_all"

    def answer(self, question: str, scope: Scope) -> SystemOutput:
        return SystemOutput(answer="查無可用資料，無法回答。", refused=True, latency_ms=0.0)


REGISTRY: dict[str, Callable[[], System]] = {"refuse_all": RefuseAll}


def load_system(spec: str) -> System:
    if spec in REGISTRY:
        return REGISTRY[spec]()
    module, sep, attr = spec.partition(":")
    if not sep:
        raise ValueError(f"unknown system {spec!r}; registered: {sorted(REGISTRY)}")
    return getattr(importlib.import_module(module), attr)()
