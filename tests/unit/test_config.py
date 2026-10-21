"""config.py — the single source of environment truth."""

from __future__ import annotations

import os

import pytest

from atlas.config import Settings, settings


@pytest.mark.skipif(
    bool(os.environ.get("ATLAS_TEST_POSTGRES_DSN")),
    reason="checks the default SQLite path; this run targets Postgres on purpose",
)
def test_lightweight_defaults_load():
    assert settings.is_sqlite
    assert settings.qdrant_is_embedded
    assert settings.neo4j_configured is False  # NEO4J_URI unset in conftest


def test_ensure_dirs_creates_subdirs():
    root = settings.ensure_dirs()
    for sub in ("pdfs", "tei", "cache"):
        assert (root / sub).is_dir()


def test_docker_dsn_flips_is_sqlite():
    s = Settings(POSTGRES_DSN="postgresql+psycopg://atlas:atlas@localhost:5432/atlas")
    assert s.is_sqlite is False


def test_http_qdrant_is_not_embedded():
    s = Settings(QDRANT_URL="http://localhost:6333")
    assert s.qdrant_is_embedded is False
