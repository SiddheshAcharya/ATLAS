"""Fill the Blue Book's Index / List of Figures / List of Tables page numbers from the exported PDF.

The team's template has dot-leader tabs but no page numbers (typed text, not Word fields). This
reads the printed page number of every figure caption, table caption and section heading from
ATLAS_Blue_Book_updated.pdf and writes it after the tab. Run after update_bluebook.py + PDF export;
then export the PDF again (numbers sit on the same line, so pagination does not move).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pymupdf

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from docx_tools import W, Document, cell_texts, set_cell, text_of, text_runs  # noqa: E402

DOCX = HERE / "ATLAS_Blue_Book_updated.docx"
PDF = HERE / "ATLAS_Blue_Book_updated.pdf"


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


pages = []  # (printed page label, normalised text)
for pg in pymupdf.open(str(PDF)):
    lines = [ln.strip() for ln in pg.get_text().splitlines() if ln.strip()]
    # the printed page number is the lowest numeric text block on the page (the footer)
    nums = [(b[3], b[4].strip()) for b in pg.get_text("blocks")
            if re.fullmatch(r"\d{1,3}|[IVX]{1,5}", b[4].strip())]
    label = max(nums)[1] if nums else ""
    pages.append((label, norm(" ".join(lines))))
body_start = next(i for i, (_, t) in enumerate(pages) if "1.1 Overview of the Project ATLAS" in t)


def page_of(needle: str, start: int = body_start) -> str:
    n = norm(needle)
    for label, t in pages[start:]:
        if n in t:
            return label
    raise LookupError(needle)


doc = Document(str(DOCX))
filled, missing = 0, []

# Lists of figures / tables: "Figure 7: …<tab>" -> page where the body caption "Figure 7:" sits
for p in doc.element.body.iter(W + "p"):
    t = text_of(p)
    m = re.match(r"(Figure|Table) (\d+):", t)
    tabs = p.find(W + "pPr/" + W + "tabs")
    if not m or tabs is None:
        continue
    try:
        num = page_of(f"{m.group(1)} {m.group(2)}:")
        assert num, t
    except LookupError:
        missing.append(t[:40])
        continue
    last = text_runs(p)[-1] if text_runs(p) else None
    run = p.makeelement(W + "r", {})
    if last is not None and last.find(W + "rPr") is not None:
        import copy
        run.append(copy.deepcopy(last.find(W + "rPr")))
    tt = run.makeelement(W + "t", {})
    tt.text = num
    run.append(tt)
    p.append(run)
    filled += 1

# Index table: chapter / section rows
idx = next(t for t in doc.element.body.iter(W + "tbl") if "Chapter No." in "|".join(cell_texts(t)[0]))
special = {"References": "References", "Research Paper": "Research Paper",
           "Appendix A": "Appendix A", "Appendix B": "Appendix B", "Appendix C": "Appendix C"}
for r, (chap, topic, pg) in enumerate(cell_texts(idx)):
    if r == 0 or pg.strip():
        continue
    try:
        if chap.startswith("Chapter"):
            num = page_of(f"{chap} {topic}")
        else:
            key = next((v for k, v in special.items() if topic.startswith(k)), None)
            needle = key if key else topic.split("(")[0].strip()[:40]
            num = page_of(needle, start=body_start + 1 if key else body_start)
        set_cell(idx, r, 2, num)
        filled += 1
    except LookupError:
        missing.append(topic[:40])

doc.save(str(DOCX))
print(f"filled {filled} page numbers; not found: {missing}")
