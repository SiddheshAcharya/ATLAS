"""Qdrant — the vector store (ADR-004).

Three collections, all cosine, all `settings.embedding_dim` wide:

* ``atlas_abstracts`` — one point per paper
* ``atlas_chunks``    — one point per text chunk (payload carries char offsets)
* ``atlas_claims``    — one point per claim

Phase 0 only needs: connect, health, create the collections. Points are written in
later phases. The connection target comes from ``settings.qdrant_url``:

* ``":memory:"``          ephemeral, per-process (fine for tests)
* ``"./data/qdrant"``     persistent on disk, **single process at a time**
* ``"http://host:6333"``  the container
"""

from __future__ import annotations

import atexit
import threading
import uuid
from typing import Any, cast

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PayloadSchemaType, PointStruct, VectorParams

from atlas.config import settings

COLLECTIONS = ("atlas_abstracts", "atlas_chunks", "atlas_claims")
_ID_NS = uuid.UUID("00000000-0000-0000-0000-00000a71a5ff")
_INDEXED_FIELDS = ("paper_id", "run_id", "section")


def point_id(key: str) -> str:
    """Deterministic Qdrant point id from any string key (chunk_id, paper_id, ...)."""
    return str(uuid.uuid5(_ID_NS, key))


class _SharedLocalClient:
    """One embedded-Qdrant client per process, every call serialized by a lock.

    Embedded Qdrant takes a file lock on its folder. Opening a new QdrantClient(path=...)
    per call meant two overlapping API requests (e.g. the paper page's source text while
    another view searched claims) collided on that lock and one failed with a 500 — and
    every call re-loaded the whole store from disk (~1 s each). Callers still call
    close() when done; for the shared client that is a no-op, and it closes at exit.
    """

    def __init__(self, client: QdrantClient) -> None:
        self._client = client
        self._lock = threading.RLock()

    def __getattr__(self, name: str) -> Any:
        if name == "close":
            return lambda *a, **k: None
        attr = getattr(self._client, name)
        if not callable(attr):
            return attr

        def locked(*args: Any, **kwargs: Any) -> Any:
            with self._lock:
                return attr(*args, **kwargs)

        return locked


_local_clients: dict[str, _SharedLocalClient] = {}
_local_clients_lock = threading.Lock()


def _close_local_clients() -> None:
    for shared in _local_clients.values():
        shared._client.close()


atexit.register(_close_local_clients)


def get_client() -> QdrantClient:
    url = settings.qdrant_url
    if url in (":memory:", "", None):
        return QdrantClient(location=":memory:")
    if url.startswith(("http://", "https://")):
        return QdrantClient(url=url)
    path = url.removeprefix("file:")
    with _local_clients_lock:
        if path not in _local_clients:
            _local_clients[path] = _SharedLocalClient(QdrantClient(path=path))
        return cast(QdrantClient, _local_clients[path])


def ping(client: QdrantClient | None = None) -> bool:
    try:
        (client or get_client()).get_collections()
        return True
    except Exception:
        return False


def ensure_collections(client: QdrantClient | None = None, dim: int | None = None) -> list[str]:
    """Create any missing collection (+ payload indexes on atlas_chunks)."""
    client = client or get_client()
    dim = dim or settings.embedding_dim
    existing = {c.name for c in client.get_collections().collections}
    created: list[str] = []
    for name in COLLECTIONS:
        if name in existing:
            continue
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
        created.append(name)
        # payload indexes are a no-op on the embedded store; only worth it on a server
        if name == "atlas_chunks" and not settings.qdrant_is_embedded:
            for field in _INDEXED_FIELDS:
                client.create_payload_index(
                    name, field_name=field, field_schema=PayloadSchemaType.KEYWORD
                )
    return created


def upsert_chunks(
    chunks: list[Any],
    vectors: list[list[float]],
    *,
    run_id: str | None,
    client: QdrantClient | None = None,
) -> int:
    """Write chunk points to `atlas_chunks`. Payload carries char offsets (DATA_MODEL §3)."""
    client = client or get_client()
    ensure_collections(client)
    points = [
        PointStruct(
            id=point_id(c.chunk_id),
            vector=vec,
            payload={
                "paper_id": c.paper_id,
                "run_id": run_id,
                "section": c.section,
                "chunk_index": c.chunk_index,
                "char_start": c.char_start,
                "char_end": c.char_end,
                "text": c.text,
            },
        )
        for c, vec in zip(chunks, vectors, strict=True)
    ]
    if points:
        client.upsert("atlas_chunks", points=points)
    return len(points)


def upsert_abstract(
    paper_id: str,
    vector: list[float],
    *,
    run_id: str | None,
    title: str | None = None,
    year: int | None = None,
    depth: str | None = None,
    client: QdrantClient | None = None,
) -> None:
    """Write one point per paper to `atlas_abstracts`."""
    client = client or get_client()
    ensure_collections(client)
    client.upsert(
        "atlas_abstracts",
        points=[
            PointStruct(
                id=point_id(paper_id),
                vector=vector,
                payload={
                    "paper_id": paper_id,
                    "run_ids": [run_id] if run_id else [],
                    "title": title,
                    "year": year,
                    "depth": depth,
                },
            )
        ],
    )


def upsert_abstracts_bulk(
    rows: list[tuple[str, list[float], str | None, int | None, str | None]],
    *,
    run_id: str | None = None,
    client: QdrantClient | None = None,
) -> int:
    """rows: [(paper_id, vector, title, year, depth)]. Used to cache seed-ranking vectors."""
    client = client or get_client()
    ensure_collections(client)
    points = [
        PointStruct(
            id=point_id(pid),
            vector=vec,
            payload={
                "paper_id": pid,
                "run_ids": [run_id] if run_id else [],
                "title": title,
                "year": year,
                "depth": depth,
            },
        )
        for pid, vec, title, year, depth in rows
    ]
    if points:
        client.upsert("atlas_abstracts", points=points)
    return len(points)


def upsert_claims(
    claims: list[Any],
    vectors: list[list[float]],
    *,
    run_id: str,
    year_by_paper: dict[str, int | None] | None = None,
    client: QdrantClient | None = None,
) -> int:
    """Write claim points to `atlas_claims`. Payload carries everything the judge needs
    (text, quote, scope, section, year) so pairing needs no second lookup."""
    client = client or get_client()
    ensure_collections(client)
    year_by_paper = year_by_paper or {}
    points = [
        PointStruct(
            id=point_id(c.claim_id),
            vector=vec,
            payload={
                "claim_id": c.claim_id,
                "paper_id": c.paper_id,
                "run_id": run_id,
                "section": c.section,
                "text": c.text,
                "quote": c.quote,
                "scope": c.scope.model_dump() if hasattr(c.scope, "model_dump") else c.scope,
                "year": year_by_paper.get(c.paper_id),
            },
        )
        for c, vec in zip(claims, vectors, strict=True)
    ]
    if points:
        client.upsert("atlas_claims", points=points)
    return len(points)


def search_claims(
    query_vector: list[float],
    *,
    run_id: str,
    k: int,
    floor: float,
    exclude_paper_id: str | None = None,
    client: QdrantClient | None = None,
) -> list[dict[str, Any]]:
    """kNN over this run's claims (ADR-008). Returns payloads with a `similarity` field."""
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    client = client or get_client()
    ensure_collections(client)  # a run with zero claims so far must return [], not crash
    must = [FieldCondition(key="run_id", match=MatchValue(value=run_id))]
    hits = client.query_points(
        "atlas_claims",
        query=query_vector,
        query_filter=Filter(must=must),
        limit=k + 5,
        score_threshold=floor,
        with_payload=True,
    ).points
    out: list[dict[str, Any]] = []
    for h in hits:
        pl = dict(h.payload or {})
        if exclude_paper_id and pl.get("paper_id") == exclude_paper_id:
            continue
        pl["similarity"] = h.score
        out.append(pl)
        if len(out) >= k:
            break
    return out


def get_chunks_by_paper(
    paper_id: str, *, run_id: str | None = None, client: QdrantClient | None = None
) -> list[dict[str, Any]]:
    """All chunks for one paper (this run's, or any if `run_id` is None), sorted by
    chunk_index — used to reconstruct per-section text for concept extraction (Phase 5)."""
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    client = client or get_client()
    ensure_collections(client)
    must = [FieldCondition(key="paper_id", match=MatchValue(value=paper_id))]
    if run_id:
        must.append(FieldCondition(key="run_id", match=MatchValue(value=run_id)))
    points, _ = client.scroll(
        "atlas_chunks", scroll_filter=Filter(must=must), limit=1000, with_payload=True
    )
    rows = [dict(p.payload or {}) for p in points]
    rows.sort(key=lambda r: r.get("chunk_index", 0))
    return rows


def get_abstract_vectors(
    paper_ids: list[str], *, client: QdrantClient | None = None
) -> dict[str, list[float]]:
    """Return {paper_id: vector} for whichever ids are already in `atlas_abstracts`."""
    if not paper_ids:
        return {}
    client = client or get_client()
    ensure_collections(client)
    id_map = {point_id(pid): pid for pid in paper_ids}
    out: dict[str, list[float]] = {}
    ids = list(id_map)
    for i in range(0, len(ids), 256):
        got = client.retrieve("atlas_abstracts", ids=ids[i : i + 256], with_vectors=True)
        for rec in got:
            if rec.vector is not None:
                out[id_map[str(rec.id)]] = list(rec.vector)
    return out


def delete_run_points(run_id: str, *, client: QdrantClient | None = None) -> dict[str, int]:
    """Drop this run's chunk + claim points. Abstract points are shared (keyed by paper) —
    left in place."""
    from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

    client = client or get_client()
    ensure_collections(client)
    flt = Filter(must=[FieldCondition(key="run_id", match=MatchValue(value=run_id))])
    out: dict[str, int] = {}
    for coll in ("atlas_chunks", "atlas_claims"):
        before = count(coll, client)
        client.delete(coll, points_selector=FilterSelector(filter=flt))
        out[coll] = before - count(coll, client)
    return out


def count(collection: str, client: QdrantClient | None = None) -> int:
    client = client or get_client()
    return int(client.count(collection).count)
