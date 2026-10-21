"""R2 tripwire — measure judge precision against a hand-labelled set.

`export_pairs` dumps judged pairs (both claims + the model verdict) as JSONL with an
empty `gold` field. A human fills `gold` for ~60 pairs (12 per label), then `score`
reports per-label precision / recall and the confusion matrix. The table is a
results-chapter artefact, not throwaway work (TESTING.md E5).

A single small run rarely has 12 pairs of every label — CONTRADICTS/REPLICATES are
naturally rare ("most pairs are unrelated", judge.v1.md). `export_pairs` accepts pairs
pooled from multiple runs (the caller concatenates `db.judged_pairs(run_id)` lists) and
`--per-label` stratified-samples down to a manageable, balanced file to hand-label.
"""

from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

LABELS = ["SUPPORTS", "CONTRADICTS", "EXTENDS", "REPLICATES", "DIFF_SCOPE", "UNRELATED"]
_SEED = 42  # reproducible sample — R9's spirit applies to evaluation artefacts too


def stratified_sample(rows: list[dict[str, Any]], *, per_label: int) -> list[dict[str, Any]]:
    """Up to `per_label` rows per relation `type`, randomly chosen but reproducible.
    A label with fewer than `per_label` rows contributes all of them — say so plainly in
    the report rather than padding to a false-looking 12."""
    by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_label[r.get("type", "")].append(r)
    rng = random.Random(_SEED)
    out: list[dict[str, Any]] = []
    for lab in LABELS:
        pool = by_label.get(lab, [])
        out.extend(rng.sample(pool, min(per_label, len(pool))))
    return out


def export_pairs(rows: list[dict[str, Any]], path: Path, *, per_label: int | None = None) -> int:
    """`rows` come from one or more db.judged_pairs(run_id) calls, concatenated by the
    caller. One JSON object per line."""
    if per_label is not None:
        rows = stratified_sample(rows, per_label=per_label)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps({**r, "gold": ""}, ensure_ascii=False) + "\n")
    return len(rows)


def score(path: Path) -> dict[str, Any]:
    """Read a labelled JSONL (`type` = model, `gold` = human) -> precision/recall table."""
    labelled = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    labelled = [r for r in labelled if r.get("gold")]
    if not labelled:
        return {"n": 0, "error": "no rows with a `gold` label"}

    confusion: dict[tuple[str, str], int] = Counter()
    for r in labelled:
        confusion[(r["gold"], r["type"])] += 1

    per_label: dict[str, dict[str, float]] = {}
    for lab in LABELS:
        tp = confusion[(lab, lab)]
        fp = sum(confusion[(g, lab)] for g in LABELS if g != lab)
        fn = sum(confusion[(lab, p)] for p in LABELS if p != lab)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        support = tp + fn
        if support:
            per_label[lab] = {
                "precision": round(prec, 3),
                "recall": round(rec, 3),
                "support": support,
            }

    accuracy = sum(confusion[(lab, lab)] for lab in LABELS) / len(labelled)
    matrix: dict[str, dict[str, int]] = defaultdict(dict)
    for (g, p), n in confusion.items():
        matrix[g][p] = n
    return {
        "n": len(labelled),
        "accuracy": round(accuracy, 3),
        "per_label": per_label,
        "confusion": {g: dict(row) for g, row in matrix.items()},
    }


def _claim_row(claim_id: str | None, text: str, quote: str) -> Any:
    """The stored claim behind one side of a labelled pair. Newer exports carry the claim id;
    older sheets (evaluation/e5_sample.jsonl) only carry text + quote, which identify a claim
    just as well because quotes are verbatim spans of one paper."""
    import sqlalchemy as sa

    from atlas.store.db import ClaimRow, session_scope

    with session_scope() as s:
        if claim_id:
            row = s.get(ClaimRow, claim_id)
            if row is not None:
                s.expunge(row)
                return row
        row = s.execute(
            sa.select(ClaimRow).where(ClaimRow.text == text, ClaimRow.quote == quote).limit(1)
        ).scalar_one_or_none()
        if row is not None:
            s.expunge(row)
        return row


def rejudge(rows: list[dict[str, Any]], client: Any) -> tuple[list[dict[str, Any]], int]:
    """Re-run the *current* judge prompt (config/models.yaml `prompts.judge`) on every pair of
    a labelled sheet, keeping `gold`. The old verdict moves to `prev_type`, so one sheet
    measures a prompt change on exactly the same pairs. Returns (rows, pairs_not_found)."""
    from atlas.contracts import Claim, ClaimScope
    from atlas.judge.pairing import Pair
    from atlas.judge.relations import judge_pairs
    from atlas.store import db

    out: list[dict[str, Any]] = []
    missing = 0
    for r in rows:
        a = _claim_row(r.get("a_claim_id"), r.get("a_text", ""), r.get("a_quote", ""))
        b = _claim_row(r.get("b_claim_id"), r.get("b_text", ""), r.get("b_quote", ""))
        if a is None or b is None:
            missing += 1
            out.append(
                {**r, "prev_type": r.get("type"), "type": "", "rejudge_error": "claim not found"}
            )
            continue
        papers = {p.paper_id: p for p in (db.get_paper(a.paper_id), db.get_paper(b.paper_id)) if p}
        claim_a = Claim(
            claim_id=a.claim_id,
            paper_id=a.paper_id,
            text=a.text,
            quote=a.quote,
            section=a.section or "other",
            scope=ClaimScope(**(a.scope or {"what_was_tested": ""})),
        )
        b_payload = {
            "claim_id": b.claim_id,
            "paper_id": b.paper_id,
            "text": b.text,
            "quote": b.quote,
            "scope": b.scope,
            "year": papers[b.paper_id].year if b.paper_id in papers else None,
        }
        rels = judge_pairs([Pair(claim_a, b_payload, 0.0)], client, "judge-eval", papers=papers)
        if not rels:
            out.append(
                {**r, "prev_type": r.get("type"), "type": "", "rejudge_error": "judge call failed"}
            )
            continue
        v = rels[0]
        out.append(
            {
                **r,
                "prev_type": r.get("type"),
                "type": v.type,
                "confidence": v.confidence,
                "rationale": v.rationale,
                "judged_by": v.judged_by,
                "a_claim_id": a.claim_id,
                "b_claim_id": b.claim_id,
            }
        )
    return out, missing
