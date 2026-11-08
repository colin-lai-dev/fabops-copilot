import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from fabops.config import get_settings
from fabops.data import seed


@pytest.fixture(scope="module")
def test_db_url():
    """A separate `<db>_test` database: seeding drops every table, including the built
    retrieval index, so it must never run against the development database."""
    url = get_settings().database_url
    name = conninfo_to_dict(url)["dbname"] + "_test"
    with psycopg.connect(url, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", [name]).fetchone()
        if not exists:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    return make_conninfo(url, dbname=name)


@pytest.mark.db
def test_seed_loads_all_tables(test_db_url):
    counts = seed.seed(test_db_url)
    assert counts["documents"] > 150
    assert counts["dispatch_log"] > 1000

    with psycopg.connect(test_db_url) as conn:
        superseded = conn.execute(
            "SELECT count(*) FROM documents WHERE superseded_by IS NOT NULL"
        ).fetchone()[0]
        assert superseded == 8
        # Business rule holds in the DB too.
        bad = conn.execute(
            """
            SELECT count(*) FROM dispatch_log d JOIN maintenance m
              ON m.chamber_id = d.chamber_id
             AND d.dispatched_at >= m.start_at AND d.dispatched_at < m.end_at
            WHERE d.result = 'ok'
            """
        ).fetchone()[0]
        assert bad == 0


@pytest.mark.db
def test_seed_test_does_not_touch_the_dev_database(test_db_url):
    assert (
        conninfo_to_dict(test_db_url)["dbname"]
        != conninfo_to_dict(get_settings().database_url)["dbname"]
    )
