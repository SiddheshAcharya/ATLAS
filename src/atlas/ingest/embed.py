"""Local sentence embeddings — `BAAI/bge-base-en-v1.5`, 768-dim, deterministic, offline.

CPU-bound and synchronous (CLAUDE.md: sync for CPU). The model (~440 MB) downloads once
on first use and is held as a process-global singleton. Async callers must go through
`asyncio.to_thread`.
"""

from __future__ import annotations

import threading
from typing import Any

import structlog

from atlas.config import settings

log = structlog.get_logger(__name__)

_lock = threading.Lock()
_model = None


def _get_model() -> Any:
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from sentence_transformers import SentenceTransformer

                log.info("embed.loading_model", model=settings.embedding_model)
                _model = SentenceTransformer(settings.embedding_model)
    return _model


def get_model() -> Any:
    """The shared SentenceTransformer instance — reuse it (KeyBERT etc) rather than
    loading a second copy of the model."""
    return _get_model()


def embed_texts(texts: list[str], *, batch_size: int = 32) -> list[list[float]]:
    if not texts:
        return []
    arr = _get_model().encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return [row.tolist() for row in arr]


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]


def embedding_dim() -> int:
    return int(_get_model().get_sentence_embedding_dimension())
