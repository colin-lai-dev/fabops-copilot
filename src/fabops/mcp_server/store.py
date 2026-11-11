"""Read-only MES data access for the agent tools, permission-filtered at the source.

Every MES table is exposed as a *view* whose rows carry the three ADR-0002 attributes
(`fab`, `department`, `clearance`; see `MES_CLEARANCE` in `authz/policy.py`). A query is
always `view + scope + equality filters`, and the scope condition is applied by the store:

- `PgMesStore` puts `sql_filter(scope)` in the WHERE clause (the same rule as `can_see`);
- `JsonlMesStore` loads `data/generated/*.jsonl` and filters with `visible()`. It backs the
  unit tests and runs without Postgres; `tests/test_mes_store_db.py` checks both agree.

There is no write method. Tools add a second, independent exit check on what they return
(`mcp_server/tools.py`).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

import psycopg

from fabops.authz.policy import MES_CLEARANCE, sql_filter, visible
from fabops.authz.scope import Scope
from fabops.data.world import SHARED_DEPARTMENT

DATA_DIR = Path("data/generated")
TIMEZONE = "Asia/Taipei"  # generated timestamps are +08:00

# view -> (SQL producing the view's rows, columns that may appear in an equality filter)
VIEWS: dict[str, tuple[str, frozenset[str]]] = {
    "lots": (
        f"SELECT l.*, '{SHARED_DEPARTMENT}'::text AS department, "
        f"{MES_CLEARANCE}::smallint AS clearance FROM lots l",
        frozenset({"lot_id"}),
    ),
    "equipment": (
        f"SELECT e.*, {MES_CLEARANCE}::smallint AS clearance FROM equipment e",
        frozenset({"equipment_id"}),
    ),
    "chambers": (
        "SELECT c.*, e.fab, e.department, "
        f"{MES_CLEARANCE}::smallint AS clearance "
        "FROM chambers c JOIN equipment e USING (equipment_id)",
        frozenset({"equipment_id", "chamber_id"}),
    ),
    **{
        t: (
            f"SELECT x.*, e.department, {MES_CLEARANCE}::smallint AS clearance "
            f"FROM {t} x JOIN equipment e USING (equipment_id)",
            frozenset({"equipment_id", "chamber_id", "lot_id"}),
        )
        for t in ("alarms", "maintenance", "dispatch_log")
    },
}
# view -> (time column, id column as tie-breaker)
ORDER_COLUMNS = {
    "alarms": ("occurred_at", "alarm_id"),
    "maintenance": ("start_at", "maintenance_id"),
    "dispatch_log": ("dispatched_at", "dispatch_id"),
}


class MesStore(Protocol):
    def select(
        self, view: str, scope: Scope, where: dict[str, str], *, newest_first: int | None = None
    ) -> list[dict[str, Any]]:
        """Rows of `view` visible to `scope` matching `where` (column = value).

        `newest_first=n` orders by the view's time column, newest first, and keeps n rows.
        """
        ...


def _check(view: str, where: dict[str, str], newest_first: int | None) -> None:
    if view not in VIEWS:
        raise ValueError(f"unknown view {view!r}")
    bad = set(where) - VIEWS[view][1]
    if bad:
        raise ValueError(f"cannot filter {view} on {sorted(bad)}")
    if newest_first is not None and view not in ORDER_COLUMNS:
        raise ValueError(f"{view} has no time column")


def _plain(v: Any) -> Any:
    return v.isoformat() if isinstance(v, datetime) else v


class PgMesStore:
    def __init__(self, connect: Callable[[], psycopg.Connection]):
        self.connect = connect

    def _scope_condition(self, scope: Scope) -> tuple[str, dict[str, Any]]:
        return sql_filter(scope, alias="v.")

    def select(
        self, view: str, scope: Scope, where: dict[str, str], *, newest_first: int | None = None
    ) -> list[dict[str, Any]]:
        _check(view, where, newest_first)
        cond, params = self._scope_condition(scope)
        for i, (col, val) in enumerate(sorted(where.items())):
            cond += f" AND v.{col} = %(w{i})s"  # col is from the VIEWS allowlist
            params[f"w{i}"] = val
        sql = f"SELECT * FROM ({VIEWS[view][0]}) v WHERE {cond}"
        if newest_first is not None:
            t, i = ORDER_COLUMNS[view]
            sql += f" ORDER BY v.{t} DESC, v.{i} DESC LIMIT %(lim)s"
            params["lim"] = newest_first
        with self.connect() as conn, conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(f"SET TIME ZONE '{TIMEZONE}'")
            cur.execute(sql, params)
            return [{k: _plain(v) for k, v in row.items()} for row in cur]


class JsonlMesStore:
    """The same views over the committed synthetic data, in memory."""

    def __init__(self, data_dir: Path = DATA_DIR):
        def read(name: str) -> list[dict[str, Any]]:
            with (data_dir / f"{name}.jsonl").open(encoding="utf-8") as f:
                return [json.loads(line) for line in f if line.strip()]

        eq = {e["equipment_id"]: e for e in read("equipment")}
        attrs = {"clearance": MES_CLEARANCE}
        self.views: dict[str, list[dict[str, Any]]] = {
            "lots": [{**r, "department": SHARED_DEPARTMENT, **attrs} for r in read("lots")],
            "equipment": [{**r, **attrs} for r in eq.values()],
            "chambers": [
                {
                    **r,
                    "fab": eq[r["equipment_id"]]["fab"],
                    "department": eq[r["equipment_id"]]["department"],
                    **attrs,
                }
                for r in read("chambers")
            ],
        }
        for t in ("alarms", "maintenance", "dispatch_log"):
            self.views[t] = [
                {
                    **{k: v for k, v in r.items() if not k.startswith("_")},
                    "department": eq[r["equipment_id"]]["department"],
                    **attrs,
                }
                for r in read(t)
            ]

    def _visible(self, scope: Scope, row: dict[str, Any]) -> bool:
        return visible(scope, row)

    def select(
        self, view: str, scope: Scope, where: dict[str, str], *, newest_first: int | None = None
    ) -> list[dict[str, Any]]:
        _check(view, where, newest_first)
        rows = [
            dict(r)
            for r in self.views[view]
            if self._visible(scope, r) and all(r.get(c) == v for c, v in where.items())
        ]
        if newest_first is not None:
            t, i = ORDER_COLUMNS[view]
            rows.sort(key=lambda r: (r[t], r[i]), reverse=True)
            rows = rows[:newest_first]
        return rows
