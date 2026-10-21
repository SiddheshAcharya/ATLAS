"""Unit-test isolation: every test runs against a throwaway SQLite file and an
in-memory Qdrant, never the real ``./data`` stores or a live Neo4j.

Env vars are set at import time — before ``atlas.config`` is first imported — so the
settings singleton picks them up.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="atlas-unit-"))
# Opt-in dialect check: ATLAS_TEST_POSTGRES_DSN=postgresql+psycopg://.../atlas_test runs the
# DB-touching tests on real Postgres. `fresh_db` drops every table, so point it at a
# throwaway database, never the one holding real runs.
os.environ["POSTGRES_DSN"] = os.environ.get("ATLAS_TEST_POSTGRES_DSN") or (
    f"sqlite+pysqlite:///{(_TMP / 'test.db').as_posix()}"
)
os.environ["QDRANT_URL"] = ":memory:"
os.environ["ATLAS_DATA_DIR"] = str(_TMP)
os.environ["ATLAS_CONTACT_EMAIL"] = "test@example.edu"
os.environ["ATLAS_LLM_PROFILE"] = "groq"
os.environ.setdefault("GROQ_API_KEY", "unit-test-key")
os.environ["ATLAS_CACHE_ENABLED"] = "false"  # tests opt in per-case
# force Neo4j "not configured" even when a real .env points at a live instance
os.environ["NEO4J_URI"] = ""

FIXTURES = Path(__file__).parent.parent / "fixtures"


def fixture(rel: str) -> str:
    return (FIXTURES / rel).read_text(encoding="utf-8")

import pytest  # noqa: E402

from atlas.store import db  # noqa: E402


@pytest.fixture
def fresh_db() -> None:
    """A clean schema for tests that touch the relational store."""
    db.reset_engine()
    db.Base.metadata.drop_all(db.get_engine())
    db.create_all()
