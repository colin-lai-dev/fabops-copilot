"""Visibility rule of ADR-0002 — the single source of truth for every data exit.

A resource (document, chunk, MES row) is visible to a scope when all three hold:

- `resource.clearance <= scope.clearance`
- `resource.fab ∈ scope.fabs`
- `resource.department ∈ scope.departments` or `resource.department == 'shared'`

The SQL form of the same rule arrives with retrieval (PLAN Phase 1) and must be tested
against `can_see` on the same user × document grid.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fabops.authz.scope import Scope
from fabops.data.world import SHARED_DEPARTMENT

# MES rows (ADR-0002, 後果) carry the same three attributes so agent tools use this rule too:
# fab from the row, department from the row's equipment (lots: shared, a lot crosses
# departments), clearance fixed at `internal`. See docs/open-questions.md (2026-11-11).
MES_CLEARANCE = 1


def can_see(scope: Scope, *, fab: str, department: str, clearance: int) -> bool:
    # Wildcards are never honoured here: SYSTEM_SCOPE (offline jobs) sees no user data.
    if scope.clearance < 0:
        return False
    return (
        int(clearance) <= scope.clearance
        and fab in scope.fabs
        and (department in scope.departments or department == SHARED_DEPARTMENT)
    )


def visible(scope: Scope, resource: Mapping[str, Any]) -> bool:
    """`can_see` for any mapping with `fab`, `department` and `clearance` keys."""
    return can_see(
        scope,
        fab=resource["fab"],
        department=resource["department"],
        clearance=resource["clearance"],
    )


def sql_filter(scope: Scope, alias: str = "") -> tuple[str, dict[str, Any]]:
    """The same rule as `can_see`, as a SQL condition with named psycopg parameters.

    Use as `WHERE {cond}` with `params`; `alias` prefixes the columns (e.g. "c.").
    Equivalence with `can_see` is tested on every demo user × document (tests/test_policy_db.py).
    """
    if scope.clearance < 0:
        return "FALSE", {}
    a = alias
    cond = (
        f"{a}clearance <= %(authz_clearance)s AND {a}fab = ANY(%(authz_fabs)s) "
        f"AND ({a}department = ANY(%(authz_departments)s) OR {a}department = %(authz_shared)s)"
    )
    return cond, {
        "authz_clearance": scope.clearance,
        "authz_fabs": list(scope.fabs),
        "authz_departments": list(scope.departments),
        "authz_shared": SHARED_DEPARTMENT,
    }


def scope_of_user(user: Mapping[str, Any]) -> Scope:
    """Scope for a user row (`users` table / `users.jsonl`). Server-side only (ADR-0001)."""
    return Scope.of(user["fabs"], user["departments"], user["clearance"])
