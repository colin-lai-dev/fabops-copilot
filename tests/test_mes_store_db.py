"""PgMesStore (SQL filter) and JsonlMesStore (`visible()`) return the same rows (ADR-0002)."""

from __future__ import annotations

import psycopg
import pytest

from fabops.authz.policy import scope_of_user
from fabops.authz.scope import SYSTEM_SCOPE, Scope
from fabops.config import get_settings
from fabops.data.world import DEMO_USERS
from fabops.mcp_server.store import ORDER_COLUMNS, JsonlMesStore, PgMesStore

pytestmark = pytest.mark.db

SCOPES = [
    *(scope_of_user({"fabs": f, "departments": d, "clearance": c}) for _, _, f, d, c in DEMO_USERS),
    Scope.of(["FX2"], ["cmp"], 1),
    Scope.of(["FX1"], ["etch"], 0),
    SYSTEM_SCOPE,
]
QUERIES = [
    ("lots", {"lot_id": "FX1L00003"}),
    ("lots", {"lot_id": "FX2L00010"}),
    ("equipment", {"equipment_id": "FX1-ETCHER-01"}),
    ("equipment", {"equipment_id": "FX2-SCANNER-02"}),
    ("chambers", {"equipment_id": "FX1-CVD-02"}),
    ("alarms", {"equipment_id": "FX1-ETCHER-03"}),
    ("maintenance", {"equipment_id": "FX2-POLISHER-01"}),
    ("dispatch_log", {"lot_id": "FX1L00013"}),
]


@pytest.fixture(scope="module")
def stores():
    url = get_settings().database_url
    return PgMesStore(lambda: psycopg.connect(url)), JsonlMesStore()


def _key(view):
    return {
        "lots": "lot_id",
        "equipment": "equipment_id",
        "chambers": "chamber_id",
        **{v: id_col for v, (_, id_col) in ORDER_COLUMNS.items()},
    }[view]


@pytest.mark.parametrize(("view", "where"), QUERIES)
def test_pg_and_jsonl_agree(stores, view, where):
    pg, js = stores
    k = _key(view)
    for scope in SCOPES:
        assert {r[k] for r in pg.select(view, scope, where)} == {
            r[k] for r in js.select(view, scope, where)
        }, (view, where, scope)


@pytest.mark.parametrize("view", list(ORDER_COLUMNS))
def test_newest_first_agrees(stores, view):
    pg, js = stores
    admin = SCOPES[-4]  # admin_all
    where = {"equipment_id": "FX1-ETCHER-02"}
    a = pg.select(view, admin, where, newest_first=7)
    b = js.select(view, admin, where, newest_first=7)
    k = _key(view)
    assert [r[k] for r in a] == [r[k] for r in b]
    t = ORDER_COLUMNS[view][0]
    assert [r[t] for r in a] == [r[t] for r in b]  # same ISO strings (+08:00)
