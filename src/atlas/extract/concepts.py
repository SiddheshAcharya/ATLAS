"""Concept / method / dataset / limitation / future-work extraction (Phase 5, R4).

Local only — spaCy noun chunks generate candidates, KeyBERT ranks them by relevance to
the document, no LLM call (TECH_STACK: domain-general, works for IoT and biomedical
alike). Normalization is what keeps the gap detectors honest (R4 tripwire): lowercase +
lemmatize, the hand-curated alias file first, then embedding-agglomerative clustering at
cosine >= 0.85; the canonical label is the most frequent observed surface form.

Section-scoped extraction (methods / datasets / limitations / future work) needs real
section boundaries, which only GROBID gives us (ADR-005). Without it (`structure` !=
"grobid" — the common case on the lightweight path) we fall back to scanning the whole
text for limitation/future-work *cue phrases*; method/dataset extraction is skipped
rather than guessed, since there is no boundary to scope it to.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
import yaml

if TYPE_CHECKING:
    from atlas.llm.client import LLMClient

log = structlog.get_logger(__name__)

_SECTIONED = frozenset(
    {"intro", "related", "methods", "results", "discussion",
     "limitations", "future_work", "conclusion"}
)

ALIASES_PATH = Path("config/concept_aliases.yaml")
CLUSTER_FLOOR = 0.85

_STOPWORD_HEADS = frozenset(
    {"paper", "study", "work", "approach", "method", "system", "result", "results",
     "section", "figure", "table", "author", "authors"}
)
_DETERMINERS = frozenset(
    {"a", "an", "the", "this", "that", "these", "those", "our", "their", "its", "his", "her"}
)
_LIMITATION_CUES = (
    "limitation", "however,", "threat to validity", "drawback", "shortcoming",
    "does not", "did not evaluate", "small sample", "further validation", "constrained by",
)
_FUTURE_CUES = (
    "future work", "future research", "we plan to", "we intend to", "in future",
    "further work", "remains to be", "an open problem", "would be interesting",
    "future direction", "left for future",
)
_DATASET_CUES = (
    "dataset", "data set", "corpus", "benchmark", "participants", "trial", "trials",
    "deployment", "testbed", "prototype", "field study", "field trial", "cohort",
)


@dataclass
class ExtractedPaper:
    paper_id: str
    concepts: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    datasets: list[str] = field(default_factory=list)
    limitation_sentences: list[str] = field(default_factory=list)
    future_work_sentences: list[str] = field(default_factory=list)


# ── local NLP singletons ────────────────────────────────────────────────────

_nlp_singleton: Any = None
_kb_singleton: Any = None


def _nlp() -> Any:
    global _nlp_singleton
    if _nlp_singleton is None:
        import spacy

        # keep parser (noun_chunks + sentence boundaries) and lemmatizer (_lemma());
        # ner is the only pipe we don't use.
        _nlp_singleton = spacy.load("en_core_web_sm", disable=["ner"])
    return _nlp_singleton


def _keybert() -> Any:
    global _kb_singleton
    if _kb_singleton is None:
        from keybert import KeyBERT

        from atlas.ingest.embed import get_model

        _kb_singleton = KeyBERT(model=get_model())
    return _kb_singleton


# ── phrase / sentence extraction ────────────────────────────────────────────


def _clean_phrase(text: str) -> str | None:
    t = "".join(c if (c.isalnum() or c in " -") else " " for c in text.lower())
    words = [w for w in t.split(" ") if w]
    while words and words[0] in _DETERMINERS:
        words = words[1:]
    if not (1 <= len(words) <= 5):
        return None
    cleaned = " ".join(words)
    if len(cleaned) < 3 or cleaned.isdigit():
        return None
    if words[-1] in _STOPWORD_HEADS and len(words) <= 2:
        return None
    return cleaned


def extract_phrases(text: str, *, top_n: int = 12) -> list[str]:
    """Noun-chunk candidates (spaCy), ranked by document relevance (KeyBERT)."""
    if not text or len(text) < 40:
        return []
    doc = _nlp()(text[:5000])
    seen: set[str] = set()
    candidates: list[str] = []
    for chunk in doc.noun_chunks:
        p = _clean_phrase(chunk.text)
        if p and p not in seen:
            seen.add(p)
            candidates.append(p)
    if not candidates:
        return []
    try:
        # keyphrase_ngram_range must cover our candidates' length even though `candidates`
        # is supplied — KeyBERT's default (1,1) silently drops multi-word candidates.
        scored = _keybert().extract_keywords(
            text[:5000], candidates=candidates, keyphrase_ngram_range=(1, 5), top_n=top_n
        )
        ranked = [p for p, _ in scored]
        return ranked or candidates[:top_n]
    except Exception as e:  # KeyBERT/model failure must not break extraction
        log.warning("concepts.keybert_failed", error=str(e))
        return candidates[:top_n]


def _sentences(text: str) -> list[str]:
    if not text:
        return []
    doc = _nlp()(text[:8000])
    return [s.text.strip() for s in doc.sents if 20 <= len(s.text.strip()) <= 400]


def _cue_sentences(text: str, cues: tuple[str, ...]) -> list[str]:
    return [s for s in _sentences(text) if any(c in s.lower() for c in cues)]


def extract_from_sections(
    paper_id: str, sections: dict[str, str], *, structure: str
) -> ExtractedPaper:
    ep = ExtractedPaper(paper_id=paper_id)
    all_text = "\n\n".join(t for t in sections.values() if t)
    ep.concepts = extract_phrases(all_text, top_n=15)

    if structure == "grobid":
        methods_text = sections.get("methods", "")
        if methods_text:
            ep.methods = extract_phrases(methods_text, top_n=8)
            ds_source = " ".join(
                _cue_sentences(methods_text, _DATASET_CUES)
                + _cue_sentences(sections.get("results", ""), _DATASET_CUES)
            )
            ep.datasets = extract_phrases(ds_source, top_n=6) if ds_source.strip() else []
        limitations_text = sections.get("limitations") or sections.get("discussion") or ""
        ep.limitation_sentences = _cue_sentences(limitations_text, _LIMITATION_CUES)
        future_text = sections.get("future_work") or sections.get("conclusion") or ""
        ep.future_work_sentences = _cue_sentences(future_text, _FUTURE_CUES)
    else:
        # no real section boundaries (PyMuPDF flat / abstract-only) — cue-phrase fallback
        # over whatever text exists, so detectors 4/6 are not *always* empty without GROBID.
        ep.limitation_sentences = _cue_sentences(all_text, _LIMITATION_CUES)
        ep.future_work_sentences = _cue_sentences(all_text, _FUTURE_CUES)

    return ep


# ── normalization (R4) ───────────────────────────────────────────────────────


def _lemma(phrase: str) -> str:
    doc = _nlp()(phrase)
    return " ".join(t.lemma_.lower() for t in doc if not t.is_punct and not t.is_space).strip()


@lru_cache
def _alias_map() -> dict[str, str]:
    if not ALIASES_PATH.exists():
        return {}
    raw = yaml.safe_load(ALIASES_PATH.read_text(encoding="utf-8")) or {}
    out: dict[str, str] = {}
    for canonical, variants in raw.items():
        canon = str(canonical).lower()
        out[canon] = canon
        for v in variants or []:
            out[_lemma(str(v))] = canon
    return out


def _cluster_by_cosine(items: list[str], vecs: list[list[float]], floor: float) -> list[list[int]]:
    if len(items) < 2:
        return [[0]] if items else []
    from sklearn.cluster import AgglomerativeClustering

    model = AgglomerativeClustering(
        n_clusters=None, distance_threshold=1.0 - floor, metric="cosine", linkage="average"
    )
    labels = model.fit_predict(vecs)
    groups: dict[int, list[int]] = {}
    for i, lab in enumerate(labels):
        groups.setdefault(int(lab), []).append(i)
    return list(groups.values())


def normalize_phrases(
    occurrences: list[str], *, cluster_floor: float = CLUSTER_FLOOR
) -> dict[str, str]:
    """Every raw phrase occurrence -> its canonical label.

    Alias file first (`config/concept_aliases.yaml`), then embedding-agglomerative
    clustering at cosine >= `cluster_floor`. The canonical label is the most frequent
    observed surface form inside its cluster (GAP_DETECTORS.md §1 guard).
    """
    if not occurrences:
        return {}
    aliases = _alias_map()
    freq = Counter(occurrences)
    mapping: dict[str, str] = {}
    unresolved: list[str] = []
    for p in freq:
        lem = _lemma(p)
        if lem in aliases:
            mapping[p] = aliases[lem]
        else:
            unresolved.append(p)

    if unresolved:
        uniq = sorted(set(unresolved))
        if len(uniq) == 1:
            mapping[uniq[0]] = uniq[0]
        else:
            from atlas.ingest.embed import embed_texts

            vecs = embed_texts(uniq)
            for idxs in _cluster_by_cosine(uniq, vecs, cluster_floor):
                members = [uniq[i] for i in idxs]
                canonical = max(members, key=lambda m: freq[m])
                for m in members:
                    mapping[m] = canonical
    return mapping


def _slugify(label: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return s or "x"


# ── orchestration: run the whole pass over one finished run ─────────────────


@dataclass
class ConceptExtractionReport:
    run_id: str
    papers_processed: int
    concepts: int
    methods: int
    datasets: int
    weakness_clusters: int
    calls: int
    top_concepts: list[tuple[str, int]] = field(default_factory=list)  # (label, df), R4


def _reconstruct_sections(paper_id: str, run_id: str) -> tuple[dict[str, str], bool]:
    from atlas.store import vector

    chunks = vector.get_chunks_by_paper(paper_id, run_id=run_id)
    sections: dict[str, str] = {}
    for c in chunks:
        sec = str(c.get("section") or "other")
        sections[sec] = (sections.get(sec, "") + " " + str(c.get("text") or "")).strip()
    return sections, any(s in _SECTIONED for s in sections)


def _first_author_group(paper_id: str) -> str:
    from atlas.store.db import get_paper

    paper = get_paper(paper_id)
    if paper is not None and paper.authors:
        name = paper.authors[0].name or ""
        surname = name.strip().split(" ")[-1].lower() if name.strip() else ""
        return surname or "unknown"
    return "unknown"


def _label_weakness_cluster(sentences: list[str], client: LLMClient) -> str:
    from pydantic import BaseModel, Field

    from atlas.llm.schemas import render_prompt

    class ClusterLabel(BaseModel):
        label: str = Field(max_length=80)

    phrase_counts = Counter(p for s in sentences for p in extract_phrases(s, top_n=3))
    fallback = phrase_counts.most_common(1)[0][0] if phrase_counts else sentences[0][:60]
    try:
        prompt = render_prompt(
            "label_cluster.v1.md", sentences="\n".join(f"- {s}" for s in sentences[:12])
        )
        result = client.complete(
            "label_cluster", messages=[{"role": "user", "content": prompt}],
            response_model=ClusterLabel,
        )
        label: ClusterLabel = result.value
        return label.label.strip().rstrip(".")
    except Exception as e:  # a labeling failure must not lose the cluster's gap signal
        log.warning("concepts.label_cluster_failed", error=str(e))
        return str(fallback)


def _cluster_weaknesses(
    items: list[tuple[str, str]],
    *,
    client: LLMClient,
    min_cluster_size: int,
    min_papers: int,
    min_author_groups: int,
) -> list[dict[str, Any]]:
    """items: [(paper_id, limitation_sentence)]. HDBSCAN over sentence embeddings, kept
    only if it spans >= min_papers distinct papers from >= min_author_groups author
    groups (GAP_DETECTORS.md §6) — otherwise it's one lab repeating itself, not a
    field-level weakness."""
    if len(items) < min_cluster_size:
        return []
    import hdbscan
    import numpy as np

    from atlas.ingest.embed import embed_texts

    sentences = [s for _, s in items]
    vecs = np.array(embed_texts(sentences))
    labels = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size).fit_predict(vecs)

    groups: dict[int, list[int]] = {}
    for i, lab in enumerate(labels):
        if lab != -1:
            groups.setdefault(int(lab), []).append(i)

    out: list[dict[str, Any]] = []
    for cid, idxs in groups.items():
        member_papers = {items[i][0] for i in idxs}
        if len(member_papers) < min_papers:
            continue
        authors = {_first_author_group(pid) for pid in member_papers}
        if len(authors) < min_author_groups:
            continue
        member_sentences = [sentences[i] for i in idxs]
        out.append(
            {
                "cluster_id": cid,
                "label": _label_weakness_cluster(member_sentences, client),
                "members": [{"paper_id": items[i][0], "text": sentences[i]} for i in idxs],
            }
        )
    log.info(
        "concepts.weakness_clusters", candidates=len(groups), kept=len(out), sentences=len(items)
    )
    return out


def extract_and_store(run_id: str, *, client: LLMClient | None = None) -> ConceptExtractionReport:
    """The Phase 5 extraction pass: pull this run's read papers' chunk text, extract
    concepts/methods/datasets/limitations/future-work, normalize, write to Neo4j."""
    from atlas.config_files import scoring
    from atlas.forage.frontier import read_paper_ids
    from atlas.llm.client import LLMClient as _LLMClient
    from atlas.store.graph import GraphStore

    client = client or _LLMClient()
    cfg = scoring()["gaps"]["thresholds"]

    paper_ids = read_paper_ids(run_id)
    per_paper: dict[str, ExtractedPaper] = {}
    for pid in paper_ids:
        sections, structured = _reconstruct_sections(pid, run_id)
        if not sections:
            continue
        ep = extract_from_sections(pid, sections, structure="grobid" if structured else "flat")
        per_paper[pid] = ep
    log.info("concepts.papers_reconstructed", run_id=run_id, n=len(per_paper), of=len(paper_ids))

    concept_map = normalize_phrases([p for ep in per_paper.values() for p in ep.concepts])
    method_map = normalize_phrases([p for ep in per_paper.values() for p in ep.methods])
    dataset_map = normalize_phrases([p for ep in per_paper.values() for p in ep.datasets])

    concept_rows: list[dict[str, Any]] = []
    method_rows: list[dict[str, Any]] = []
    dataset_rows: list[dict[str, Any]] = []
    call_rows: list[dict[str, Any]] = []

    for pid, ep in per_paper.items():
        counts = Counter(concept_map[p] for p in ep.concepts if p in concept_map)
        total = sum(counts.values()) or 1
        for canon, tf in counts.most_common():
            concept_rows.append(
                {"paper_id": pid, "concept_id": f"concept:{_slugify(canon)}", "label": canon,
                 "tf": tf, "salience": round(tf / total, 4)}
            )
        for canon in {method_map[p] for p in ep.methods if p in method_map}:
            method_rows.append(
                {"paper_id": pid, "method_id": f"method:{_slugify(canon)}", "label": canon}
            )
        for canon in {dataset_map[p] for p in ep.datasets if p in dataset_map}:
            dataset_rows.append(
                {"paper_id": pid, "dataset_id": f"dataset:{_slugify(canon)}", "label": canon}
            )
        for sentence in ep.future_work_sentences:
            for phrase in extract_phrases(sentence, top_n=3):
                canon = concept_map.get(phrase, phrase)
                call_rows.append(
                    {"paper_id": pid, "concept_id": f"concept:{_slugify(canon)}",
                     "label": canon, "text": sentence}
                )

    limitation_items = [
        (pid, s) for pid, ep in per_paper.items() for s in ep.limitation_sentences
    ]
    weakness_clusters = _cluster_weaknesses(
        limitation_items,
        client=client,
        min_cluster_size=int(cfg["weakness_min_cluster_size"]),
        min_papers=int(cfg["weakness_min_papers"]),
        min_author_groups=int(cfg["weakness_min_author_groups"]),
    )

    graph = GraphStore()
    try:
        graph.write_concepts(concept_rows)
        graph.write_methods(method_rows)
        graph.write_datasets(dataset_rows)
        graph.write_calls(call_rows)
        graph.write_weakness_clusters(run_id, weakness_clusters)
    finally:
        graph.close()

    top = Counter(r["label"] for r in concept_rows).most_common(100)
    report = ConceptExtractionReport(
        run_id=run_id,
        papers_processed=len(per_paper),
        concepts=len({r["concept_id"] for r in concept_rows}),
        methods=len({r["method_id"] for r in method_rows}),
        datasets=len({r["dataset_id"] for r in dataset_rows}),
        weakness_clusters=len(weakness_clusters),
        calls=len(call_rows),
        top_concepts=top,
    )
    log.info(
        "concepts.done", run_id=run_id, papers=report.papers_processed,
        concepts=report.concepts, methods=report.methods, datasets=report.datasets,
        weakness_clusters=report.weakness_clusters, calls=report.calls,
    )
    return report
