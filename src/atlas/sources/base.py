"""The `Source` protocol and a shared HTTP base for the four scholarly APIs.

Every source:
* is queried per keyword from a `QueryPlan`,
* returns `PaperMeta` with `paper_id` from `ids.canonical_id` and `found_via=[its name]`,
* caches every HTTP response to `api_cache` (invariant 5) — a re-run hits disk, not the network,
* rate-limits itself politely (per-source minimum interval) and backs off on 429/5xx.

Cross-source dedup is the orchestrator's job (`ids.dedup_papers`), not the source's.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, Self, runtime_checkable

import httpx
import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from atlas.config import settings
from atlas.contracts import PaperMeta, QueryPlan, SourceName
from atlas.store import cache
from atlas.store.cache import make_key

log = structlog.get_logger(__name__)

CACHE_TTL = timedelta(days=30)


@runtime_checkable
class Source(Protocol):
    name: SourceName

    async def search(self, plan: QueryPlan, *, per_keyword: int) -> list[PaperMeta]: ...


class RetryableStatus(Exception):
    """A 429/5xx worth retrying."""

    def __init__(self, status: int, retry_after: float | None) -> None:
        super().__init__(f"HTTP {status}")
        self.retry_after = retry_after


class HttpSource:
    """Base class: cached, throttled, retrying GETs."""

    name: SourceName
    min_interval: float = 0.2  # seconds between requests to this source
    timeout: float = 30.0
    max_keywords: int | None = None  # cap keywords queried (rate-limited sources)

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client
        self._owns_client = client is None
        self._throttle_lock = asyncio.Lock()
        self._last_request = 0.0

    async def __aenter__(self) -> Self:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={"User-Agent": f"ATLAS/0.1 (mailto:{settings.contact_email})"},
                follow_redirects=True,
            )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _throttle(self) -> None:
        async with self._throttle_lock:
            gap = self.min_interval - (time.monotonic() - self._last_request)
            if gap > 0:
                await asyncio.sleep(gap)
            self._last_request = time.monotonic()

    async def _fetch_text(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> str | None:
        """GET `url`, return the response body as text. Cached. None on give-up."""
        key = make_key("GET", url, json.dumps(params or {}, sort_keys=True))
        if settings.cache_enabled:
            hit = await asyncio.to_thread(cache.api_cache_get, key)
            if hit is not None:
                return str(hit["response"])

        assert self._client is not None, "use `async with source:`"
        body: str | None = None
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(4),
                wait=wait_exponential(multiplier=1, min=1, max=20),
                retry=retry_if_exception_type((httpx.TransportError, RetryableStatus)),
                reraise=True,
            ):
                with attempt:
                    await self._throttle()
                    resp = await self._client.get(
                        url, params=params, headers=headers, timeout=self.timeout
                    )
                    if resp.status_code == 429 or resp.status_code >= 500:
                        ra = resp.headers.get("Retry-After")
                        if ra:
                            await asyncio.sleep(min(float(ra), 30))
                        raise RetryableStatus(resp.status_code, None)
                    resp.raise_for_status()
                    body = resp.text
        except Exception as e:  # network dead or 4xx — a source outage must not kill the harvest
            log.warning("source.fetch_failed", source=self.name.value, url=url, error=str(e))
            return None

        expires = datetime.now(UTC) + CACHE_TTL
        await asyncio.to_thread(
            cache.api_cache_put,
            key,
            source=self.name.value,
            response=body,
            status_code=200,
            expires_at=expires,
        )
        return body

    async def _fetch_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        text = await self._fetch_text(url, params=params, headers=headers)
        if text is None:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            log.warning("source.bad_json", source=self.name.value, url=url)
            return None

    async def search_keyword(self, keyword: str, *, limit: int) -> list[PaperMeta]:
        raise NotImplementedError

    async def search(self, plan: QueryPlan, *, per_keyword: int) -> list[PaperMeta]:
        """Query every keyword, concurrently within this source, and concat the results."""
        keywords = plan.keywords
        if self.max_keywords is not None:
            keywords = keywords[: self.max_keywords]
        tasks = [self.search_keyword(k.text, limit=per_keyword) for k in keywords]
        out: list[PaperMeta] = []
        for res in await asyncio.gather(*tasks, return_exceptions=True):
            if isinstance(res, BaseException):
                log.warning("source.keyword_failed", source=self.name.value, error=str(res))
                continue
            out.extend(res)
        return out
