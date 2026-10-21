"""Neo4j — the knowledge graph (ADR-004, DATA_MODEL.md §1).

Only this module runs Cypher. Phase 0 scope: connect, health, apply the constraints
and indexes, and report whether GDS/APOC are present (four gap detectors need GDS).

Neo4j is optional on the lightweight path: if ``NEO4J_URI`` is unset, `health()` reports
``configured=False`` and nothing raises. Set it to a Neo4j AuraDB Free connection
string (``neo4j+s://<id>.databases.neo4j.io``) or the local container
(``bolt://localhost:7687``) to enable it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog

from atlas.config import settings

if TYPE_CHECKING:
    from neo4j import Driver, Session

    from atlas.contracts import Claim, RankedGap, Relation

log = structlog.get_logger(__name__)

# From DATA_MODEL.md §1 — idempotent, safe to run every startup.
SCHEMA_STATEMENTS = (
    "CREATE CONSTRAINT paper_id IF NOT EXISTS FOR (p:Paper) REQUIRE p.paper_id IS UNIQUE",
    "CREATE CONSTRAINT claim_id IF NOT EXISTS FOR (c:Claim) REQUIRE c.claim_id IS UNIQUE",
    "CREATE CONSTRAINT concept_id IF NOT EXISTS FOR (k:Concept) REQUIRE k.concept_id IS UNIQUE",
    "CREATE CONSTRAINT method_id IF NOT EXISTS FOR (m:Method) REQUIRE m.method_id IS UNIQUE",
    "CREATE CONSTRAINT dataset_id IF NOT EXISTS FOR (d:Dataset) REQUIRE d.dataset_id IS UNIQUE",
    # Gap nodes are per run (key run_id:gap_id). One node per gap_id let two runs that found
    # the same gap overwrite each other's rank/run_id (ADR-013 addendum, 2026-09-28).
    "DROP CONSTRAINT gap_id IF EXISTS",
    "CREATE CONSTRAINT gap_key IF NOT EXISTS FOR (g:Gap) REQUIRE g.gap_key IS UNIQUE",
    "CREATE CONSTRAINT run_id IF NOT EXISTS FOR (r:Run) REQUIRE r.run_id IS UNIQUE",
    "CREATE INDEX paper_year IF NOT EXISTS FOR (p:Paper) ON (p.year)",
    "CREATE INDEX paper_pagerank IF NOT EXISTS FOR (p:Paper) ON (p.pagerank)",
    "CREATE INDEX claim_section IF NOT EXISTS FOR (c:Claim) ON (c.section)",
)


_UsageMap = dict[str, tuple[str, list[str]]]


@dataclass
class GraphHealth:
    configured: bool
    reachable: bool
    has_gds: bool = False
    has_apoc: bool = False
    detail: str = ""


class GraphStore:
    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
    ) -> None:
        self.uri = uri or settings.neo4j_uri
        self._user = user or settings.neo4j_user
        self._password = password or settings.neo4j_password
        self._database = database or settings.neo4j_database
        self._driver: Driver | None = None

    def _session(self) -> Session:
        assert self._driver is not None
        return self._driver.session(database=self._database)

    def _connect(self) -> None:
        if self._driver is not None or not self.uri:
            return
        from neo4j import GraphDatabase

        # A crawl can leave the pool idle for minutes (harvest + embedding) and AuraDB drops
        # idle connections; the first write then died with SessionExpired and took the whole
        # run down. Ping any connection idle > 30 s before reuse, and recycle old ones.
        self._driver = GraphDatabase.driver(
            self.uri,
            auth=(self._user, self._password),
            liveness_check_timeout=30,
            max_connection_lifetime=300,
        )

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def __enter__(self) -> GraphStore:
        self._connect()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _procedures(self) -> set[str]:
        assert self._driver is not None
        with self._session() as s:
            rows = s.run("SHOW PROCEDURES YIELD name RETURN name")
            return {r["name"] for r in rows}

    def apply_schema(self) -> list[str]:
        """Run every constraint/index statement. Returns the statements executed."""
        self._connect()
        if self._driver is None:
            raise RuntimeError("Neo4j is not configured (set NEO4J_URI)")
        with self._session() as s:
            for stmt in SCHEMA_STATEMENTS:
                s.run(stmt)
        log.info("graph.schema_applied", count=len(SCHEMA_STATEMENTS))
        return list(SCHEMA_STATEMENTS)

    # ── incremental writes (invariant 6: paper by paper, never batched to the end) ──

    def _run_write(self, cypher: str, **params: object) -> None:
        self._connect()
        if self._driver is None:
            raise RuntimeError("Neo4j is not configured (set NEO4J_URI)")
        # A managed transaction: the driver retries it on a dropped connection or other
        # transient error. Safe because every write here is an idempotent MERGE/SET.
        with self._session() as s:
            # dict, not **kwargs — a param may be named `query`
            s.execute_write(lambda tx: tx.run(cypher, params).consume())

    def write_run(self, run_id: str, query: str, mode: str, config_hash: str) -> None:
        self._run_write(
            "MERGE (r:Run {run_id:$run_id}) "
            "SET r.query=$query, r.mode=$mode, r.config_hash=$cfg, "
            "    r.started_at=coalesce(r.started_at, datetime())",
            run_id=run_id, query=query, mode=mode, cfg=config_hash,
        )

    def finish_run(self, run_id: str, status: str, stop_reason: str) -> None:
        self._run_write(
            "MERGE (r:Run {run_id:$run_id}) "
            "SET r.status=$status, r.stop_reason=$reason, r.finished_at=datetime()",
            run_id=run_id, status=status, reason=stop_reason,
        )

    def write_paper(
        self,
        *,
        paper_id: str,
        title: str,
        run_id: str,
        year: int | None = None,
        venue: str | None = None,
        doi: str | None = None,
        pdf_url: str | None = None,
        abstract: str | None = None,
        citation_count: int | None = None,
        depth: str | None = None,
        relevance: float | None = None,
        read_order: int | None = None,
        first_seen_via: str | None = None,
    ) -> None:
        """MERGE a Paper node keyed on canonical id. Re-running never duplicates it."""
        self._run_write(
            """
            MERGE (p:Paper {paper_id:$paper_id})
            ON CREATE SET p.title=$title, p.first_seen_via=$via, p.run_ids=[$run_id]
            SET p.title=coalesce($title, p.title),
                p.year=coalesce($year, p.year),
                p.venue=coalesce($venue, p.venue),
                p.doi=coalesce($doi, p.doi),
                p.pdf_url=coalesce($pdf_url, p.pdf_url),
                p.abstract=coalesce($abstract, p.abstract),
                p.citation_count=coalesce($cc, p.citation_count),
                p.depth=coalesce($depth, p.depth),
                p.relevance=coalesce($relevance, p.relevance),
                p.read_order=coalesce($read_order, p.read_order),
                p.run_ids = CASE WHEN $run_id IN coalesce(p.run_ids, [])
                                 THEN p.run_ids ELSE coalesce(p.run_ids, []) + $run_id END
            """,
            paper_id=paper_id, title=title, via=first_seen_via, run_id=run_id,
            year=year, venue=venue, doi=doi, pdf_url=pdf_url, abstract=abstract,
            cc=citation_count, depth=depth, relevance=relevance, read_order=read_order,
        )

    def write_claims(self, claims: list[Claim], run_id: str) -> int:
        rows = [
            {
                "claim_id": c.claim_id, "paper_id": c.paper_id, "text": c.text,
                "quote": c.quote, "section": c.section,
                "qs": c.quote_char_start, "qe": c.quote_char_end,
                "polarity": c.polarity, "confidence": c.confidence,
                "verify_method": c.verify_method,
            }
            for c in claims
        ]
        if not rows:
            return 0
        self._run_write(
            """
            UNWIND $rows AS row
            MATCH (p:Paper {paper_id: row.paper_id})
            MERGE (c:Claim {claim_id: row.claim_id})
            SET c.text=row.text, c.quote=row.quote, c.section=row.section,
                c.quote_char_start=row.qs, c.quote_char_end=row.qe,
                c.polarity=row.polarity, c.confidence=row.confidence,
                c.verified=true, c.verify_method=row.verify_method, c.run_id=$run_id
            MERGE (p)-[:MAKES_CLAIM]->(c)
            """,
            rows=rows, run_id=run_id,
        )
        return len(rows)

    def write_cites(
        self, src_paper_id: str, targets: list[tuple[str, str]], run_id: str
    ) -> int:
        """targets: [(paper_id, title)]. Creates stub Paper nodes for unknown targets."""
        rows = [{"paper_id": pid, "title": title} for pid, title in targets]
        if not rows:
            return 0
        self._run_write(
            """
            MATCH (src:Paper {paper_id:$src})
            UNWIND $rows AS row
            MERGE (dst:Paper {paper_id: row.paper_id})
            ON CREATE SET dst.title=row.title
            SET dst.run_ids = CASE WHEN $run_id IN coalesce(dst.run_ids, [])
                                   THEN dst.run_ids ELSE coalesce(dst.run_ids, []) + $run_id END
            MERGE (src)-[:CITES]->(dst)
            """,
            src=src_paper_id, rows=rows, run_id=run_id,
        )
        return len(rows)

    # claim-claim edges: type can't be parameterised in Cypher, so one query per type.
    _REL_TYPES = ("SUPPORTS", "CONTRADICTS", "EXTENDS", "REPLICATES", "DIFF_SCOPE")

    def write_relations(self, relations: list[Relation], run_id: str) -> int:
        by_type: dict[str, list[dict[str, object]]] = {t: [] for t in self._REL_TYPES}
        for r in relations:  # UNRELATED -> no edge
            if r.type in by_type:
                by_type[r.type].append(
                    {
                        "src": r.source_claim_id,
                        "dst": r.target_claim_id,
                        "confidence": r.confidence,
                        "rationale": r.rationale,
                        "judged_by": r.judged_by,
                    }
                )
        written = 0
        for rel_type, rows in by_type.items():
            if not rows:
                continue
            self._run_write(
                f"""
                UNWIND $rows AS row
                MATCH (a:Claim {{claim_id: row.src}}), (b:Claim {{claim_id: row.dst}})
                MERGE (a)-[e:{rel_type} {{run_id: $run_id}}]->(b)
                SET e.confidence = row.confidence, e.rationale = row.rationale,
                    e.judged_by = row.judged_by
                """,
                rows=rows,
                run_id=run_id,
            )
            written += len(rows)
        return written

    # ── graph analytics (networkx, not GDS — decided for the laptop) ──────────

    def citation_edges(self, run_id: str) -> list[tuple[str, str]]:
        self._connect()
        assert self._driver is not None
        with self._session() as s:
            rows = s.run(
                "MATCH (a:Paper)-[:CITES]->(b:Paper) "
                "WHERE $run_id IN a.run_ids AND $run_id IN b.run_ids "
                "RETURN a.paper_id AS a, b.paper_id AS b",
                {"run_id": run_id},
            )
            return [(r["a"], r["b"]) for r in rows]

    def graph_snapshot(self, run_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """(nodes, edges) as Cytoscape elements for GET /runs/{id}/graph (docs/API.md).

        Nodes: this run's Paper nodes with pagerank / cluster_id / depth, and `read_order`
        taken from this run's own READ edge. (`p.read_order` is shared by every run that
        touched the paper, so a paper another run read looked "read" here too.)
        Edges: CITES between papers, plus this run's claim relations rolled up to paper
        pairs — one edge per (paper, paper, relation type) with the claim-pair count — so
        the UI can colour contradictions red and support green (docs/API.md).
        """
        self._connect()
        assert self._driver is not None
        with self._session() as s:
            node_rows = s.run(
                "MATCH (p:Paper) WHERE $rid IN p.run_ids "
                "OPTIONAL MATCH (:Run {run_id:$rid})-[rd:READ]->(p) "
                "RETURN p.paper_id AS id, p.title AS title, p.year AS year, "
                "       p.depth AS depth, p.pagerank AS pagerank, "
                "       p.cluster_id AS cluster_id, rd.order AS read_order "
                "ORDER BY id",
                {"rid": run_id},
            )
            nodes = [
                {
                    "data": {
                        "id": r["id"], "label": r["title"] or r["id"], "year": r["year"],
                        "depth": r["depth"], "pagerank": r["pagerank"] or 0.0,
                        "cluster_id": r["cluster_id"], "read_order": r["read_order"],
                    }
                }
                for r in node_rows
            ]
            edge_rows = s.run(
                "MATCH (a:Paper)-[:CITES]->(b:Paper) "
                "WHERE $rid IN a.run_ids AND $rid IN b.run_ids "
                "RETURN a.paper_id AS src, b.paper_id AS dst ORDER BY src, dst",
                {"rid": run_id},
            )
            edges: list[dict[str, Any]] = [
                {
                    "data": {
                        "id": f"{r['src']}->{r['dst']}", "source": r["src"], "target": r["dst"],
                        "type": "CITES",
                    }
                }
                for r in edge_rows
            ]
            rel_rows = s.run(
                "MATCH (pa:Paper)-[:MAKES_CLAIM]->(:Claim)-[e]->(:Claim)"
                "      <-[:MAKES_CLAIM]-(pb:Paper) "
                "WHERE e.run_id = $rid AND type(e) IN $types AND pa <> pb "
                "RETURN pa.paper_id AS src, pb.paper_id AS dst, type(e) AS type, "
                "       count(*) AS n, max(e.confidence) AS confidence "
                "ORDER BY src, dst, type",
                {"rid": run_id, "types": list(self._REL_TYPES)},
            )
            edges += [
                {
                    "data": {
                        "id": f"{r['type']}:{r['src']}->{r['dst']}", "source": r["src"],
                        "target": r["dst"], "type": r["type"], "count": r["n"],
                        "confidence": r["confidence"],
                    }
                }
                for r in rel_rows
            ]
        return nodes, edges

    def run_paper_ids(self, run_id: str) -> list[str]:
        self._connect()
        assert self._driver is not None
        with self._session() as s:
            rows = s.run(
                "MATCH (p:Paper) WHERE $run_id IN p.run_ids RETURN p.paper_id AS pid",
                {"run_id": run_id},
            )
            return [r["pid"] for r in rows]

    def write_pagerank_clusters(
        self, run_id: str, pagerank: dict[str, float], cluster: dict[str, int]
    ) -> None:
        rows = [
            {"pid": pid, "pr": pagerank.get(pid, 0.0), "cl": cluster.get(pid, -1)}
            for pid in set(pagerank) | set(cluster)
        ]
        if rows:
            self._run_write(
                "UNWIND $rows AS row MATCH (p:Paper {paper_id: row.pid}) "
                "SET p.pagerank = row.pr, p.cluster_id = row.cl",
                rows=rows,
            )

    def contest_inputs(self, run_id: str) -> dict[str, tuple[int, int]]:
        """{paper_id: (contradiction_edges, total_judged_edges)} over its claims."""
        self._connect()
        assert self._driver is not None
        with self._session() as s:
            rows = s.run(
                """
                MATCH (p:Paper)-[:MAKES_CLAIM]->(c:Claim {run_id:$run_id})
                OPTIONAL MATCH (c)-[e {run_id:$run_id}]-(:Claim)
                WITH p.paper_id AS pid,
                     sum(CASE WHEN type(e) = 'CONTRADICTS' THEN 1 ELSE 0 END) AS contra,
                     count(e) AS total
                RETURN pid, contra, total
                """,
                {"run_id": run_id},
            )
            return {r["pid"]: (r["contra"], r["total"]) for r in rows}

    def cluster_read_counts(self, run_id: str) -> dict[int, int]:
        """{cluster_id: number of READ papers in it} — the 'actively building' clusters."""
        self._connect()
        assert self._driver is not None
        with self._session() as s:
            rows = s.run(
                "MATCH (r:Run {run_id:$run_id})-[:READ]->(p:Paper) "
                "WHERE p.cluster_id IS NOT NULL "
                "RETURN p.cluster_id AS cl, count(p) AS n",
                {"run_id": run_id},
            )
            return {r["cl"]: r["n"] for r in rows}

    def clusters_of(self, paper_ids: list[str]) -> dict[str, int]:
        if not paper_ids:
            return {}
        self._connect()
        assert self._driver is not None
        with self._session() as s:
            rows = s.run(
                "MATCH (p:Paper) WHERE p.paper_id IN $ids AND p.cluster_id IS NOT NULL "
                "RETURN p.paper_id AS pid, p.cluster_id AS cl",
                {"ids": paper_ids},
            )
            return {r["pid"]: r["cl"] for r in rows}

    def write_read(self, run_id: str, paper_id: str, order: int) -> None:
        self._run_write(
            "MATCH (r:Run {run_id:$run_id}), (p:Paper {paper_id:$paper_id}) "
            "MERGE (r)-[rel:READ]->(p) SET rel.order=$order, rel.at=datetime()",
            run_id=run_id, paper_id=paper_id, order=order,
        )

    # ── concepts / methods / datasets / weaknesses / calls (Phase 5) ──────────

    def write_concepts(self, rows: list[dict[str, object]]) -> int:
        """rows: [{paper_id, concept_id, label, tf, salience}] -> MENTIONS edges."""
        if not rows:
            return 0
        self._run_write(
            """
            UNWIND $rows AS row
            MERGE (k:Concept {concept_id: row.concept_id})
            ON CREATE SET k.label = row.label
            WITH k, row
            MATCH (p:Paper {paper_id: row.paper_id})
            MERGE (p)-[m:MENTIONS]->(k)
            SET m.tf = row.tf, m.salience = row.salience
            """,
            rows=rows,
        )
        self._recompute_df({str(r["concept_id"]) for r in rows}, "Concept", "MENTIONS")
        return len(rows)

    def write_methods(self, rows: list[dict[str, object]]) -> int:
        """rows: [{paper_id, method_id, label}] -> USES_METHOD edges."""
        return self._write_typed_entity(rows, "Method", "method_id", "USES_METHOD")

    def write_datasets(self, rows: list[dict[str, object]]) -> int:
        """rows: [{paper_id, dataset_id, label}] -> EVALUATED_ON edges."""
        return self._write_typed_entity(rows, "Dataset", "dataset_id", "EVALUATED_ON")

    def _write_typed_entity(
        self, rows: list[dict[str, object]], label: str, id_key: str, rel: str
    ) -> int:
        if not rows:
            return 0
        self._run_write(
            f"""
            UNWIND $rows AS row
            MERGE (e:{label} {{{id_key}: row.entity_id}})
            ON CREATE SET e.label = row.label
            WITH e, row
            MATCH (p:Paper {{paper_id: row.paper_id}})
            MERGE (p)-[:{rel}]->(e)
            """,
            rows=[
                {"paper_id": r["paper_id"], "entity_id": r[id_key], "label": r["label"]}
                for r in rows
            ],
        )
        return len(rows)

    def write_weakness_clusters(
        self, run_id: str, clusters: list[dict[str, object]]
    ) -> int:
        """clusters: [{cluster_id, label, members: [{paper_id, text}]}] -> HAS_LIMITATION."""
        rows = [
            {
                "concept_id": f"weakness:{run_id}:{c['cluster_id']}",
                "label": c["label"],
                "paper_id": m["paper_id"],
                "text": m["text"],
                "cluster_id": c["cluster_id"],
            }
            for c in clusters
            for m in c["members"]  # type: ignore[attr-defined]
        ]
        if not rows:
            return 0
        self._run_write(
            """
            UNWIND $rows AS row
            MERGE (k:Concept {concept_id: row.concept_id})
            ON CREATE SET k.label = row.label, k.kind = 'weakness'
            WITH k, row
            MATCH (p:Paper {paper_id: row.paper_id})
            MERGE (p)-[e:HAS_LIMITATION]->(k)
            SET e.text = row.text, e.cluster_id = row.cluster_id
            """,
            rows=rows,
        )
        return len(rows)

    def write_calls(self, rows: list[dict[str, object]]) -> int:
        """rows: [{paper_id, concept_id, label, text}] -> CALLS_FOR edges."""
        if not rows:
            return 0
        self._run_write(
            """
            UNWIND $rows AS row
            MERGE (k:Concept {concept_id: row.concept_id})
            ON CREATE SET k.label = row.label
            WITH k, row
            MATCH (p:Paper {paper_id: row.paper_id})
            MERGE (p)-[e:CALLS_FOR]->(k)
            SET e.text = row.text
            """,
            rows=rows,
        )
        return len(rows)

    def _recompute_df(self, ids: set[str], label: str, rel: str) -> None:
        """Document frequency recomputed from the live edge count — idempotent on re-run,
        unlike an incrementing counter."""
        if not ids:
            return
        self._run_write(
            f"""
            MATCH (k:{label}) WHERE k.concept_id IN $ids
            OPTIONAL MATCH (:Paper)-[:{rel}]->(k)
            WITH k, count(*) AS df
            SET k.df = df
            """,
            ids=list(ids),
        )

    def concept_mentions(self, run_id: str) -> list[tuple[str, str, str]]:
        """[(paper_id, concept_id, label)] for papers this run read (excludes weaknesses)."""
        self._connect()
        assert self._driver is not None
        with self._session() as s:
            rows = s.run(
                "MATCH (r:Run {run_id:$rid})-[:READ]->(p:Paper)-[:MENTIONS]->(k:Concept) "
                "RETURN p.paper_id AS pid, k.concept_id AS cid, k.label AS label",
                {"rid": run_id},
            )
            return [(row["pid"], row["cid"], row["label"]) for row in rows]

    def method_dataset_usage(
        self, run_id: str
    ) -> tuple[_UsageMap, _UsageMap, set[tuple[str, str]]]:
        """(methods, datasets, tried_pairs). methods/datasets: {id: (label, [paper_id])}."""
        self._connect()
        assert self._driver is not None
        with self._session() as s:
            m_rows = s.run(
                "MATCH (r:Run {run_id:$rid})-[:READ]->(p:Paper)-[:USES_METHOD]->(m:Method) "
                "RETURN m.method_id AS id, m.label AS label, "
                "       collect(DISTINCT p.paper_id) AS papers",
                {"rid": run_id},
            )
            methods = {row["id"]: (row["label"], row["papers"]) for row in m_rows}
            d_rows = s.run(
                "MATCH (r:Run {run_id:$rid})-[:READ]->(p:Paper)-[:EVALUATED_ON]->(d:Dataset) "
                "RETURN d.dataset_id AS id, d.label AS label, "
                "       collect(DISTINCT p.paper_id) AS papers",
                {"rid": run_id},
            )
            datasets = {row["id"]: (row["label"], row["papers"]) for row in d_rows}
            pair_rows = s.run(
                "MATCH (r:Run {run_id:$rid})-[:READ]->(p:Paper) "
                "MATCH (p)-[:USES_METHOD]->(m:Method) "
                "MATCH (p)-[:EVALUATED_ON]->(d:Dataset) "
                "RETURN DISTINCT m.method_id AS mid, d.dataset_id AS did",
                {"rid": run_id},
            )
            tried = {(row["mid"], row["did"]) for row in pair_rows}
        return methods, datasets, tried

    def calls_for(self, run_id: str) -> list[dict[str, object]]:
        """[{paper_id, year, citation_count, concept_id, label, text}] this run's papers."""
        self._connect()
        assert self._driver is not None
        with self._session() as s:
            rows = s.run(
                "MATCH (r:Run {run_id:$rid})-[:READ]->(p:Paper)-[e:CALLS_FOR]->(k:Concept) "
                "RETURN p.paper_id AS pid, p.year AS year, p.citation_count AS cc, "
                "       k.concept_id AS cid, k.label AS label, e.text AS text",
                {"rid": run_id},
            )
            return [dict(row) for row in rows]

    def weakness_clusters(self, run_id: str) -> list[dict[str, object]]:
        """[{cluster_id, label, members: [{paper_id, text, year}]}]."""
        self._connect()
        assert self._driver is not None
        with self._session() as s:
            rows = s.run(
                "MATCH (r:Run {run_id:$rid})-[:READ]->(p:Paper)-[e:HAS_LIMITATION]->(k:Concept) "
                "RETURN k.concept_id AS cid, k.label AS label, e.cluster_id AS cluster_id, "
                "       p.paper_id AS pid, e.text AS text, p.year AS year",
                {"rid": run_id},
            )
            byc: dict[str, dict[str, object]] = {}
            for row in rows:
                default: dict[str, object] = {
                    "cluster_id": row["cluster_id"], "label": row["label"], "members": [],
                }
                c = byc.setdefault(row["cid"], default)
                members = c["members"]
                assert isinstance(members, list)
                members.append({"paper_id": row["pid"], "text": row["text"], "year": row["year"]})
            return list(byc.values())

    def agreement_pairs(self, run_id: str) -> list[dict[str, object]]:
        """Every SUPPORTS/EXTENDS/REPLICATES edge between claims of two papers this run
        read — the raw material for synthesis's agreement clusters."""
        self._connect()
        assert self._driver is not None
        with self._session() as s:
            rows = s.run(
                """
                MATCH (r:Run {run_id:$rid})-[:READ]->(pa:Paper)-[:MAKES_CLAIM]->(ca:Claim)
                      -[e:SUPPORTS|EXTENDS|REPLICATES {run_id:$rid}]->(cb:Claim)
                      <-[:MAKES_CLAIM]-(pb:Paper)<-[:READ]-(r)
                RETURN pa.paper_id AS pa, pa.title AS ta, pa.year AS ya, ca.text AS claim_a,
                       pb.paper_id AS pb, pb.title AS tb, pb.year AS yb, cb.text AS claim_b,
                       type(e) AS rel_type, e.confidence AS confidence
                """,
                {"rid": run_id},
            )
            return [dict(row) for row in rows]

    def contradiction_pairs(self, run_id: str) -> list[dict[str, object]]:
        """Every CONTRADICTS edge between claims of two papers this run read."""
        self._connect()
        assert self._driver is not None
        with self._session() as s:
            rows = s.run(
                """
                MATCH (r:Run {run_id:$rid})-[:READ]->(pa:Paper)-[:MAKES_CLAIM]->(ca:Claim)
                      -[e:CONTRADICTS {run_id:$rid}]->(cb:Claim)<-[:MAKES_CLAIM]-(pb:Paper)
                      <-[:READ]-(r)
                // Papers are shared across runs, so without the run filter this also
                // returned CONTRADICTS edges judged in *other* runs over the same papers
                // (a0e32253 reported 7 where it judged 1) — into detector 5 and the report.
                WHERE ca.run_id = $rid AND cb.run_id = $rid
                RETURN pa.paper_id AS pa, pa.title AS ta, pa.year AS ya, ca.text AS claim_a,
                       pb.paper_id AS pb, pb.title AS tb, pb.year AS yb, cb.text AS claim_b,
                       e.confidence AS confidence, e.rationale AS rationale
                """,
                {"rid": run_id},
            )
            return [dict(row) for row in rows]

    def paper_attrs(self, run_id: str) -> dict[str, dict[str, object]]:
        """{paper_id: {title, year, citation_count, depth, pagerank, cluster_id}} for this
        run's read papers — one round trip for detectors that need paper metadata in bulk."""
        self._connect()
        assert self._driver is not None
        with self._session() as s:
            rows = s.run(
                "MATCH (r:Run {run_id:$rid})-[:READ]->(p:Paper) "
                "RETURN p.paper_id AS pid, p.title AS title, p.year AS year, "
                "       p.citation_count AS citation_count, p.depth AS depth, "
                "       p.pagerank AS pagerank, p.cluster_id AS cluster_id",
                {"rid": run_id},
            )
            return {
                r["pid"]: {
                    "title": r["title"],
                    "year": r["year"],
                    "citation_count": r["citation_count"],
                    "depth": r["depth"],
                    "pagerank": r["pagerank"],
                    "cluster_id": r["cluster_id"],
                }
                for r in rows
            }

    def has_resolver(self, paper_a: str, paper_b: str, after_year: int) -> dict[str, object] | None:
        """A later paper citing both P1 and P2 — resolves the conflict (detector 5)."""
        self._connect()
        assert self._driver is not None
        with self._session() as s:
            row = s.run(
                """
                MATCH (x:Paper)-[:CITES]->(a:Paper {paper_id:$pa}),
                      (x:Paper)-[:CITES]->(b:Paper {paper_id:$pb})
                WHERE coalesce(x.year, 9999) > $year
                RETURN x.paper_id AS paper_id, x.title AS title, x.year AS year LIMIT 1
                """,
                {"pa": paper_a, "pb": paper_b, "year": after_year},
            ).single()
            return dict(row) if row else None

    def write_gaps(self, run_id: str, gaps: list[RankedGap]) -> int:
        """gaps: RankedGap-like objects (DATA_MODEL.md §Gap). MERGE (:Gap) + BOUNDED_BY
        edges to every bounding paper, tagged with the role each detector assigned."""
        # Replace, don't accumulate: a re-run of the detectors must not leave the previous
        # pass's gaps behind (they surfaced as duplicate ranks, e.g. 3,3,5,5,6,6,7) — and
        # that includes a pass that now finds no gaps at all.
        self._run_write("MATCH (g:Gap {run_id:$rid}) DETACH DELETE g", rid=run_id)
        if not gaps:
            return 0
        gap_rows = [
            {
                "gap_key": f"{run_id}:{g.gap_id}",
                "gap_id": g.gap_id,
                "run_id": run_id,
                "type": g.type,
                "statement": g.statement,
                "gap_score": g.gap_score,
                "rank": g.rank,
                "found_by": list(g.found_by),
            }
            for g in gaps
        ]
        self._run_write(
            """
            UNWIND $rows AS row
            MERGE (g:Gap {gap_key: row.gap_key})
            SET g.gap_id = row.gap_id,
                g.run_id = row.run_id, g.type = row.type, g.statement = row.statement,
                g.gap_score = row.gap_score, g.rank = row.rank, g.found_by = row.found_by
            """,
            rows=gap_rows,
        )
        edge_rows = [
            {"gap_key": f"{run_id}:{g.gap_id}", "paper_id": p.paper_id, "role": p.role}
            for g in gaps
            for p in g.bounding_papers
        ]
        if edge_rows:
            self._run_write(
                """
                UNWIND $rows AS row
                MATCH (g:Gap {gap_key: row.gap_key}), (p:Paper {paper_id: row.paper_id})
                MERGE (g)-[e:BOUNDED_BY]->(p)
                SET e.role = row.role
                """,
                rows=edge_rows,
            )
        return len(gaps)

    def gaps_for(self, run_id: str) -> list[dict[str, Any]]:
        """[{gap_id, type, statement, gap_score, rank, found_by, bounding_papers}] ordered
        by rank — bounding_papers: [{paper_id, title, year, role}]. detector_score/
        entities/detail are NOT persisted (Neo4j properties can't hold GapCandidate.detail's
        nested structure) — GET /runs/{id}/gaps (api/routes/runs.py) reconstructs a
        RankedGap with detector_score defaulted to gap_score and entities/detail empty."""
        self._connect()
        assert self._driver is not None
        with self._session() as s:
            rows = s.run(
                """
                MATCH (g:Gap {run_id:$rid})
                OPTIONAL MATCH (g)-[e:BOUNDED_BY]->(p:Paper)
                WITH g, collect(CASE WHEN p IS NULL THEN NULL ELSE
                    {paper_id: p.paper_id, title: p.title, year: p.year, role: e.role} END
                ) AS bounding
                RETURN g.gap_id AS gap_id, g.type AS type, g.statement AS statement,
                       g.gap_score AS gap_score, g.rank AS rank, g.found_by AS found_by,
                       [b IN bounding WHERE b IS NOT NULL] AS bounding_papers
                ORDER BY g.rank
                """,
                {"rid": run_id},
            )
            return [dict(r) for r in rows]

    def delete_run(self, run_id: str) -> dict[str, int]:
        """Delete this run's Claims (+ their edges) and Run node; prune run_id from Papers
        and delete any Paper that no run references any more (DATA_MODEL §Consistency 3).

        Weakness Concept nodes (concept_id = "weakness:<run_id>:<cluster_id>") are deleted
        outright, not just detached — unlike real Concept/Method/Dataset nodes they are not
        shared across runs (the run_id is baked into their id), so leaving them behind after
        a `clear-run` is pure orphaned garbage, not reusable graph structure."""
        self._connect()
        if self._driver is None:
            return {}
        with self._session() as s:
            claims = s.run(
                "MATCH (c:Claim {run_id:$rid}) DETACH DELETE c RETURN count(c) AS n",
                {"rid": run_id},
            ).single()["n"]
            s.run(
                "MATCH (g:Gap {run_id:$rid}) DETACH DELETE g",
                {"rid": run_id},
            )
            s.run(
                "MATCH (k:Concept {kind:'weakness'}) "
                "WHERE k.concept_id STARTS WITH ('weakness:' + $rid + ':') "
                "DETACH DELETE k",
                {"rid": run_id},
            )
            s.run(
                "MATCH (p:Paper) WHERE $rid IN p.run_ids "
                "SET p.run_ids = [x IN p.run_ids WHERE x <> $rid]",
                {"rid": run_id},
            )
            orphans = s.run(
                "MATCH (p:Paper) WHERE size(coalesce(p.run_ids, [])) = 0 "
                "DETACH DELETE p RETURN count(p) AS n"
            ).single()["n"]
            s.run("MATCH (r:Run {run_id:$rid}) DETACH DELETE r", {"rid": run_id})
        return {"claims": claims, "orphan_papers": orphans}

    def counts(self, run_id: str) -> dict[str, int]:
        self._connect()
        assert self._driver is not None
        with self._session() as s:
            rec = s.run(
                """
                OPTIONAL MATCH (p:Paper) WHERE $run_id IN p.run_ids
                WITH collect(DISTINCT p) AS ps
                WITH ps, size(ps) AS papers
                OPTIONAL MATCH (c:Claim {run_id:$run_id})
                WITH ps, papers, count(DISTINCT c) AS claims
                OPTIONAL MATCH (a)-[cit:CITES]->(:Paper) WHERE a IN ps
                WITH papers, claims, count(cit) AS cites
                OPTIONAL MATCH (:Claim)-[rel {run_id:$run_id}]->(:Claim)
                RETURN papers, claims, cites, count(rel) AS relations
                """,
                {"run_id": run_id},
            ).single()
            return {
                "papers": rec["papers"] if rec else 0,
                "claims": rec["claims"] if rec else 0,
                "cites": rec["cites"] if rec else 0,
                "relations": rec["relations"] if rec else 0,
            }

    def health(self) -> GraphHealth:
        if not self.uri:
            return GraphHealth(configured=False, reachable=False, detail="NEO4J_URI unset")
        try:
            self._connect()
            assert self._driver is not None
            self._driver.verify_connectivity()
            procs = self._procedures()
            has_gds = any(p.startswith("gds.") for p in procs)
            has_apoc = any(p.startswith("apoc.") for p in procs)
            return GraphHealth(
                configured=True,
                reachable=True,
                has_gds=has_gds,
                has_apoc=has_apoc,
                detail="ok" if has_gds else "reachable, but GDS not installed",
            )
        except Exception as e:
            return GraphHealth(configured=True, reachable=False, detail=f"{type(e).__name__}: {e}")


def health() -> GraphHealth:
    store = GraphStore()
    try:
        return store.health()
    finally:
        store.close()
