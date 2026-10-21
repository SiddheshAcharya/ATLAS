# ATLAS

**A**gentic **T**echnology for **L**iterature review using **A**ugmented **S**ynthesis.

Ask a research question. ATLAS reads the literature the way a researcher does — most promising
paper first, then follow its citations, then reconsider what to read next — and builds a live
knowledge graph as it goes. It ends by telling you what the field agrees on, where it contradicts
itself, and which gaps are genuinely unexplored, with a verbatim citation for every statement.

## Quick start

The defaults below are the **no-Docker "lightweight" path** — SQLite, an embedded Qdrant,
PyMuPDF instead of GROBID, and (optionally) a free Neo4j AuraDB cloud instance. This is what
runs on a weak laptop with no Docker and no GPU. If you have Docker and want the full stack
(Postgres, self-hosted Neo4j, Qdrant server, GROBID) instead, see `docker-compose.yml` and swap
in the commented-out `POSTGRES_DSN`/`NEO4J_URI`/`QDRANT_URL`/`GROBID_URL` lines in `.env.example`,
then run `make up` before the steps below.

```bash
cp .env.example .env          # add your LLM API key + a contact email for the polite pools
                               # (optional: add Neo4j AuraDB Free credentials for the live graph)
atlas init-stores              # runs migrations, creates the Qdrant collections, applies Neo4j schema
make dev                       # api on :8000, web on :5173
atlas run "Women safety using IoT devices" --mode standard
```

## Docs

Start with `CLAUDE.md`, then `docs/ARCHITECTURE.md`. Full index in `CLAUDE.md`.

## What makes it different from RAG-over-papers

| | Naive RAG | ATLAS |
|---|---|---|
| Paper selection | one cosine ranking, fixed | re-scored after every paper read |
| Citations | ignored | walked; PageRank and clusters feed selection |
| Quotes | model-generated | verified character-for-character or discarded |
| Output | a summary | agreement, contradictions, ranked gaps, methodology timeline |
| Off-corpus questions | answered from model knowledge | refused |

## Status

Final-year B.Tech project. See `docs/ROADMAP.md`.
