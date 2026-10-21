"""Job B — verbatim claim extraction, section by section.

For each usable section: window it if it is very long (a flat PyMuPDF doc is one giant
section), ask the model for claims (`claims.v1.md`), stamp identity fields, then run every
claim through the grounding gate. Ungrounded claims are dropped and counted, never repaired.

Claim `quote_char_start` / `quote_char_end` are shifted to index the doc's `full_text`
(section offset + window offset), so the UI can highlight the exact span.

An LLM failure on one window is logged and skipped — it never stops the loop.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import structlog

from atlas.contracts import Claim, PaperMeta, ParsedDoc
from atlas.extract.grounding import verify_all
from atlas.llm.client import LLMClient
from atlas.llm.schemas import render_prompt

log = structlog.get_logger(__name__)

MIN_SECTION_CHARS = 200
WINDOW_CHARS = 8000
WINDOW_OVERLAP = 400
MAX_WINDOWS = 4
SKIP_SECTIONS = frozenset({"related"})


@dataclass
class ClaimHarvest:
    kept: list[Claim]
    n_extracted: int
    n_dropped: int
    n_failed_calls: int = 0
    dropped: list[Claim] = field(default_factory=list)


def _windows(text: str) -> list[tuple[int, str]]:
    """[(start_offset_in_text, window_text)] — one entry unless the section is huge."""
    if len(text) <= WINDOW_CHARS:
        return [(0, text)]
    out: list[tuple[int, str]] = []
    step = WINDOW_CHARS - WINDOW_OVERLAP
    for start in range(0, len(text), step):
        out.append((start, text[start : start + WINDOW_CHARS]))
        if len(out) >= MAX_WINDOWS:
            break
    return out


def _stamp(raw: object, paper_id: str, section: str) -> Claim:
    claim: Claim = raw  # type: ignore[assignment]
    return claim.model_copy(
        update={"claim_id": str(uuid.uuid4()), "paper_id": paper_id, "section": section}
    )


def _shift(claim: Claim, delta: int) -> Claim:
    if claim.quote_char_start is None or claim.quote_char_end is None:
        return claim
    return claim.model_copy(
        update={
            "quote_char_start": claim.quote_char_start + delta,
            "quote_char_end": claim.quote_char_end + delta,
        }
    )


def extract_claims(doc: ParsedDoc, paper: PaperMeta, *, client: LLMClient) -> ClaimHarvest:
    kept: list[Claim] = []
    all_dropped: list[Claim] = []
    seen_quotes: set[str] = set()
    extracted = 0
    dropped = 0
    failed = 0

    for sec in doc.sections:
        if len(sec.text) < MIN_SECTION_CHARS or sec.name in SKIP_SECTIONS:
            continue
        for win_start, win_text in _windows(sec.text):
            prompt = render_prompt(
                "claims.v1.md",
                title=paper.title,
                year=paper.year if paper.year is not None else "n/a",
                venue=paper.venue or "n/a",
                section_name=sec.name,
                section_text=win_text,
            )
            try:
                result = client.complete(
                    "claims",
                    messages=[{"role": "user", "content": prompt}],
                    response_model=list[Claim],
                )
            except Exception as e:  # one window's failure must not stop the run
                failed += 1
                log.warning(
                    "claims.call_failed", paper_id=paper.paper_id, section=sec.name, error=str(e)
                )
                continue

            stamped = [_stamp(c, paper.paper_id, sec.name) for c in list(result.value)]
            extracted += len(stamped)
            verified, window_dropped = verify_all(stamped, win_text)
            dropped += len(window_dropped)
            all_dropped.extend(window_dropped)
            for c in verified:
                if c.quote in seen_quotes:
                    continue
                seen_quotes.add(c.quote)
                kept.append(_shift(c, sec.char_start + win_start))

    log.info(
        "claims.extracted",
        paper_id=paper.paper_id,
        extracted=extracted,
        kept=len(kept),
        dropped=dropped,
        failed_calls=failed,
    )
    return ClaimHarvest(
        kept=kept, n_extracted=extracted, n_dropped=dropped, n_failed_calls=failed,
        dropped=all_dropped,
    )
