"""Provider-agnostic LLM access: LiteLLM + instructor, response cache, cost ledger.

One entry point — ``LLMClient.complete(job, ...)``. ``job`` is one of the four defined in
``config/models.yaml`` (``keywords`` | ``claims`` | ``judge`` | ``synthesis``); the active
profile there maps it to a concrete model string. Change providers by editing that YAML,
never this file (ADR: LiteLLM behind a thin client).

Invariant 4 — every call is cached and replayable, keyed on
``(job, model, params, prompt_version, messages, response_model)``. A rerun of a run_id
must reproduce the same output. Every call (hit or miss) writes a row to ``costs``.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar, cast, get_args, get_origin

import structlog
import yaml
from pydantic import BaseModel

from atlas.config import settings
from atlas.store import cache
from atlas.store.cache import make_key
from atlas.store.db import Cost, session_scope

log = structlog.get_logger(__name__)

MODELS_YAML = Path("config/models.yaml")
T = TypeVar("T", bound=BaseModel)


class LLMUnavailable(RuntimeError):
    """Raised when no provider is reachable for the active profile."""


class LLMOutputTruncated(LLMUnavailable):
    """The model hit `max_tokens` before finishing its structured answer.

    Unlike other failures this one is a property of the (prompt, model, params) input, not
    of the network, so it is cached like an answer: a replay reaches the same verdict
    without calling the provider, and `complete()` takes the same retry path.
    """


# Stored in llm_cache in place of a response when a call was truncated.
_TRUNCATED: dict[str, Any] = {"__truncated__": True}


def _is_truncation(e: Exception) -> bool:
    text = f"{type(e).__name__}: {e}"
    return "IncompleteOutputException" in text or "max_tokens length limit" in text


# ── client-side rate limiting ──────────────────────────────────────────────


class _RateLimiter:
    """Trailing-60s token/request budget. `acquire(est)` blocks until the call fits."""

    def __init__(self, *, tpm: int | None = None, rpm: int | None = None) -> None:
        self.tpm = tpm
        self.rpm = rpm
        self._events: deque[tuple[float, int]] = deque()
        self._lock = threading.Lock()

    def _prune(self, now: float) -> None:
        while self._events and now - self._events[0][0] > 60.0:
            self._events.popleft()

    def acquire(self, est_tokens: int) -> None:
        with self._lock:
            while True:
                now = time.monotonic()
                self._prune(now)
                tok = sum(t for _, t in self._events)
                req = len(self._events)
                over_tpm = self.tpm is not None and tok + est_tokens > self.tpm
                over_rpm = self.rpm is not None and req + 1 > self.rpm
                if not (over_tpm or over_rpm) or not self._events:
                    self._events.append((now, est_tokens))
                    return
                wait = 60.0 - (now - self._events[0][0]) + 0.2
                log.info("llm.rate_limit_wait", seconds=round(wait, 1), used_tokens=tok)
                time.sleep(max(0.2, wait))


_limiters: dict[str, _RateLimiter] = {}
_limiters_lock = threading.Lock()


def _limiter_for(provider: str) -> _RateLimiter | None:
    with _limiters_lock:
        if provider in _limiters:
            return _limiters[provider] or None
        raw = yaml.safe_load(MODELS_YAML.read_text(encoding="utf-8")).get("rate_limits", {})
        cfg = raw.get(provider)
        limiter = _RateLimiter(tpm=cfg.get("tpm"), rpm=cfg.get("rpm")) if cfg else None
        _limiters[provider] = limiter  # type: ignore[assignment]
        return limiter


def _estimate_tokens(messages: list[dict[str, str]], params: dict[str, Any]) -> int:
    prompt = sum(len(m.get("content", "")) for m in messages) // 4
    return prompt + int(params.get("max_tokens", 1500)) + 200  # +fudge for reasoning models


@dataclass
class CallMeta:
    job: str
    model: str
    cache_hit: bool
    prompt_tokens: int
    output_tokens: int
    usd: float


@dataclass
class LLMResult:
    value: Any  # a `response_model` instance, or `str`
    meta: CallMeta


# ── model routing ───────────────────────────────────────────────────────────


class ModelRouting:
    def __init__(self, path: Path = MODELS_YAML, profile: str | None = None) -> None:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        self._profiles: dict[str, dict[str, Any]] = raw["profiles"]
        self._prompts: dict[str, str] = raw.get("prompts", {})
        self.profile = profile or settings.llm_profile or raw.get("default_profile", "groq")
        if self.profile not in self._profiles:
            raise ValueError(
                f"unknown llm profile {self.profile!r}; have {sorted(self._profiles)}"
            )

    def for_job(self, job: str) -> tuple[str, dict[str, Any]]:
        jobs = self._profiles[self.profile]
        if job not in jobs:
            raise ValueError(f"job {job!r} undefined for profile {self.profile!r}")
        cfg = dict(jobs[job])
        model = cfg.pop("model")
        return model, cfg

    def prompt_file(self, job: str) -> str:
        return str(self._prompts[job])

    def prompt_version(self, job: str) -> str:
        # the version token in the filename, e.g. "keywords.v1.md" -> "v1"
        name = self._prompts.get(job, "")
        for part in name.split("."):
            if part.startswith("v") and part[1:].isdigit():
                return part
        return "v0"


_gemini_key_idx = 0


def _export_provider_keys() -> None:
    """LiteLLM reads provider keys from os.environ; mirror them from settings."""
    for env_name, value in (
        ("ANTHROPIC_API_KEY", settings.anthropic_api_key),
        ("GROQ_API_KEY", settings.groq_api_key),
    ):
        if value and not os.environ.get(env_name):
            os.environ[env_name] = value
    keys = settings.gemini_api_keys
    if keys:
        os.environ.setdefault("GEMINI_API_KEY", keys[_gemini_key_idx % len(keys)])
    if settings.ollama_base_url and not os.environ.get("OLLAMA_API_BASE"):
        os.environ["OLLAMA_API_BASE"] = settings.ollama_base_url


def _rotate_gemini_key() -> bool:
    """Advance to the next configured Gemini key. False when they're all exhausted."""
    global _gemini_key_idx
    keys = settings.gemini_api_keys
    if len(keys) < 2 or _gemini_key_idx >= len(keys) - 1:
        return False
    _gemini_key_idx += 1
    os.environ["GEMINI_API_KEY"] = keys[_gemini_key_idx]
    log.warning("llm.gemini_key_rotated", to_index=_gemini_key_idx, of=len(keys))
    return True


# ── client ─────────────────────────────────────────────────────────────────


class LLMClient:
    def __init__(self, routing: ModelRouting | None = None, run_id: str | None = None) -> None:
        self.routing = routing or ModelRouting()
        self.run_id = run_id
        _export_provider_keys()

    def complete(
        self,
        job: str,
        *,
        messages: list[dict[str, str]],
        response_model: Any = None,
        prompt_version: str | None = None,
        **overrides: Any,
    ) -> LLMResult:
        model, params = self.routing.for_job(job)
        params.update(overrides)
        pv = prompt_version or self.routing.prompt_version(job)
        try:
            return self._complete_once(job, model, params, pv, messages, response_model)
        except LLMOutputTruncated:
            # Reasoning models spend completion tokens thinking, so a long input can run
            # out of room mid-answer. One retry with double the budget; its own cache key.
            # A caller that chose max_tokens itself gets no second guess.
            if "max_tokens" in overrides:
                raise
            bigger = {**params, "max_tokens": int(params.get("max_tokens", 1500)) * 2}
            log.warning(
                "llm.truncated_retry", job=job, model=model, max_tokens=bigger["max_tokens"]
            )
            return self._complete_once(job, model, bigger, pv, messages, response_model)

    def _complete_once(
        self,
        job: str,
        model: str,
        params: dict[str, Any],
        pv: str,
        messages: list[dict[str, str]],
        response_model: Any,
    ) -> LLMResult:
        key = make_key(
            job, model, json.dumps(params, sort_keys=True), pv,
            json.dumps(messages, sort_keys=True),
            str(response_model) if response_model else "str",
        )

        if settings.cache_enabled:
            cached = cache.llm_cache_get(key)
            if cached is not None:
                meta = CallMeta(
                    job, model, True,
                    cached["prompt_tokens"], cached["output_tokens"], 0.0,
                )
                self._log_cost(meta)
                if cached["response"] == _TRUNCATED:
                    log.info("llm.cache_hit_truncated", job=job, model=model)
                    raise LLMOutputTruncated(f"{model}: cached truncation for this input")
                value = _decode(cached["response"], response_model)
                log.info("llm.cache_hit", job=job, model=model)
                return LLMResult(value, meta)

        try:
            # a copy: _call adds transport defaults that must not leak into a retry's key
            value, pt, ot, usd = self._call(model, messages, dict(params), response_model)
        except LLMOutputTruncated:
            if settings.cache_enabled:
                cache.llm_cache_put(
                    key, model=model, job=job, response=_TRUNCATED,
                    prompt_tokens=0, output_tokens=0,
                )
            self._log_cost(CallMeta(job, model, False, 0, 0, 0.0))
            raise
        payload = _encode(value)
        if settings.cache_enabled:
            cache.llm_cache_put(
                key, model=model, job=job, response=payload,
                prompt_tokens=pt, output_tokens=ot,
            )
        meta = CallMeta(job, model, False, pt, ot, usd)
        self._log_cost(meta)
        log.info("llm.call", job=job, model=model, prompt_tokens=pt, output_tokens=ot, usd=usd)
        return LLMResult(value, meta)

    # -- internals ----------------------------------------------------------

    def _call(
        self,
        model: str,
        messages: list[dict[str, str]],
        params: dict[str, Any],
        response_model: type[T] | None,
    ) -> tuple[Any, int, int, float]:
        try:
            import litellm
        except ImportError as e:  # pragma: no cover
            raise LLMUnavailable("litellm is not installed") from e

        litellm.drop_params = True
        params.setdefault("timeout", 120)  # a hung provider must not stall the loop
        value: Any
        msgs = cast("Any", messages)

        limiter = _limiter_for(model.split("/", 1)[0])

        def _invoke() -> tuple[Any, Any]:
            if limiter is not None:
                limiter.acquire(_estimate_tokens(messages, params))
            if response_model is not None:
                import instructor

                # MD_JSON (parse a ```json block) — reasoning models like Groq's gpt-oss
                # emit fenced JSON and reject forced tool calls.
                ic = instructor.from_litellm(litellm.completion, mode=instructor.Mode.MD_JSON)
                pair: tuple[Any, Any] = ic.chat.completions.create_with_completion(
                    model=model, messages=msgs, response_model=response_model,
                    max_retries=2, **params,
                )
                return pair
            r = litellm.completion(model=model, messages=msgs, **params)
            return r.choices[0].message.content or "", r

        try:
            value, raw = _invoke()
        except Exception as e:
            if _is_truncation(e):
                raise LLMOutputTruncated(f"{model}: {type(e).__name__}: {e}") from e
            msg = str(e).lower()
            is_rate = "rate_limit" in msg or "resource_exhausted" in msg or "quota" in msg
            if not is_rate and "ratelimit" not in type(e).__name__.lower():
                raise LLMUnavailable(f"{model}: {type(e).__name__}: {e}") from e
            # Gemini daily-quota: a sleep won't help — swap to the fallback key
            if model.startswith("gemini/") and _rotate_gemini_key():
                pass
            else:
                time.sleep(20)  # one polite backoff for a per-minute limit
            try:
                value, raw = _invoke()
            except Exception as e2:
                if _is_truncation(e2):
                    raise LLMOutputTruncated(f"{model}: {type(e2).__name__}: {e2}") from e2
                raise LLMUnavailable(f"{model}: {type(e2).__name__}: {e2}") from e2

        usage = getattr(raw, "usage", None)
        pt = int(getattr(usage, "prompt_tokens", 0) or 0)
        ot = int(getattr(usage, "completion_tokens", 0) or 0)
        try:
            usd = float(litellm.completion_cost(completion_response=raw))
        except Exception:
            usd = 0.0
        return value, pt, ot, usd

    def _log_cost(self, meta: CallMeta) -> None:
        try:
            with session_scope() as s:
                s.add(
                    Cost(
                        run_id=self.run_id,
                        job=meta.job,
                        model=meta.model,
                        prompt_tokens=meta.prompt_tokens,
                        output_tokens=meta.output_tokens,
                        usd=meta.usd,
                        cache_hit=meta.cache_hit,
                    )
                )
        except Exception:
            log.warning("llm.cost_log_failed", job=meta.job, exc_info=True)


def _encode(value: Any) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return {
            "items": [
                v.model_dump(mode="json") if isinstance(v, BaseModel) else v for v in value
            ]
        }
    return {"text": value}


def _decode(payload: dict[str, Any], response_model: Any) -> Any:
    if response_model is None:
        return payload.get("text", "")
    if get_origin(response_model) is list:
        (item_model,) = get_args(response_model)
        return [item_model.model_validate(x) for x in payload.get("items", [])]
    return response_model.model_validate(payload)
