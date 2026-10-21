"""`POST /runs/{run_id}/chat` — grounded Q&A (docs/API.md §Grounded chat).

The one endpoint where scope creep is most tempting and most damaging (API.md's own
words). Rules enforced here, not by prompt instruction:

1. Retrieval is hard-filtered to `run_id`, server-side, via vector.search_claims()'s own
   run_id filter — never a prompt instruction the model could ignore.
2. The prompt receives only retrieved claim snippets with their paper_ids.
3. citations[] is built from the retrieved snippets themselves, not parsed out of the
   model's prose — the same "don't trust the LLM with the citation list" pattern
   synthesis/report.py uses. cited_paper_ids the model returns are filtered against the
   actual retrieved set so a hallucinated id can't leak into citations[].
4. If retrieval returns nothing above the similarity floor, the canned refusal is
   returned directly — no LLM call at all, so there is no way for the model to fall back
   on its own parametric knowledge.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter
from pydantic import BaseModel

from atlas.config_files import scoring
from atlas.contracts import ChatCitation, ChatMessage, ChatRequest, ChatResponse
from atlas.ingest.embed import embed_query
from atlas.llm.client import LLMClient
from atlas.llm.schemas import render_prompt
from atlas.store import db, vector

log = structlog.get_logger(__name__)
router = APIRouter(tags=["chat"])

_TOP_K = 8
_REFUSAL = "ATLAS did not read anything that addresses this."


class _ChatLLMOutput(BaseModel):
    answer: str
    cited_paper_ids: list[str] = []


def _render_history(history: list[ChatMessage]) -> str:
    if not history:
        return "(no prior turns)"
    return "\n".join(f"{m.role}: {m.content}" for m in history[-6:])


def _render_snippets(snippets: list[dict[str, object]]) -> str:
    lines = []
    for s in snippets:
        lines.append(f'- paper_id={s["paper_id"]!r} ({s.get("year", "n.d.")}): "{s["quote"]}"')
    return "\n".join(lines)


@router.post("/runs/{run_id}/chat", response_model=ChatResponse)
def chat(run_id: str, body: ChatRequest) -> ChatResponse:
    floor = float(scoring()["judging"]["similarity_floor"])
    qvec = embed_query(body.message)
    hits = vector.search_claims(qvec, run_id=run_id, k=_TOP_K, floor=floor)

    if not hits:
        log.info("api.chat_no_retrieval", run_id=run_id)
        return ChatResponse(answer=_REFUSAL, citations=[])

    prompt = render_prompt(
        "chat.v1.md",
        history=_render_history(body.history),
        question=body.message,
        snippets=_render_snippets(hits),
    )
    client = LLMClient(run_id=run_id)
    result = client.complete(
        "chat", messages=[{"role": "user", "content": prompt}], response_model=_ChatLLMOutput
    )
    out: _ChatLLMOutput = result.value

    retrieved_ids = {str(h["paper_id"]) for h in hits}
    by_paper: dict[str, dict[str, object]] = {}
    for h in hits:
        by_paper.setdefault(str(h["paper_id"]), h)

    cited = [pid for pid in out.cited_paper_ids if pid in retrieved_ids] or list(retrieved_ids)
    citations = []
    for pid in cited:
        paper = db.get_paper(pid)
        citations.append(
            ChatCitation(
                paper_id=pid,
                title=paper.title if paper is not None else pid,
                quote=str(by_paper[pid].get("quote") or "") or None,
            )
        )
    return ChatResponse(answer=out.answer, citations=citations)
