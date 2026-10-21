"""Repair page numbering after the research paper was pasted into the Blue Book (.docx, in place).

Pasting a multi-section document moves section properties: the Blue Book's chapters inherited the paper's
first section (US Letter, paper footer) and the paper's ending inherited the Blue Book's last section
(A4, one column, numbering restarted at 1). This script:
  1. adds a section break before the paper title -> Blue Book body keeps A4, its footer, page 1 at Chapter 1
  2. adds a section break after the paper's last reference -> paper ending gets its two-column layout back
  3. removes the restart from the appendix section so numbers run on
  4. sets the paper's pages to A4 with the same text width (side margins 914 twips)
Idempotent guards: refuses to run if the breaks already exist.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from docx_tools import W, Document, text_of  # noqa: E402

DOCX = HERE / "ATLAS_Blue_Book_updated.docx"

doc = Document(str(DOCX))
body = doc.element.body
kids = list(body.iterchildren())
secs = list(body.iter(W + "sectPr"))
final = body.find(W + "sectPr")
assert final is secs[-1]

title_i = next(i for i, e in enumerate(kids) if text_of(e).startswith("ATLAS: Agentic Technology for Literature Analysis &"))
appx_i = next(i for i, e in enumerate(kids) if text_of(e).strip() == "Appendix A" and i > title_i)
before_title = kids[title_i - 1]
paper_last = next(kids[i] for i in range(appx_i - 1, title_i, -1) if kids[i].tag == W + "p" and text_of(kids[i]).strip())

for e in (before_title, paper_last):
    assert e.tag == W + "p", "expected a paragraph at the boundary"
    assert e.find(W + "pPr/" + W + "sectPr") is None, "section break already present; nothing to do"


def put_sectpr(p, sectpr):
    ppr = p.find(W + "pPr")
    if ppr is None:
        ppr = p.makeelement(W + "pPr", {})
        p.insert(0, ppr)
    ppr.append(sectpr)


# 1. Blue Book body (Chapter 1 .. References): A4, Blue Book footer, numbering starts at 1
bb_body = copy.deepcopy(final)
put_sectpr(before_title, bb_body)

# 2. paper ending (4.9 .. references): two columns like the paper's other text sections
two_col = next(s for s in reversed(secs[:-1]) if s.find(W + "cols") is not None and s.find(W + "cols").get(W + "num") == "2")
put_sectpr(paper_last, copy.deepcopy(two_col))

# 3. appendices: continue numbering
for pn in final.findall(W + "pgNumType"):
    final.remove(pn)

# 4. paper sections: A4 with unchanged text width
a4_w, a4_h = final.find(W + "pgSz").get(W + "w"), final.find(W + "pgSz").get(W + "h")
n_a4 = 0
for s in body.iter(W + "sectPr"):
    sz = s.find(W + "pgSz")
    if sz is not None and sz.get(W + "w") == "12240":
        mar = s.find(W + "pgMar")
        text_w = 12240 - int(mar.get(W + "left")) - int(mar.get(W + "right"))
        side = (int(a4_w) - text_w) // 2
        sz.set(W + "w", a4_w)
        sz.set(W + "h", a4_h)
        mar.set(W + "left", str(side))
        mar.set(W + "right", str(side))
        n_a4 += 1

doc.save(str(DOCX))
print(f"section breaks added before the paper title and after '{text_of(paper_last)[:30]}...'; "
      f"appendix restart removed; {n_a4} paper sections set to A4")
