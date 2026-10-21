"""LLM job registry — prompt loading + typed dispatch.

Four jobs, each: a prompt file (versioned, name enters the cache key), a set of template
variables, and a Pydantic output model from `contracts.py`. Nothing here inlines a prompt
string — they live in `config/prompts/`.

| job       | prompt                | output          |
|-----------|-----------------------|-----------------|
| keywords  | keywords.v1.md        | QueryPlan       |
| claims    | claims.v1.md          | list[Claim]     |
| judge     | judge.v1.md           | Relation        |
| synthesis | synthesis.v1.md       | Report          |
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from atlas.contracts import QueryPlan, Relation, Report
from atlas.llm.client import LLMClient

PROMPT_DIR = Path("config/prompts")

T = TypeVar("T", bound=BaseModel)

# job -> output model. `claims` returns a list and is handled by its caller in Phase 3.
JOB_OUTPUT: dict[str, type[BaseModel]] = {
    "keywords": QueryPlan,
    "judge": Relation,
    "synthesis": Report,
}


def render_prompt(filename: str, /, **variables: Any) -> str:
    """Load a prompt file and substitute {name} placeholders.

    Uses plain replacement, not str.format — prompt bodies contain literal braces
    (fenced code blocks, JSON examples) that would break formatting.
    """
    text = (PROMPT_DIR / filename).read_text(encoding="utf-8")
    for key, value in variables.items():
        text = text.replace("{" + key + "}", str(value))
    return text


def run_job(
    client: LLMClient,
    job: str,
    response_model: type[T],
    **variables: Any,
) -> T:
    """Render the job's prompt with `variables` and return its structured output."""
    filename = client.routing.prompt_file(job)
    prompt = render_prompt(filename, **variables)
    result = client.complete(
        job,
        messages=[{"role": "user", "content": prompt}],
        response_model=response_model,
    )
    return result.value  # type: ignore[no-any-return]


def expand_query(client: LLMClient, query: str) -> QueryPlan:
    """Job A — one research question -> a tiered keyword search plan."""
    plan = run_job(client, "keywords", QueryPlan, query=query)
    # the model sometimes omits/rewrites the query field; pin it to what was asked.
    if plan.query != query:
        plan = plan.model_copy(update={"query": query})
    return plan


__all__ = ["JOB_OUTPUT", "expand_query", "render_prompt", "run_job"]
