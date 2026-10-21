"""Fill the Blue Book Index and Lists of Figures/Tables from its exported PDF (paper already inside the .docx).

    python fill_index.py      # reads ATLAS_Blue_Book_updated.pdf, writes page numbers into the .docx
Re-export the PDF afterwards (numbers sit on existing lines, so the layout does not move).
"""

from __future__ import annotations

import copy
import re
import sys
from pathlib import Path

import pymupdf

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from docx_tools import W, Document, cell_texts, set_cell, text_of  # noqa: E402

DOCX = HERE / "ATLAS_Blue_Book_updated.docx"
PDF = HERE / "ATLAS_Blue_Book_updated.pdf"


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


pages = []
for pg in pymupdf.open(str(PDF)):
    nums = [(b[3], b[4].strip()) for b in pg.get_text("blocks")
            if re.fullmatch(r"\d{1,3}", b[4].strip()) and b[1] > pg.rect.height - 80]
    pages.append((max(nums)[1] if nums else "", norm(pg.get_text())))
body0 = next(i for i, (lab, t) in enumerate(pages) if lab == "1" and "Chapter 1" in t[:20])
paper0 = next(i for i, (lab, t) in enumerate(pages) if "ATLAS: Agentic Technology for Literature Analysis &" in t[:120])


def find(needle: str, at_start: bool = False, stop: int | None = None) -> str:
    n = norm(needle)
    for i in range(body0, stop if stop is not None else len(pages)):
        lab, t = pages[i]
        if (t.startswith(f"{lab} {n}") if at_start else n in t):
            return lab
    raise LookupError(needle)


doc = Document(str(DOCX))
changed, missing = 0, []
idx = next(t for t in doc.element.body.iter(W + "tbl") if "Chapter No." in "|".join(cell_texts(t)[0]))
for r, (chap, topic, old) in enumerate(cell_texts(idx)):
    if r == 0 or topic.strip() in ("List of Figures", "List of Tables", "Abstract"):
        continue
    try:
        if chap.startswith("Chapter"):
            new = find(chap, at_start=True)
        elif topic.startswith(("References", "Refrences")):
            new = next(lab for lab, t in pages[body0:paper0] if re.match(r"\d+ (References|Refrences) \[1\]", t))
        elif topic.startswith("Research Paper"):
            new = pages[paper0][0]
        elif topic.startswith("Appendix"):
            new = find(topic.split(":")[0].split("  ")[0].strip(), at_start=True)
        else:
            new = find(topic.split("(")[0].strip()[:40], stop=paper0)
    except (LookupError, StopIteration):
        missing.append(topic[:40])
        continue
    if new != old.strip():
        set_cell(idx, r, 2, new)
        changed += 1

for p in doc.element.body.iter(W + "p"):
    m = re.match(r"(Figure|Table) (\d+):", text_of(p))
    if not m or p.find(W + "pPr/" + W + "tabs") is None:
        continue
    try:
        new = find(f"{m.group(1)} {m.group(2)}:", stop=paper0)
    except LookupError:
        missing.append(text_of(p)[:30])
        continue
    runs = p.findall(W + "r")
    first = next(r for r in runs if r.find(W + "t") is not None and (r.find(W + "t").text or "").strip())
    old = "".join(t.text or "" for r in runs[runs.index(first) + 1:] for t in r.iter(W + "t")).strip()
    for r in runs[runs.index(first) + 1:]:
        p.remove(r)
    num_run = copy.deepcopy(first)
    for child in list(num_run):
        if child.tag != W + "rPr":
            num_run.remove(child)
    num_run.append(num_run.makeelement(W + "tab", {}))
    t = num_run.makeelement(W + "t", {})
    t.text = new
    num_run.append(t)
    p.append(num_run)
    changed += old != new

doc.save(str(DOCX))
print(f"page numbers changed: {changed}; not found: {missing}; research paper starts on page {pages[paper0][0]}")
