"""Single source of environment truth (pydantic-settings).

Stage code imports `settings` from here; it never reads `os.environ` directly.

The defaults are the *lightweight* path — SQLite, an embedded on-disk Qdrant, and a
PyMuPDF fallback when GROBID is not running — so ATLAS runs on a laptop with no Docker.
To scale up,
point `POSTGRES_DSN` / `NEO4J_URI` / `QDRANT_URL` / `GROBID_URL` at the compose stack
in `docker-compose.yml`. Nothing else in the code changes.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# GROBID has no reliable free hosted instance (the old HF Space demo is down). Default to
# the docker-compose container; when it is not running, ingest falls back to PyMuPDF.
DEFAULT_GROBID = "http://localhost:8070"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    # ── identity (polite API pools want a real address) ──────────────────────
    contact_email: str = Field("you@example.edu", alias="ATLAS_CONTACT_EMAIL")

    # ── LLM (LiteLLM routes by the prefix in config/models.yaml) ─────────────
    llm_profile: str = Field("groq", alias="ATLAS_LLM_PROFILE")
    anthropic_api_key: str | None = Field(None, alias="ANTHROPIC_API_KEY")
    gemini_api_key: str | None = Field(None, alias="GEMINI_API_KEY")
    gemini_api_key_2: str | None = Field(None, alias="GEMINI_API_KEY_2")
    groq_api_key: str | None = Field(None, alias="GROQ_API_KEY")
    ollama_base_url: str | None = Field(None, alias="OLLAMA_BASE_URL")

    # ── scholarly APIs (all optional) ───────────────────────────────────────
    semantic_scholar_api_key: str | None = Field(None, alias="SEMANTIC_SCHOLAR_API_KEY")
    ncbi_api_key: str | None = Field(None, alias="NCBI_API_KEY")

    # ── stores ─────────────────────────────────────────────────────────────
    postgres_dsn: str = Field("sqlite+pysqlite:///./data/atlas.db", alias="POSTGRES_DSN")
    neo4j_uri: str | None = Field(None, alias="NEO4J_URI")
    neo4j_user: str = Field("neo4j", alias="NEO4J_USER")
    neo4j_password: str = Field("atlaspassword", alias="NEO4J_PASSWORD")
    # AuraDB Free names the default DB after the instance id, not "neo4j".
    neo4j_database: str = Field("neo4j", alias="NEO4J_DATABASE")
    # ":memory:" (ephemeral), a path like "./data/qdrant" (persistent, single-process),
    # or an "http://host:6333" URL (the container).
    qdrant_url: str = Field("./data/qdrant", alias="QDRANT_URL")
    grobid_url: str = Field(DEFAULT_GROBID, alias="GROBID_URL")

    # ── models ─────────────────────────────────────────────────────────────
    embedding_model: str = Field("BAAI/bge-base-en-v1.5", alias="EMBEDDING_MODEL")
    embedding_dim: int = Field(768, alias="EMBEDDING_DIM")

    # ── behaviour ──────────────────────────────────────────────────────────
    mode: str = Field("standard", alias="ATLAS_MODE")
    cache_enabled: bool = Field(True, alias="ATLAS_CACHE_ENABLED")
    log_level: str = Field("INFO", alias="ATLAS_LOG_LEVEL")
    data_dir: Path = Field(Path("./data"), alias="ATLAS_DATA_DIR")

    # ── API (Phase 6) ──────────────────────────────────────────────────────
    # Comma-separated origins the dashboard is served from. Defaults cover Vite's dev
    # server on both common ports; narrow this before anything resembling a real deploy.
    api_cors_origins_raw: str = Field(
        "http://localhost:5173,http://127.0.0.1:5173", alias="ATLAS_API_CORS_ORIGINS"
    )

    # ── optional tracing ───────────────────────────────────────────────────
    langfuse_public_key: str | None = Field(None, alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str | None = Field(None, alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str | None = Field(None, alias="LANGFUSE_HOST")

    # ── derived ────────────────────────────────────────────────────────────
    @property
    def is_sqlite(self) -> bool:
        return self.postgres_dsn.startswith("sqlite")

    @property
    def qdrant_is_embedded(self) -> bool:
        return not self.qdrant_url.startswith(("http://", "https://"))

    @property
    def neo4j_configured(self) -> bool:
        return bool(self.neo4j_uri)

    @property
    def gemini_api_keys(self) -> list[str]:
        """All configured Gemini keys, in fallback order."""
        return [k for k in (self.gemini_api_key, self.gemini_api_key_2) if k]

    @property
    def api_cors_origins(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins_raw.split(",") if o.strip()]

    def ensure_dirs(self) -> Path:
        """Create data/ and its subdirs. Called once at startup."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        for sub in ("pdfs", "tei", "cache"):
            (self.data_dir / sub).mkdir(parents=True, exist_ok=True)
        return self.data_dir


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s


settings = get_settings()
