"""Permission scope of a request (ADR-0002).

The full policy (`policy.py`) arrives in Phase 1. Phase 0 only needs a stable, hashable
description of what a user may see, so that caches never mix results across scopes.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class Scope:
    fabs: tuple[str, ...]
    departments: tuple[str, ...]
    clearance: int

    @classmethod
    def of(cls, fabs, departments, clearance: int) -> Scope:
        return cls(tuple(sorted(set(fabs))), tuple(sorted(set(departments))), int(clearance))

    def key(self) -> str:
        """Stable identifier used in cache keys and (hashed) in logs."""
        raw = f"f={','.join(self.fabs)};d={','.join(self.departments)};c={self.clearance}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


# Scope for work that touches no user data (e.g. polishing synthetic documents offline).
SYSTEM_SCOPE = Scope(fabs=("*",), departments=("*",), clearance=-1)
