# Tests

`tests/unit/test_invariants.py` is the file that matters most. It encodes the project's
central claims as executable checks:

- canonical IDs collapse the same paper across four sources (ADR-006)
- normalization is idempotent, so character offsets stay valid
- the grounding gate rejects paraphrases, fabricated numbers, and truncated quotes (ADR-007)
- a gap with no bounding papers cannot even be constructed

Run: `PYTHONPATH=src pytest tests/unit -q`

No live network in `tests/unit`. Fixtures under `tests/fixtures/api/` are REAL captured API
responses — capture them with `atlas harvest --save-fixtures`, never hand-write them.
See `docs/TESTING.md` for the full strategy and the evaluation plan.

`tests/e2e/test_full_pipeline.py` runs the real `forage/loop.py` end to end — no faked
collaborators, unlike `tests/unit` — against a real warm cache
(`tests/fixtures/e2e/cache.db` + `tests/fixtures/e2e/qdrant/`, from one genuine tiny crawl)
with live network hard-blocked (`tests/e2e/conftest.py`). Run it on its own: `make
test-offline` or `pytest tests/e2e` — never combined with `tests/unit` in the same pytest
invocation, since the two directories' conftests set incompatible env vars at import time.
