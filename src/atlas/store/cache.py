"""Response caches backed by the relational store.

Two caches, same idea, different keys:

* ``api_cache``  — keyed on ``sha256(method|url|sorted_params)``   (invariant 5)
* ``llm_cache``  — keyed on ``sha256(prompt|model|params|prompt_version)``  (invariant 4)

A cache hit must be byte-identical to the original response so a rerun of a ``run_id``
reproduces the same graph.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

import sqlalchemy as sa

from atlas.store.db import ApiCache, LlmCache, session_scope


def make_key(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


# ── LLM cache ───────────────────────────────────────────────────────────────


def llm_cache_get(cache_key: str) -> dict[str, Any] | None:
    with session_scope() as s:
        row = s.get(LlmCache, cache_key)
        if row is None:
            return None
        return {
            "response": row.response,
            "model": row.model,
            "job": row.job,
            "prompt_tokens": row.prompt_tokens or 0,
            "output_tokens": row.output_tokens or 0,
        }


def llm_cache_put(
    cache_key: str,
    *,
    model: str,
    job: str,
    response: dict[str, Any],
    prompt_tokens: int,
    output_tokens: int,
) -> None:
    with session_scope() as s:
        if s.get(LlmCache, cache_key) is not None:
            return
        s.add(
            LlmCache(
                cache_key=cache_key,
                model=model,
                job=job,
                response=response,
                prompt_tokens=prompt_tokens,
                output_tokens=output_tokens,
            )
        )


# ── API cache ───────────────────────────────────────────────────────────────


def api_cache_get(cache_key: str) -> dict[str, Any] | None:
    with session_scope() as s:
        row = s.get(ApiCache, cache_key)
        if row is None:
            return None
        if row.expires_at is not None and row.expires_at < datetime.now(row.expires_at.tzinfo):
            return None
        return {"response": row.response, "status_code": row.status_code, "source": row.source}


def api_cache_put(
    cache_key: str,
    *,
    source: str,
    response: Any,
    status_code: int,
    expires_at: datetime | None = None,
) -> None:
    with session_scope() as s:
        existing = s.get(ApiCache, cache_key)
        if existing is not None:
            existing.response = response
            existing.status_code = status_code
            existing.expires_at = expires_at
            return
        s.add(
            ApiCache(
                cache_key=cache_key,
                source=source,
                response=response,
                status_code=status_code,
                expires_at=expires_at,
            )
        )


def clear_all() -> None:
    """Test helper — wipe both caches."""
    with session_scope() as s:
        s.execute(sa.delete(LlmCache))
        s.execute(sa.delete(ApiCache))
