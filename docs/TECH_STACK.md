# TECH STACK

Chosen for: free or near-free at student scale, runs on one laptop with 16 GB RAM via Docker,
demonstrable offline if campus wifi fails on demo day, and defensible in a viva.

## The stack

| Layer | Choice | Why this one | Considered instead |
|---|---|---|---|
| Language | **Python 3.11+** | every scholarly/ML library assumes it | — |
| Orchestration | **Plain async Python** state machine | the loop is deterministic and sequential; a framework hides the very logic being graded | LangGraph (see ADR-002), Celery, Prefect |
| API server | **FastAPI + uvicorn** | async, Pydantic-native, SSE via `sse-starlette` | Flask (no async), Django (too heavy) |
| Validation / contracts | **Pydantic v2** + `pydantic-settings` | one model set shared by API, LLM structured output, and DB | dataclasses, attrs |
| LLM access | **LiteLLM** (provider-agnostic) + **instructor** for structured output | swap Claude ↔ Gemini ↔ local Ollama by editing one YAML; protects against a key expiring in April | direct SDKs (lock-in), LangChain LLM wrappers |
| Embeddings | **`BAAI/bge-base-en-v1.5`** via `sentence-transformers`, local | 768-dim, strong on scientific text, free, offline, deterministic | OpenAI `text-embedding-3`, `all-MiniLM-L6-v2` (faster/weaker — keep as `--fast` flag) |
| Vector store | **Qdrant** (Docker) | payload filtering by `run_id`/`paper_id`/`section` is essential and it is first-class here; persists across restarts | Chroma (weak filtering at scale), FAISS (no payloads), pgvector (fine, but one more Postgres load) |
| Graph DB | **Neo4j 5.x Community** + **APOC** + **GDS** | GDS gives PageRank, Louvain, Adamic-Adar, node similarity out of the box — four of the six gap detectors lean on it | NetworkX (in-memory only, no live UI), ArangoDB, Memgraph |
| Relational | **PostgreSQL 16** + SQLAlchemy 2 + Alembic | frontier queue, run state, caches, cost ledger | SQLite (fine for single-user; keep as a dev fallback) |
| PDF → structure | **GROBID 0.8.x** (Docker) | the only realistic way to get *sections* (abstract / methods / results / limitations / future work) rather than a wall of text. Section labels are what make claim extraction and detectors 4 and 6 possible. | PyMuPDF alone (no structure), Grobid-less LLM parsing (expensive, unverifiable) |
| PDF fallback | **PyMuPDF (fitz)** | when GROBID times out or the PDF is a scan; degrades to unsectioned text | pdfplumber (slower) |
| Chunking | **`langchain-text-splitters`** only | `RecursiveCharacterTextSplitter` is genuinely good and it is one small package — no need for the LangChain framework | custom splitter (reinvention), full LangChain (ADR-002) |
| Text matching | **rapidfuzz** | grounding-gate fallback after exact match fails | difflib (slow), fuzzywuzzy (dead) |
| Classical ML | **scikit-learn**, **hdbscan**, **networkx** | limitation clustering, TF-IDF/PMI for Swanson ABC, graph algorithms GDS lacks | — |
| Concept extraction | **KeyBERT** + noun-phrase chunking (spaCy `en_core_web_sm`), normalized by embedding-clustering | domain-general — works for IoT *and* biomedical queries | SciSpaCy + UMLS (biomedical only — wrong for the sample query), raw LLM extraction (uncontrolled vocabulary) |
| Logging | **structlog** (JSON) | run_id/paper_id-bound logs you can actually grep during a 40-minute crawl | stdlib logging |
| LLM tracing | **Langfuse** self-hosted *(optional)* | see every prompt/response/cost of a run in one UI; excellent viva demo | plain logs (adequate — this is a stretch item) |
| CLI | **Typer** | every stage runnable standalone | argparse, click |
| Tests | **pytest**, `pytest-asyncio`, **respx** (HTTP mocking), **testcontainers** (integration) | fixtures from real captured responses, no live network in unit tests | VCR.py (also fine) |
| Frontend | **React 18 + Vite + TypeScript + Tailwind + shadcn/ui** | fast, familiar, good components without design work | Next.js (SSR not needed), Streamlit (see ADR-009) |
| Graph viz | **Cytoscape.js** (`fcose` layout) + `react-cytoscapejs` | handles 500–2000 nodes, incremental `cy.add()` for live streaming, good layout control | react-force-graph (nice, weaker at incremental layout), D3 from scratch (time sink), Neo4j Bloom (not embeddable free) |
| Charts | **Recharts** | timeline + score charts | Chart.js |
| Container | **Docker Compose** | one `make up` brings up 4 services; reproducible on the examiner's machine | bare installs |

## Model routing (`config/models.yaml`)

Four LLM jobs with very different profiles. Do not use one model for all four — the judge job
dominates call volume and will eat the budget.

| Job | Volume | Needs | Default | Cheap fallback |
|---|---|---|---|---|
| A. Keyword expansion | 1/run | breadth | `claude-sonnet-5` | any |
| B. Claim extraction | ~1–3 per paper | long context, exact quoting, schema adherence | `claude-sonnet-5` | `gemini-2.x-flash` |
| C. Relation judging | **hundreds–thousands/run** | cheap, fast, consistent on a 5-way label | `claude-haiku-4-5-20251001` | local `qwen2.5:7b-instruct` via Ollama |
| D. Synthesis | 1/run | long context, strong writing | `claude-opus-5` | `claude-sonnet-5` |

Set `temperature: 0` everywhere. Job C should be batchable — group 10 pairs per call to cut
overhead, but keep one output object per pair.

Cost control: aggressive prompt caching, response caching keyed on `(prompt_hash, model, params)`,
and a hard per-run budget in `scoring.yaml` that stops the loop when hit. Log every call's tokens
to the `costs` table. Standard mode (20–25 papers) should land in the low single-digit dollars;
extra-deep (200 papers) is the one to run **once**, save, and demo from cache.

## Free / offline path

If API budget disappears, everything except quality still works:
- Ollama running `qwen2.5:7b-instruct` (jobs A and C) and `qwen2.5:14b-instruct` (jobs B and D)
- embeddings are already local
- Postgres, Qdrant, Neo4j, GROBID all run locally

Keep this path tested — `make test-offline` — because it is also your demo-day insurance.

## External APIs: real limits

| API | Auth | Limit | Gotcha |
|---|---|---|---|
| OpenAlex | none; add `mailto=` for the polite pool | 100k/day, 10 rps | abstracts are inverted indices; reconstruct |
| arXiv | none | be polite, ~1 req / 3 s | Atom XML, not JSON; only preprints |
| PubMed E-utilities | optional key | ~3 rps without key, ~10 with | two-step: `esearch` → `efetch` |
| Semantic Scholar | key recommended | ~100 req/5 min shared unauthenticated; a key starts around 1 rps and returns 429/500 when it bites | do not build the citation walk on this; use OpenAlex |
| Unpaywall | `email=` param | polite | best route to a legal OA PDF when the source lacks one |

Every response is cached to Postgres by URL hash with a TTL. Re-running a query must not re-hit
the network.

## What is deliberately *not* in the stack

- **No Kubernetes, no message broker, no microservices.** One compose file.
- **No fine-tuning.** Nothing here needs it.
- **No LangChain agents / AgentExecutor.** ADR-002.
- **No cloud vector DB.** Local Qdrant is faster, free, and demoable offline.
- **No auth system.** Single-user project. If a multi-user demo is needed, put it behind a
  hardcoded token — do not build user management in week 11.
