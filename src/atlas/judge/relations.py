"""Job C — 5-way relation judging.

One candidate pair -> one `Relation` (SUPPORTS / CONTRADICTS / EXTENDS / REPLICATES /
DIFF_SCOPE / UNRELATED). `DIFF_SCOPE` and `UNRELATED` are first-class answers — a judge
that never says them is guessing (R2). One pair per call for now; batching is an
optimisation for the strong PC. A failed call is logged and skipped, never fatal.
"""

from __future__ import annotations

from typing import Any

import structlog
from pydantic import BaseModel, Field

from atlas.contracts import PaperMeta, Relation, RelationType
from atlas.judge.pairing import Pair
from atlas.llm.client import LLMClient
from atlas.llm.schemas import render_prompt

log = structlog.get_logger(__name__)


class RelationVerdict(BaseModel):
    type: RelationType
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(max_length=400)


def _scope_str(scope: Any) -> str:
    d = scope.model_dump() if hasattr(scope, "model_dump") else (scope or {})
    parts = [f"{k}={v}" for k, v in d.items() if v]
    return "; ".join(parts) if parts else "(not specified)"


def _year(pid: str, papers: dict[str, PaperMeta] | None, fallback: Any = None) -> str:
    if papers and pid in papers and papers[pid].year is not None:
        return str(papers[pid].year)
    return str(fallback) if fallback is not None else "n/a"


def _title(pid: str, papers: dict[str, PaperMeta] | None) -> str:
    if papers and pid in papers:
        return papers[pid].title
    return pid


def judge_pairs(
    pairs: list[Pair],
    client: LLMClient,
    run_id: str,
    *,
    papers: dict[str, PaperMeta] | None = None,
    max_calls: int | None = None,
) -> list[Relation]:
    out: list[Relation] = []
    calls = 0
    for p in pairs:
        if max_calls is not None and calls >= max_calls:
            log.info("judge.call_budget_reached", run_id=run_id, made=calls)
            break
        b_id = str(p.b.get("claim_id") or "")
        b_pid = str(p.b.get("paper_id") or "")
        prompt = render_prompt(
            client.routing.prompt_file("judge"),  # config/models.yaml `prompts:` — one place
            paper_a_title=_title(p.a.paper_id, papers),
            paper_a_year=_year(p.a.paper_id, papers),
            claim_a_text=p.a.text,
            claim_a_quote=p.a.quote,
            claim_a_scope=_scope_str(p.a.scope),
            paper_b_title=_title(b_pid, papers),
            paper_b_year=_year(b_pid, papers, p.b.get("year")),
            claim_b_text=p.b.get("text", ""),
            claim_b_quote=p.b.get("quote", ""),
            claim_b_scope=_scope_str(p.b.get("scope")),
        )
        calls += 1
        try:
            res = client.complete(
                "judge",
                messages=[{"role": "user", "content": prompt}],
                response_model=RelationVerdict,
            )
        except Exception as e:  # a bad pair must not stop the loop
            log.warning("judge.call_failed", run_id=run_id, error=str(e))
            continue
        v: RelationVerdict = res.value
        out.append(
            Relation(
                source_claim_id=p.a.claim_id,
                target_claim_id=b_id,
                type=v.type,
                confidence=v.confidence,
                rationale=v.rationale[:400],
                judged_by=res.meta.model,
                run_id=run_id,
            )
        )
    labels: dict[str, int] = {}
    for r in out:
        labels[r.type] = labels.get(r.type, 0) + 1
    log.info("judge.done", run_id=run_id, calls=calls, verdicts=len(out), by_label=labels)
    return out


def contradiction_count(relations: list[Relation], min_confidence: float) -> int:
    return sum(
        1 for r in relations if r.type == "CONTRADICTS" and r.confidence >= min_confidence
    )
