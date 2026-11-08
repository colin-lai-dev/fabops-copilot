"""The SQL filter and the pure function must agree on every user × row (ADR-0002)."""

import itertools

import psycopg
import pytest

from fabops.authz.policy import scope_of_user, sql_filter, visible
from fabops.authz.scope import SYSTEM_SCOPE, Scope
from fabops.config import get_settings

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def conn():
    with psycopg.connect(get_settings().database_url) as c:
        yield c


def _rows(conn, table, key):
    with conn.cursor() as cur:
        cur.execute(f"SELECT {key}, fab, department, clearance FROM {table}")
        return [dict(zip((key, "fab", "department", "clearance"), r, strict=True)) for r in cur]


def _sql_visible(conn, table, key, scope):
    cond, params = sql_filter(scope)
    with conn.cursor() as cur:
        cur.execute(f"SELECT {key} FROM {table} WHERE {cond}", params)
        return {r[0] for r in cur}


def _scopes(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT user_id, fabs, departments, clearance FROM users")
        users = [
            dict(zip(("user_id", "fabs", "departments", "clearance"), r, strict=True)) for r in cur
        ]
    synthetic = [  # extra combinations beyond the demo users, including 'shared' and empties
        Scope.of(f, d, c)
        for f, d, c in itertools.product(
            [["FX1"], ["FX2"], ["FX1", "FX2"], []], [["etch"], ["cmp", "litho"], []], [0, 1, 2, 3]
        )
    ]
    return [scope_of_user(u) for u in users] + synthetic + [SYSTEM_SCOPE]


@pytest.mark.parametrize(("table", "key"), [("documents", "doc_id"), ("chunks", "chunk_id")])
def test_sql_filter_matches_can_see(conn, table, key):
    rows = _rows(conn, table, key)
    if not rows:
        pytest.skip(f"{table} is empty (run the index build first)")
    for scope in _scopes(conn):
        expected = {r[key] for r in rows if visible(scope, r)}
        assert _sql_visible(conn, table, key, scope) == expected, scope
