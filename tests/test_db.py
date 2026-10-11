"""Tests for pipeline.db safeguards. Run: python -m pytest tests/"""

from pipeline.db import REMOVAL_REFUSED, get_connection, mark_removed, upsert_job


def _db(tmp_path, n):
    conn = get_connection(str(tmp_path / "t.db"))
    for i in range(n):
        upsert_job(conn, {"url": f"https://x/{i}", "title": "RN", "company": "c"})
    conn.commit()
    return conn


def live(conn):
    return conn.execute("SELECT COUNT(*) FROM jobs WHERE removed_at IS NULL").fetchone()[0]


def test_mark_removed_normal_churn(tmp_path):
    conn = _db(tmp_path, 10)
    assert mark_removed(conn, {f"https://x/{i}" for i in range(8)}) == 2
    assert live(conn) == 8


def test_mark_removed_refuses_mass_removal(tmp_path):
    conn = _db(tmp_path, 10)
    # A source that returned nothing looks like every job closing at once.
    assert mark_removed(conn, {"https://x/0"}) == REMOVAL_REFUSED
    assert live(conn) == 10


def test_upsert_stamps_last_seen(tmp_path):
    conn = _db(tmp_path, 1)
    row = conn.execute("SELECT last_seen_at FROM jobs").fetchone()
    assert row["last_seen_at"]
