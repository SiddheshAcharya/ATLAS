"""Text normalization — applied exactly once, right after extraction.

Everything downstream (chunks, offsets, claims, the grounding gate) operates on
normalized text. The original is kept only for display.

MUST be idempotent: normalize(normalize(x)) == normalize(x). There is a test for this.
"""

from __future__ import annotations

import re
import unicodedata

_HYPHEN_LINEBREAK = re.compile(r"(\w)-\s*\n\s*(\w)")
_PARA_BREAK = re.compile(r"\n\s*\n+")
_SINGLE_NEWLINE = re.compile(r"(?<!\n)\n(?!\n)")
_WS_RUN = re.compile(r"[ \t\u00a0]+")
_QUOTES = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'})
_DASHES = str.maketrans({"\u2013": "-", "\u2014": "-", "\u2212": "-"})
_PARA_SENTINEL = "\x00PARA\x00"


def normalize_text(text: str) -> str:
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)      # ligatures: fi -> fi
    t = t.replace("\u00ad", "")                  # soft hyphens
    t = _HYPHEN_LINEBREAK.sub(r"\1\2", t)        # de-hyphenate across line breaks
    t = _PARA_BREAK.sub(_PARA_SENTINEL, t)       # protect paragraph boundaries
    t = _SINGLE_NEWLINE.sub(" ", t)              # in-paragraph wraps become spaces
    t = t.replace(_PARA_SENTINEL, "\n\n")
    t = t.translate(_QUOTES).translate(_DASHES)
    t = _WS_RUN.sub(" ", t)
    return "\n\n".join(part.strip() for part in t.split("\n\n")).strip()


_PAGE_NUMBER = re.compile(
    r"(?:[Pp]age\s+)?(?:\d{1,4}|[ivx]{1,5}|[IVX]{1,5})(?:\s*(?:of|/)\s*\d{1,4})?"
)


def strip_page_numbers(pages: list[str]) -> list[str]:
    """Drop a bare page number ("5", "xii", "Page 5 of 12") from the top or bottom of a page.

    Page numbers are unique per page, so `strip_repeated_headers` never catches them, and
    when a sentence runs across a page break the number lands mid-sentence ("the last few
    5 layers"). A quote the LLM copies from there is then verbatim to the parsed text but
    not to the paper (E4 claim #18). Only the first and last non-empty lines are checked,
    so numbers inside tables or body text are left alone.
    """
    out = []
    for page in pages:
        lines = page.splitlines()
        for pick in (0, -1):
            nonempty = [i for i, ln in enumerate(lines) if ln.strip()]
            if nonempty and _PAGE_NUMBER.fullmatch(lines[nonempty[pick]].strip()):
                del lines[nonempty[pick]]
        out.append("\n".join(lines))
    return out


def strip_repeated_headers(pages: list[str], min_pages: int = 3) -> list[str]:
    """Remove lines that repeat on >= min_pages pages (running heads, footers)."""
    from collections import Counter

    counts: Counter[str] = Counter()
    for page in pages:
        for line in {ln.strip() for ln in page.splitlines() if 3 < len(ln.strip()) < 120}:
            counts[line] += 1
    junk = {line for line, n in counts.items() if n >= min_pages}
    return [
        "\n".join(ln for ln in page.splitlines() if ln.strip() not in junk) for page in pages
    ]
