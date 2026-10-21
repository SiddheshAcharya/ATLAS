"""Combine the Blue Book and the research paper into one PDF, the paper in its own place.

Works on the team's current Blue Book (ATLAS_Blue_Book_updated.docx, including their own edits); only the
Index and List of Figures/Tables page numbers are written. Two steps, with a Word PDF export between:
    python combine.py            # 1. recompute every page number for the combined layout, save the .docx
    (export the .docx to PDF with Word)
    python combine.py --merge    # 2. build ATLAS_Blue_Book_with_Research_Paper.pdf

The paper goes straight after the References, where the Index lists "Research Paper"; page numbers run
continuously through it (its own 1..N are replaced) and the appendices move on by N pages.
"""

from __future__ import annotations

import copy
import re
import sys
from pathlib import Path

import pymupdf

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from docx_tools import W, Document, cell_texts, set_cell, text_of, text_runs  # noqa: E402

BB_DOCX = HERE / "ATLAS_Blue_Book_updated.docx"
BB_PDF = HERE / "ATLAS_Blue_Book_updated.pdf"
PAPER_PDF = HERE / "ATLAS_FINAL_updated.pdf"
OUT = HERE / "ATLAS_Blue_Book_with_Research_Paper.pdf"


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def page_label(pg) -> str:
    nums = [(b[3], b[4].strip()) for b in pg.get_text("blocks")
            if re.fullmatch(r"\d{1,3}|[IVX]{1,5}", b[4].strip()) and b[1] > pg.rect.height - 60]  # footer only
    return max(nums)[1] if nums else ""


def layout():
    """[(label, text)] for the Blue Book PDF, and the index of the last References page."""
    bb = pymupdf.open(str(BB_PDF))
    pages = [(page_label(p), norm(p.get_text())) for p in bb]
    start = next(i for i, (_, t) in enumerate(pages) if re.match(r"\S+ (References|Refrences) \[1\]", t))
    end = start
    while end + 1 < len(pages) and re.match(r"\S+ \[\d+\]", pages[end + 1][1]):
        end += 1
    return pages, start, end


def renumber() -> None:
    n_paper = len(pymupdf.open(str(PAPER_PDF)))
    pages, ref_start, ref_end = layout()
    body0 = next(i for i, (lab, t) in enumerate(pages) if lab == "1" and t.startswith("1 Chapter 1"))

    def final(i: int) -> str:  # printed number once the paper is inserted after page ref_end
        lab = pages[i][0]
        return str(int(lab) + n_paper) if i > ref_end and lab.isdigit() else lab

    def find(needle: str, at_start: bool = False) -> str:
        n = norm(needle)
        for i in range(body0, len(pages)):
            lab, t = pages[i]
            if (t.startswith(f"{lab} {n}") if at_start else n in t):
                return final(i)
        raise LookupError(needle)

    doc = Document(str(BB_DOCX))
    changed, missing = 0, []
    idx = next(t for t in doc.element.body.iter(W + "tbl") if "Chapter No." in "|".join(cell_texts(t)[0]))
    for r, (chap, topic, old) in enumerate(cell_texts(idx)):
        if r == 0 or not old.strip().isdigit():
            continue
        try:
            if chap.startswith("Chapter"):
                new = find(chap, at_start=True)
            elif topic.startswith(("References", "Refrences")):
                new = final(ref_start)
            elif topic.startswith("Research Paper"):
                new = str(int(pages[ref_end][0]) + 1)
            elif topic.startswith("Appendix"):
                new = find(topic.split(":")[0].split("  ")[0].strip(), at_start=True)
            else:
                new = find(topic.split("(")[0].strip()[:40])
        except LookupError:
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
            new = find(f"{m.group(1)} {m.group(2)}:")
        except LookupError:
            missing.append(text_of(p)[:30])
            continue
        # canonical form: the caption run, then exactly one run holding <tab/> and the page number
        runs = [r for r in p.findall(W + "r")]
        first = next(r for r in runs if (r.find(W + "t") is not None and (r.find(W + "t").text or "").strip()))
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
        if old != new:
            changed += 1
    doc.save(str(BB_DOCX))
    print(f"page numbers rewritten: {changed}; not found: {missing}; references end on printed page "
          f"{pages[ref_end][0]}, paper will be {int(pages[ref_end][0]) + 1} to {int(pages[ref_end][0]) + n_paper}")


def stamp(page, number: int) -> None:
    """Bottom-centre page number in the Blue Book's style (Times, 10 pt)."""
    page.draw_rect(pymupdf.Rect(270, 758, 345, 812), color=None, fill=(1, 1, 1))
    txt = str(number)
    w = pymupdf.get_text_length(txt, fontname="Times-Roman", fontsize=9.96)
    page.insert_text((311.6 - w / 2, 804.0), txt, fontname="Times-Roman", fontsize=9.96, color=(0, 0, 0))


def merge() -> None:
    bb = pymupdf.open(str(BB_PDF))
    paper = pymupdf.open(str(PAPER_PDF))
    pages, _, ref_end = layout()
    last = int(pages[ref_end][0])
    out = pymupdf.open()
    out.insert_pdf(bb, from_page=0, to_page=ref_end)
    Wd, Ht = bb[0].rect.width, bb[0].rect.height
    scale = Wd / paper[0].rect.width
    h = paper[0].rect.height * scale
    top = (Ht - h) / 2 - 6
    for k in range(len(paper)):
        pg = out.new_page(width=Wd, height=Ht)
        pg.show_pdf_page(pymupdf.Rect(0, top, Wd, top + h), paper, k)
        stamp(pg, last + 1 + k)
    for i in range(ref_end + 1, len(bb)):
        out.insert_pdf(bb, from_page=i, to_page=i)
        if pages[i][0].isdigit():
            stamp(out[-1], int(pages[i][0]) + len(paper))
    out.set_metadata({"title": "ATLAS: Blue Book with Research Paper", "author": "Team Synergy"})
    out.save(str(OUT), garbage=3, deflate=True)
    print(f"{OUT.name}: {len(out)} pages; paper on printed pages {last + 1} to {last + len(paper)}; "
          f"appendices from {int(pages[ref_end + 1][0]) + len(paper)}")


if __name__ == "__main__":
    merge() if "--merge" in sys.argv else renumber()
