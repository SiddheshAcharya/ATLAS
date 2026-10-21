"""llm/client.py — routing, response cache (invariant 4), cost ledger.

No network: `_call` is monkeypatched. The cache and cost-logging paths are what Phase 0
must guarantee.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from atlas.llm.client import LLMClient, LLMOutputTruncated, ModelRouting
from atlas.store import cache
from atlas.store.db import Cost, get_engine


def test_routing_resolves_groq_profile():
    r = ModelRouting(profile="groq")
    model, params = r.for_job("judge")
    assert model.startswith("groq/")
    assert params["temperature"] == 0


def test_cache_hit_on_second_identical_call(fresh_db: None, monkeypatch):
    monkeypatch.setattr("atlas.llm.client.settings.cache_enabled", True)
    cache.clear_all()
    calls: list[int] = []

    def fake_call(self, model, messages, params, response_model):
        calls.append(1)
        return "OK", 11, 3, 0.0

    monkeypatch.setattr(LLMClient, "_call", fake_call)
    client = LLMClient(run_id=None)
    msg = [{"role": "user", "content": "ping"}]

    first = client.complete("judge", messages=msg)
    second = client.complete("judge", messages=msg)

    assert first.value == "OK" == second.value
    assert first.meta.cache_hit is False
    assert second.meta.cache_hit is True
    assert len(calls) == 1  # the model was hit exactly once

    with get_engine().connect() as c:
        rows = list(c.execute(sa.select(Cost.cache_hit, Cost.job)))
    # one row per complete() call — hit and miss both logged
    assert sorted(bool(r[0]) for r in rows) == [False, True]
    assert {r[1] for r in rows} == {"judge"}


def _truncating_call(calls: list[int], succeed_at: int | None):
    """A fake `_call` that truncates until `max_tokens` reaches `succeed_at`."""

    def fake_call(self, model, messages, params, response_model):
        calls.append(params["max_tokens"])
        if succeed_at is None or params["max_tokens"] < succeed_at:
            raise LLMOutputTruncated(f"{model}: IncompleteOutputException")
        return "done", 11, 3, 0.0

    return fake_call


def test_truncated_call_retries_with_double_budget_and_replays_offline(
    fresh_db: None, monkeypatch
):
    """A cut-off answer is cached as such, so a replay takes the same retry path with zero
    provider calls (invariant 4) instead of re-asking and possibly getting a new answer."""
    monkeypatch.setattr("atlas.llm.client.settings.cache_enabled", True)
    cache.clear_all()
    base = ModelRouting(profile="groq").for_job("claims")[1]["max_tokens"]
    calls: list[int] = []
    monkeypatch.setattr(LLMClient, "_call", _truncating_call(calls, succeed_at=base * 2))
    client = LLMClient(run_id=None)
    msg = [{"role": "user", "content": "a long section"}]

    first = client.complete("claims", messages=msg)
    assert first.value == "done"
    assert calls == [base, base * 2]

    replay = client.complete("claims", messages=msg)
    assert replay.value == "done" and replay.meta.cache_hit
    assert calls == [base, base * 2]  # nothing new reached the provider


def test_truncated_twice_raises_and_replays_the_same_failure(fresh_db: None, monkeypatch):
    monkeypatch.setattr("atlas.llm.client.settings.cache_enabled", True)
    cache.clear_all()
    calls: list[int] = []
    monkeypatch.setattr(LLMClient, "_call", _truncating_call(calls, succeed_at=None))
    client = LLMClient(run_id=None)
    msg = [{"role": "user", "content": "an even longer section"}]

    with pytest.raises(LLMOutputTruncated):
        client.complete("claims", messages=msg)
    assert len(calls) == 2
    with pytest.raises(LLMOutputTruncated):
        client.complete("claims", messages=msg)
    assert len(calls) == 2


def test_caller_chosen_max_tokens_is_not_second_guessed(fresh_db: None, monkeypatch):
    monkeypatch.setattr("atlas.llm.client.settings.cache_enabled", True)
    cache.clear_all()
    calls: list[int] = []
    monkeypatch.setattr(LLMClient, "_call", _truncating_call(calls, succeed_at=None))
    client = LLMClient(run_id=None)
    with pytest.raises(LLMOutputTruncated):
        client.complete("claims", messages=[{"role": "user", "content": "x"}], max_tokens=50)
    assert calls == [50]
