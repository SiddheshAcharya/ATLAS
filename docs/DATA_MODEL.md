# DATA MODEL

Three stores. **Postgres is the source of truth for existence and run state**; Neo4j and Qdrant
are projections that can be rebuilt from it (`atlas repair --run-id <id>`).

---

## 1. Neo4j — the knowledge graph

### Nodes

| Label | Key | Properties |
|---|---|---|
| `Paper` | `paper_id` (canonical, unique) | `title, year, venue, doi, url, pdf_url, depth, abstract, citation_count, pagerank, cluster_id, read_order, relevance, first_seen_via, run_ids[]` |
| `Author` | `author_id` | `name, orcid, openalex_id` |
| `Concept` | `concept_id` (slug of normalized label) | `label, aliases[], embedding_id, df` |
| `Claim` | `claim_id` (uuid) | `text, quote, quote_char_start, quote_char_end, section, scope, polarity, confidence, verified, run_id` |
| `Method` | `method_id` | `label, aliases[]` |
| `Dataset` | `dataset_id` | `label, aliases[]` |
| `Gap` | `gap_key` (= `run_id:gap_id`) | `gap_id, type, statement, gap_score, detector_scores{}, rank, run_id` — one node per (run, gap): a run's gap set is replaced on every detector pass, and two runs that find the same gap no longer share (and overwrite) one node |
| `Run` | `run_id` | `query, mode, started_at, finished_at, status, config_hash` |

### Relationships

```cypher
(:Paper)-[:CITES]->(:Paper)                       // directed; the citation graph
(:Paper)-[:MAKES_CLAIM]->(:Claim)
(:Paper)-[:AUTHORED_BY]->(:Author)
(:Paper)-[:MENTIONS {tf, salience}]->(:Concept)
(:Paper)-[:USES_METHOD]->(:Method)
(:Paper)-[:EVALUATED_ON]->(:Dataset)
(:Paper)-[:HAS_LIMITATION {text, cluster_id}]->(:Concept)
(:Paper)-[:CALLS_FOR {text, answered}]->(:Concept)     // "future work" statements
(:Claim)-[:SUPPORTS      {confidence, judged_by, rationale, run_id}]->(:Claim)
(:Claim)-[:CONTRADICTS   {confidence, judged_by, rationale, run_id, resolved}]->(:Claim)
(:Claim)-[:EXTENDS       {confidence, judged_by, rationale, run_id}]->(:Claim)
(:Claim)-[:REPLICATES    {confidence, judged_by, rationale, run_id}]->(:Claim)
(:Claim)-[:DIFF_SCOPE    {confidence, judged_by, rationale, run_id}]->(:Claim)
(:Gap)-[:BOUNDED_BY {role}]->(:Paper)             // role: "a_side" | "b_side" | "evidence"
(:Gap)-[:INVOLVES]->(:Concept|:Method|:Dataset)
(:Run)-[:READ {order, at}]->(:Paper)
```

`run_id` on relationships lets multiple runs share the same `Paper` nodes without polluting each
other's analysis. Always filter by `run_id` in analytical queries.

### Constraints and indexes

```cypher
CREATE CONSTRAINT paper_id   IF NOT EXISTS FOR (p:Paper)   REQUIRE p.paper_id   IS UNIQUE;
CREATE CONSTRAINT claim_id   IF NOT EXISTS FOR (c:Claim)   REQUIRE c.claim_id   IS UNIQUE;
CREATE CONSTRAINT concept_id IF NOT EXISTS FOR (k:Concept) REQUIRE k.concept_id IS UNIQUE;
CREATE CONSTRAINT gap_key    IF NOT EXISTS FOR (g:Gap)     REQUIRE g.gap_key    IS UNIQUE;  -- was gap_id until 2026-09-28
CREATE CONSTRAINT run_id     IF NOT EXISTS FOR (r:Run)     REQUIRE r.run_id     IS UNIQUE;
CREATE INDEX paper_year      IF NOT EXISTS FOR (p:Paper)   ON (p.year);
CREATE INDEX paper_pagerank  IF NOT EXISTS FOR (p:Paper)   ON (p.pagerank);
CREATE INDEX claim_section   IF NOT EXISTS FOR (c:Claim)   ON (c.section);
```

### GDS projections

Named graph `citation_<run_id>`, refreshed when dirty:

```cypher
CALL gds.graph.project.cypher(
  $graphName,
  'MATCH (p:Paper) WHERE $runId IN p.run_ids RETURN id(p) AS id',
  'MATCH (a:Paper)-[:CITES]->(b:Paper)
   WHERE $runId IN a.run_ids AND $runId IN b.run_ids
   RETURN id(a) AS source, id(b) AS target'
);
CALL gds.pageRank.write($graphName, {writeProperty: 'pagerank', dampingFactor: 0.85});
CALL gds.louvain.write($graphName, {writeProperty: 'cluster_id'});
```

Always `gds.graph.drop` before re-projecting, and treat projection as expensive — batch it
(see `SCORING.md` §Recompute cadence).

### Writes are idempotent

Every write is a `MERGE` keyed on the canonical ID. Re-running the loop over the same paper must
not duplicate nodes. Test this explicitly.

---

## 2. Postgres — run state

```sql
CREATE TYPE frontier_state AS ENUM ('pending','parked','reading','read','dropped','failed');
CREATE TYPE paper_depth    AS ENUM ('full_text','abstract_only','metadata_only');

CREATE TABLE runs (
  run_id         UUID PRIMARY KEY,
  query          TEXT NOT NULL,
  mode           TEXT NOT NULL,              -- standard | deep | extra_deep
  config_hash    TEXT NOT NULL,
  keywords       JSONB,
  status         TEXT NOT NULL DEFAULT 'running',
  stop_reason    TEXT,
  started_at     TIMESTAMPTZ DEFAULT now(),
  finished_at    TIMESTAMPTZ
);

CREATE TABLE papers (                        -- source of truth for existence
  paper_id       TEXT PRIMARY KEY,
  title          TEXT NOT NULL,
  year           INT,
  venue          TEXT,
  doi            TEXT,
  arxiv_id       TEXT,
  pmid           TEXT,
  openalex_id    TEXT,
  s2_corpus_id   TEXT,
  abstract       TEXT,
  authors        JSONB,
  pdf_url        TEXT,
  depth          paper_depth DEFAULT 'metadata_only',
  raw            JSONB,                      -- original API payloads, per source
  created_at     TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ON papers (doi);
CREATE INDEX ON papers (lower(title));

CREATE TABLE frontier (
  run_id         UUID REFERENCES runs(run_id),
  paper_id       TEXT REFERENCES papers(paper_id),
  state          frontier_state NOT NULL DEFAULT 'pending',
  score          DOUBLE PRECISION,
  relevance      DOUBLE PRECISION,
  pagerank       DOUBLE PRECISION,
  novelty        DOUBLE PRECISION,
  contest        DOUBLE PRECISION,
  recency        DOUBLE PRECISION,
  discovered_via TEXT,                       -- 'seed' | 'reference_of:<id>' | 'citer_of:<id>' | 'bridge'
  parked_reason  TEXT,
  read_order     INT,
  attempts       INT DEFAULT 0,
  updated_at     TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (run_id, paper_id)
);
CREATE INDEX ON frontier (run_id, state, score DESC);

CREATE TABLE claims (                        -- mirror of Neo4j Claim, for cheap SQL analysis
  claim_id       UUID PRIMARY KEY,
  run_id         UUID,
  paper_id       TEXT,
  text           TEXT,
  quote          TEXT,
  quote_start    INT,
  quote_end      INT,
  section        TEXT,
  scope          JSONB,
  verified       BOOLEAN,
  verify_method  TEXT,                       -- 'exact' | 'fuzzy97' | 'failed'
  created_at     TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE api_cache (
  cache_key      TEXT PRIMARY KEY,           -- sha256(method|url|sorted_params)
  source         TEXT,
  response       JSONB,
  status_code    INT,
  fetched_at     TIMESTAMPTZ DEFAULT now(),
  expires_at     TIMESTAMPTZ
);

CREATE TABLE llm_cache (
  cache_key      TEXT PRIMARY KEY,           -- sha256(prompt|model|params|prompt_version)
  model          TEXT,
  job            TEXT,
  response       JSONB,
  prompt_tokens  INT,
  output_tokens  INT,
  created_at     TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE costs (
  id             BIGSERIAL PRIMARY KEY,
  run_id         UUID,
  job            TEXT,
  model          TEXT,
  prompt_tokens  INT,
  output_tokens  INT,
  usd            NUMERIC(10,6),
  cache_hit      BOOLEAN,
  at             TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE events (                        -- SSE replay log; lets a refreshed browser catch up
  id             BIGSERIAL PRIMARY KEY,
  run_id         UUID,
  seq            BIGINT,
  type           TEXT,
  payload        JSONB,
  at             TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ON events (run_id, seq);

CREATE TABLE relations (                     -- mirror of the Neo4j Claim-Claim edges (Job C, R2 eval)
  id                BIGSERIAL PRIMARY KEY,   -- migration 0002; added in Phase 4
  run_id            TEXT,
  source_claim_id   TEXT,
  target_claim_id   TEXT,
  type              TEXT,                    -- SUPPORTS | CONTRADICTS | EXTENDS | REPLICATES | DIFF_SCOPE
  confidence        DOUBLE PRECISION,
  rationale         TEXT,
  judged_by         TEXT,
  created_at        TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ON relations (run_id, type);
CREATE INDEX ON relations (source_claim_id, target_claim_id);
```

> **Note (impl):** `run_id` / `claim_id` columns are `TEXT`, not `UUID` — the identical string
> has to key Postgres, Neo4j and the `data/runs/<id>/` directory (SQLAlchemy's `Uuid` stores
> hyphen-less on SQLite). Native `ENUM`s are emulated as `CHECK` constraints for SQLite/Postgres
> portability. See ADR-011/012 for the networkx-not-GDS and rate-limit-pacer deviations.

---

## 3. Qdrant — vectors

Three collections, all 768-dim (bge-base-en-v1.5), cosine distance.

| Collection | One point per | Payload |
|---|---|---|
| `atlas_abstracts` | paper | `paper_id, run_ids[], year, depth, title` |
| `atlas_chunks` | text chunk | `paper_id, run_id, section, chunk_index, char_start, char_end, text` |
| `atlas_claims` | claim | `claim_id, paper_id, run_id, section, year` |

`atlas_chunks` payload **must** carry `char_start`/`char_end` into the normalized source text —
the grounding gate and the UI's quote highlighting both depend on it.

Chunking: `RecursiveCharacterTextSplitter`, 1000 characters, 150 overlap, split within GROBID
sections so a chunk never spans Methods→Results. Abstracts are never chunked.

Payload indexes on `paper_id`, `run_id`, and `section` — filtered search is the common case.

---

## Consistency rules

1. Write order is always **Postgres → Neo4j → Qdrant**. A crash mid-write leaves projections
   behind the truth, which `atlas repair` fixes; the reverse order would leave orphans.
2. Nothing except `store/db.py` writes to Postgres. Nothing except `store/graph.py` runs Cypher.
   Nothing except `store/vector.py` talks to Qdrant. No raw driver calls scattered in stage code.
3. Deleting a run deletes its Qdrant points and its `run_id`-tagged Neo4j relationships, but
   **not** shared `Paper` nodes — remove the `run_id` from `run_ids[]` and delete the node only if
   the array is then empty.
