"""E2E isolation — a real, warm cache, real network fully blocked.

Unlike `tests/unit`, this doesn't fake the harvest/ingest/claims/judge collaborators —
it runs the actual `forage/loop.py` code path against a *real* cache of API/LLM responses
recorded from a genuine tiny crawl (`tests/fixtures/e2e/cache.db` +
`tests/fixtures/e2e/qdrant/`, seeded once via a real `atlas run` against
"small language models for edge devices", 3 papers, standard mode — see the file's own
git history for the exact command). Every external call this run needs is already a cache
hit; anything that would reach the network instead is a bug, and `_block_network` below
makes that a hard failure rather than a silent slow test.

Run as its own pytest invocation (`pytest tests/e2e` or `pytest -m e2e`), never combined
with `tests/unit` in the same process — env vars are set at import time, same constraint
as `tests/unit/conftest.py`, and the two directories set incompatible values
(`ATLAS_CACHE_ENABLED` in particular: false for unit, true here — the cache path is
exactly what this suite is testing).
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

FIXTURES = Path(__file__).parent.parent / "fixtures" / "e2e"
_TMP = Path(tempfile.mkdtemp(prefix="atlas-e2e-"))

# Copy the fixture DB + Qdrant snapshot + downloaded PDFs so a test run never mutates the
# checked-in fixtures (which would make the suite non-reproducible across runs). PDFs
# aren't in the DB cache at all — ingest/pdf_fetch.py's own docstring: "Downloaded PDFs
# are the cache: a file already on disk is returned without a network call" — so they
# have to be replayed from disk, same as the DB-backed caches.
_DB_COPY = _TMP / "cache.db"
shutil.copy(FIXTURES / "cache.db", _DB_COPY)
_QDRANT_COPY = _TMP / "qdrant"
shutil.copytree(FIXTURES / "qdrant", _QDRANT_COPY)
_DATA_DIR = _TMP / "data"
shutil.copytree(FIXTURES / "pdfs", _DATA_DIR / "pdfs")

os.environ["POSTGRES_DSN"] = f"sqlite+pysqlite:///{_DB_COPY.as_posix()}"
os.environ["QDRANT_URL"] = str(_QDRANT_COPY)
os.environ["ATLAS_DATA_DIR"] = str(_DATA_DIR)
# Must exactly match the contact email the fixture was seeded with — OpenAlex's `mailto`
# param is part of the cached request URL, so a different value here is a guaranteed
# cache miss (found the hard way — see this file's git history). A placeholder, not the
# real .env value: this fixture ships in the repo, and a real address has no business
# being baked into committed test data.
os.environ["ATLAS_CONTACT_EMAIL"] = "atlas-e2e-fixture@example.edu"
os.environ["ATLAS_LLM_PROFILE"] = "groq"  # must match the profile the fixture was seeded with
os.environ.setdefault("GROQ_API_KEY", "e2e-test-key-never-actually-used")
os.environ["ATLAS_CACHE_ENABLED"] = "true"
os.environ["NEO4J_URI"] = ""  # graph writes skipped, matching how the fixture was seeded
os.environ["HF_HUB_OFFLINE"] = "1"  # embedding model is local + already cached; never phone home
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import httpx  # noqa: E402
import pytest  # noqa: E402
import respx  # noqa: E402


@pytest.fixture(autouse=True)
def _block_network():
    """Every external call this test needs should already be a cache hit. If anything
    reaches for the real network, that's worth failing on — but as a *real-shaped*
    network failure (`httpx.ConnectError`), not an arbitrary exception type.

    Found the hard way: `ingest/grobid.py`'s `is_alive()` health check always hits the
    network by design (asking "is the service up right now" isn't cacheable) and already
    handles a real connection failure gracefully, falling back to PyMuPDF — exactly what
    happens on every real run on this GROBID-less machine. An arbitrary exception type
    (e.g. a plain RuntimeError) isn't what that `except httpx.HTTPError` clause is written
    to catch, so it were propagating past code that already handles a dead network
    correctly, and failing the test on already-working behavior, not a real cache-miss
    bug. `httpx.ConnectError` lets every already-graceful path work exactly as it does
    against a real dead service, while anything that isn't wrapped in error handling at
    all still fails loudly, which is the actual thing worth catching here."""
    with respx.mock(assert_all_called=False) as router:
        router.route().mock(side_effect=httpx.ConnectError(
            "tests/e2e blocked a real network call — every request here should be a "
            "cache hit against tests/fixtures/e2e/cache.db. Either the fixture is stale "
            "(the query/config changed since it was seeded) or something isn't checking "
            "the cache before falling back to the network."
        ))
        yield router
