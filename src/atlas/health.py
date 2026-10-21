"""Per-dependency health checks — shared by `atlas health` (cli.py) and `GET /health`
(api/main.py) so the two never drift. No Typer/Rich dependency here on purpose: the API
server should not need to import a CLI-rendering library just to report health.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx

from atlas.config import settings

_PROFILE_KEY: dict[str, tuple[str, Callable[[], str | None]]] = {
    "hybrid": ("GROQ+GEMINI keys", lambda: settings.groq_api_key and settings.gemini_api_key),
    "groq": ("GROQ_API_KEY", lambda: settings.groq_api_key),
    "cloud": ("ANTHROPIC_API_KEY", lambda: settings.anthropic_api_key),
    "cheap": ("GEMINI_API_KEY", lambda: settings.gemini_api_key),
    "local": ("OLLAMA_BASE_URL", lambda: settings.ollama_base_url),
}


def check_db() -> tuple[bool, str]:
    from atlas.store import db

    ok = db.ping()
    kind = "sqlite" if settings.is_sqlite else "postgres"
    return ok, f"{kind}: {settings.postgres_dsn.split('@')[-1]}"


def check_qdrant() -> tuple[bool, str]:
    from atlas.store import vector

    ok = vector.ping()
    mode = "embedded" if settings.qdrant_is_embedded else "server"
    return ok, f"{mode}: {settings.qdrant_url}"


def check_neo4j() -> tuple[bool | None, str]:
    from atlas.store import graph

    h = graph.health()
    if not h.configured:
        return None, "not configured (NEO4J_URI unset) — using in-memory graph later"
    if not h.reachable:
        return False, h.detail
    return True, h.detail


def check_grobid() -> tuple[bool | None, str]:
    """GROBID is optional (ADR-005: PyMuPDF is the fallback). A miss is SKIP, not FAIL."""
    try:
        r = httpx.get(f"{settings.grobid_url}/api/isalive", timeout=10.0, follow_redirects=True)
        if r.status_code == 200 and r.text.strip().lower() == "true":
            return True, settings.grobid_url
        return None, f"{settings.grobid_url} unavailable — PyMuPDF fallback will be used"
    except Exception as e:
        return None, f"{settings.grobid_url} unreachable ({type(e).__name__}) — PyMuPDF fallback"


def check_llm(live: bool) -> tuple[bool | None, str]:
    env_name, getter = _PROFILE_KEY.get(settings.llm_profile, ("?", lambda: None))
    key = getter()
    if not key:
        return False, f"profile {settings.llm_profile!r}: {env_name} not set"
    if not live:
        return True, f"profile {settings.llm_profile!r}: {env_name} present (--live-llm to call)"
    try:
        from atlas.llm.client import LLMClient

        res = LLMClient().complete(
            "judge", messages=[{"role": "user", "content": "Reply with the single word OK."}]
        )
        return True, f"{res.meta.model} responded ({res.meta.output_tokens} tok)"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def check_all(*, live_llm: bool = False) -> list[tuple[str, bool | None, str]]:
    """[(service, ok, detail)]. ok: True=OK, False=FAIL, None=SKIP (optional dependency)."""
    return [
        ("postgres/sqlite", *check_db()),
        ("neo4j", *check_neo4j()),
        ("qdrant", *check_qdrant()),
        ("grobid", *check_grobid()),
        ("llm", *check_llm(live_llm)),
    ]
