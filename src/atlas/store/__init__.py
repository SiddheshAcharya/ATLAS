"""The only modules allowed to touch Postgres (db), Neo4j (graph), Qdrant (vector).
Write order is always Postgres -> Neo4j -> Qdrant (ADR-004)."""
