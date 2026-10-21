"""The grounding gate (ADR-007).

Every claim carries a quote that must match the source character-for-character after
normalization. Failures are DROPPED. There is no repair path, no re-ask, no
"confidence: low" passthrough. This is the project's integrity guarantee and the
single most important function in the codebase.

Expect 10-25% of extracted claims to be dropped early. That is correct behaviour —
report the number, it is a strength.
"""

from __future__ import annotations

import re

import structlog
from rapidfuzz import fuzz

from atlas.contracts import Claim
from atlas.ingest.normalize import normalize_text

log = structlog.get_logger(__name__)

MIN_QUOTE_CHARS = 15   # shorter than this is not evidence
MAX_QUOTE_CHARS = 400  # longer than this is the model copying a paragraph to game the check
FUZZY_THRESHOLD = 97.0

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def _numbers_preserved(quote: str, matched_span: str) -> bool:
    """Every numeric token in the quote must appear in the matched source span.

    Without this, the fuzzy path is a fabrication hole: changing "1.8 seconds" to
    "0.8 seconds" in a 56-character quote still scores ~99 on partial_ratio and would
    pass. A single altered digit is exactly the failure the gate exists to catch, so
    numbers get an exact check even when the surrounding text is matched fuzzily.
    """
    q = _NUMBER.findall(quote)
    if not q:
        return True
    s = _NUMBER.findall(matched_span)
    return all(n in s for n in q)


_IGNORABLE = frozenset("'\"`")
_HYPHENS = frozenset({"-", chr(0x2010), chr(0x2011)})  # NFKC maps U+2011 to U+2010, not "-"
_EDGE_PUNCT = ".,;:"
# numbered reference markers: [7], [12, 13], [3-5]
_CITATION_MARKER = re.compile(r"\[\d{1,3}(?:\s*[,;-]\s*\d{1,3})*\]")


def _skeleton(text: str) -> tuple[str, list[int]]:
    """Text with only formatting noise removed, plus a map back to `text` offsets.

    Lowercases, and drops whitespace, quote marks, numbered reference markers ("[7]"), and
    hyphens sitting between two letters ("fixed-rank" vs "fixedrank", "COUNTER- FACT").
    Keeps every letter, digit and symbol, so a leading minus, a decimal point, a comparison
    sign or a changed letter still differ. Case is forgiven because quotes routinely
    capitalise a mid-sentence start ("We see" for "...we see"); no case-only difference
    changes what a sentence claims. Reference markers are forgiven because quotes routinely
    omit them; an *invented* marker still fails the numeric guard.
    """
    markers = {i for m in _CITATION_MARKER.finditer(text) for i in range(m.start(), m.end())}
    kept: list[tuple[str, int]] = [
        (ch, i)
        for i, ch in enumerate(text)
        if not ch.isspace() and ch not in _IGNORABLE and i not in markers
    ]
    out: list[str] = []
    idx: list[int] = []
    for k, (ch, i) in enumerate(kept):
        if (
            ch in _HYPHENS
            and 0 < k < len(kept) - 1
            and kept[k - 1][0].isalpha()
            and kept[k + 1][0].isalpha()
        ):
            continue
        for low in ch.lower():
            out.append(low)
            idx.append(i)
    return "".join(out), idx


def _skeleton_span(quote: str, source: str, start: int, end: int) -> tuple[int, int] | None:
    """Locate `quote` near source[start:end] allowing only formatting noise.

    The fuzzy path exists for PDF noise the normalizer missed (a missing space, a stray
    hyphen), not for wording. `partial_ratio` alone lets a two-letter edit through
    ("increased" -> "decreased" scores ~98), so the fuzzy match must also be an exact
    match once formatting noise is removed from both sides. Returns exact source offsets
    of the match, or None.
    """
    # A quote cut mid-sentence often gains a full stop the source has as a comma or not
    # at all; edge punctuation says nothing about what was claimed.
    sq, _ = _skeleton(quote.strip(_EDGE_PUNCT + " "))
    if not sq:
        return None
    pad = len(quote) // 10 + 10
    lo = max(0, start - pad)
    window = source[lo : min(len(source), end + pad)]
    sw, idx = _skeleton(window)
    pos = sw.find(sq)
    if pos == -1:
        return None
    return lo + idx[pos], lo + idx[pos + len(sq) - 1] + 1


def verify(claim: Claim, section_text: str) -> Claim:
    """Return the claim with verified/verify_method/offsets set.

    Never mutates the quote. Never asks the LLM to fix anything.
    Callers MUST drop claims where `verified is False`.
    """
    quote = claim.quote.strip()

    if not (MIN_QUOTE_CHARS <= len(quote) <= MAX_QUOTE_CHARS):
        log.warning("grounding.rejected_length", claim_id=claim.claim_id, length=len(quote))
        return claim.model_copy(update={"verified": False, "verify_method": "failed"})

    nq = normalize_text(quote)
    ns = normalize_text(section_text)

    # 1. exact substring
    idx = ns.find(nq)
    if idx != -1:
        return claim.model_copy(
            update={
                "verified": True,
                "verify_method": "exact",
                "quote_char_start": idx,
                "quote_char_end": idx + len(nq),
            }
        )

    # 2. fuzzy with alignment, for residual PDF noise the normalizer missed
    alignment = fuzz.partial_ratio_alignment(nq, ns)
    if alignment is not None and alignment.score >= FUZZY_THRESHOLD:
        span = ns[alignment.dest_start : alignment.dest_end]
        if not _numbers_preserved(nq, span):
            log.warning(
                "grounding.failed_numeric",
                claim_id=claim.claim_id,
                paper_id=claim.paper_id,
                score=round(alignment.score, 2),
                quote=quote[:120],
            )
            return claim.model_copy(update={"verified": False, "verify_method": "failed"})
        located = _skeleton_span(nq, ns, alignment.dest_start, alignment.dest_end)
        if located is None:
            log.warning(
                "grounding.failed_wording",
                claim_id=claim.claim_id,
                paper_id=claim.paper_id,
                score=round(alignment.score, 2),
                quote=quote[:120],
                source=span[:120],
            )
            return claim.model_copy(update={"verified": False, "verify_method": "failed"})
        start, end = located
        log.info(
            "grounding.fuzzy_pass",
            claim_id=claim.claim_id,
            score=round(alignment.score, 2),
            quote=quote[:80],
            source=ns[start:end][:80],
        )
        return claim.model_copy(
            update={
                "verified": True,
                "verify_method": "fuzzy97",
                "quote_char_start": start,
                "quote_char_end": end,
            }
        )

    # 3. dropped
    log.warning(
        "grounding.failed",
        claim_id=claim.claim_id,
        paper_id=claim.paper_id,
        best_score=round(alignment.score, 2) if alignment else 0.0,
        quote=quote[:120],
    )
    return claim.model_copy(update={"verified": False, "verify_method": "failed"})


def verify_all(claims: list[Claim], section_text: str) -> tuple[list[Claim], list[Claim]]:
    """Verify a batch. Returns (kept, dropped) — only `kept` proceeds downstream (Neo4j,
    Qdrant, the judge); `dropped` claims are returned so the caller can retain them for
    evaluation (TESTING.md E4: "hand-check 20 dropped claims to show the gate isn't
    discarding good ones indiscriminately") — never for repair, never re-entering the
    pipeline. That invariant lives in the caller, not here: this function's contract is
    unchanged, it just stops throwing the dropped claims away instead of only counting them.
    """
    checked = [verify(c, section_text) for c in claims]
    kept = [c for c in checked if c.verified]
    dropped = [c for c in checked if not c.verified]
    return kept, dropped
