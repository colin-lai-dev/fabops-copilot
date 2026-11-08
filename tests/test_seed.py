import pytest

from fabops.config import get_settings
from fabops.data import seed


@pytest.mark.db
def test_seed_loads_all_tables():
    url = get_settings().database_url
    counts = seed.seed(url)
    assert counts["documents"] > 150
    assert counts["dispatch_log"] > 1000

    import psycopg

    with psycopg.connect(url) as conn:
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
