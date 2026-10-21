"""Store connectivity on the lightweight path — SQLite, embedded Qdrant, Alembic."""

from __future__ import annotations

import sqlalchemy as sa
from alembic.config import Config

from alembic import command
from atlas.store import db, vector


def test_sqlite_ping(fresh_db: None):
    assert db.ping() is True


def test_expected_tables_exist(fresh_db: None):
    names = set(sa.inspect(db.get_engine()).get_table_names())
    assert {"runs", "papers", "frontier", "claims", "llm_cache", "costs", "events"} <= names


def test_alembic_upgrade_then_downgrade_roundtrips(tmp_path, monkeypatch):
    dsn = f"sqlite+pysqlite:///{(tmp_path / 'mig.db').as_posix()}"
    # alembic/env.py builds Settings() fresh, so it reads this straight from the env.
    monkeypatch.setenv("POSTGRES_DSN", dsn)
    engine = sa.create_engine(dsn, future=True)

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    assert "papers" in sa.inspect(engine).get_table_names()

    command.downgrade(cfg, "base")
    remaining = set(sa.inspect(engine).get_table_names())
    assert "papers" not in remaining and "frontier" not in remaining
    engine.dispose()


def test_qdrant_embedded_ping_and_collection_creation():
    client = vector.get_client()
    assert vector.ping(client) is True
    created = vector.ensure_collections(client)
    assert set(created) == set(vector.COLLECTIONS)
    # idempotent — a second call creates nothing
    assert vector.ensure_collections(client) == []


def test_embedded_qdrant_is_one_shared_client_safe_across_threads(tmp_path, monkeypatch):
    """Embedded Qdrant locks its folder. A fresh client per call made two overlapping API
    requests collide on that lock (a 500 in the live dashboard, 2026-09-29); now every
    caller in the process shares one client, close() is a no-op for it, and concurrent
    calls are serialized."""
    from concurrent.futures import ThreadPoolExecutor

    from atlas.store import vector

    monkeypatch.setattr(vector.settings, "qdrant_url", str(tmp_path / "qdrant"))
    monkeypatch.setattr(vector, "_local_clients", {})
    a, b = vector.get_client(), vector.get_client()
    assert a is b
    vector.ensure_collections(a)
    a.close()  # what every caller does when finished — must not close the shared client

    def list_collections(_: int) -> int:
        return len(vector.get_client().get_collections().collections)

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert set(pool.map(list_collections, range(16))) == {len(vector.COLLECTIONS)}
    vector._close_local_clients()
