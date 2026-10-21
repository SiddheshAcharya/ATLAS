"""Final pass over ATLAS_FINAL_updated.docx and ATLAS_Blue_Book_updated.docx (2026-09-30).

Run after update_paper.py and update_bluebook.py:
  1. replace every figure with the print-size redraws in fig2/ (text-width, 9 pt+ text)
  2. add six recent (2024-2025) papers to the literature tables, verified against arXiv, and
     sort both tables newest to oldest; add their references and a short paragraph
  3. rewrite em dashes (and en-dash number ranges) as ordinary punctuation
  4. Blue Book only: SDG section reduced to SDG 9, and the rule under its heading removed
"""

from __future__ import annotations

import copy
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from docx_tools import (  # noqa: E402
    EMU_PER_IN, W, Document, body, cell_texts, image_info, insert_par_after, replace_image, set_cell,
    set_par_text, text_of,
)

FIG = HERE / "fig2"
PAPER = HERE / "ATLAS_FINAL_updated.docx"
BB = HERE / "ATLAS_Blue_Book_updated.docx"

REFS = [
    (2024, "Skarlinski, M. D., Cox, S., Laurent, J. M., Braza, J. D., Hinks, M., Hammerling, M. J., Ponnapati, M., "
           "Rodriques, S. G., & White, A. D. (2024). Language agents achieve superhuman synthesis of scientific "
           "knowledge. arXiv preprint arXiv:2409.13740."),
    (2024, "Asai, A., He, J., Shao, R., Shi, W., Singh, A., Chang, J. C., Lo, K., Soldaini, L., Feldman, S., "
           "D'Arcy, M., et al. (2024). OpenScholar: Synthesizing scientific literature with retrieval-augmented "
           "LMs. arXiv preprint arXiv:2411.14199."),
    (2024, "Shao, Y., Jiang, Y., Kanell, T. A., Xu, P., Khattab, O., & Lam, M. S. (2024). Assisting in writing "
           "Wikipedia-like articles from scratch with large language models. In Proceedings of NAACL 2024. "
           "arXiv:2402.14207."),
    (2024, "Lu, C., Lu, C., Lange, R. T., Foerster, J., Clune, J., & Ha, D. (2024). The AI Scientist: Towards "
           "fully automated open-ended scientific discovery. arXiv preprint arXiv:2408.06292."),
    (2025, "Schmidgall, S., Su, Y., Wang, Z., Sun, X., Wu, J., Yu, X., Liu, J., Moor, M., Liu, Z., & Barsoum, E. "
           "(2025). Agent Laboratory: Using LLM agents as research assistants. arXiv preprint arXiv:2501.04227."),
    (2025, "Gottweis, J., Weng, W.-H., Daryin, A., Tu, T., Sirkovic, P., et al. (2025). Accelerating scientific "
           "discovery with Co-Scientist. arXiv preprint arXiv:2502.18864."),
]

# (year, paper-table row [6 cols, ref placeholder {n}], blue-book row [5 cols])
NEW_ROWS = [
    (2025,
     ["Gottweis et al. [{n}]", "Generate and refine new research hypotheses",
      "Multi-agent loop that generates, critiques and ranks hypotheses in tournament-style rounds",
      "Proposed drug repurposing candidates for acute myeloid leukaemia that laboratory experiments supported",
      "Shows that agent-generated hypotheses can survive experimental testing",
      "Produces hypotheses; the paper does not describe a quote-verified map of the literature read"],
     ["Gottweis et al. (2025)", "Hypothesis generation", "Co-Scientist: multi-agent generate, critique and rank loop",
      "Drug repurposing candidates supported in the laboratory",
      "Output is a hypothesis, not a verified map of the literature"]),
    (2025,
     ["Schmidgall et al. [{n}]", "Carry a human research idea through review, experiments and a report",
      "Three-stage agent pipeline: literature review, experimentation, report writing",
      "Reported an 84 % reduction in research cost compared with earlier autonomous methods",
      "Covers the whole research workflow end to end",
      "Literature review is one preparatory stage; no claim-level evidence graph is described"],
     ["Schmidgall et al. (2025)", "End-to-end research assistant", "Agent Laboratory: review, experiments, report",
      "84 % lower research cost than earlier autonomous methods",
      "Review is one stage of many; no claim-level evidence graph"]),
    (2024,
     ["Asai et al. [{n}]", "Answer scientific questions with citation-backed synthesis",
      "Retrieval-augmented model over 45 million open-access papers",
      "The 8B model beat GPT-4o by 5 % in correctness, with citation accuracy close to human experts",
      "Open model and datastore; strong citation grounding",
      "Retrieves per question; does not choose what to read next or report gaps"],
     ["Asai et al. (2024)", "Scientific question answering", "OpenScholar: retrieval over 45 million papers",
      "Beat GPT-4o by 5 % in correctness; expert-level citation accuracy",
      "Retrieves per question; no reading policy and no gap report"]),
    (2024,
     ["Skarlinski et al. [{n}]", "Retrieve, summarise and find contradictions in scientific literature",
      "PaperQA2 language agent with search, citation traversal and contradiction detection",
      "Matched or exceeded subject experts on literature tasks; about 70 % of its contradictions were confirmed "
      "by experts",
      "Closest prior system to ATLAS; shows contradiction detection works at scale",
      "The paper does not describe a verbatim quotation gate or a register of bounded gaps"],
     ["Skarlinski et al. (2024)", "Literature synthesis and contradiction finding",
      "PaperQA2: agent with search, citation traversal and contradiction detection",
      "Matched or beat subject experts; about 70 % of contradictions confirmed",
      "No verbatim quotation gate or bounded gap register described"]),
    (2024,
     ["Lu et al. [{n}]", "Automate open-ended scientific discovery",
      "Pipeline that writes ideas, code, experiments and papers, with a simulated reviewer",
      "Produced full papers for under US$15 each, some rated above a top-conference bar by its own reviewer",
      "Demonstrates end-to-end autonomy at very low cost",
      "Uses the literature mainly to check novelty, not to synthesise or verify it"],
     ["Lu et al. (2024)", "Automated discovery", "The AI Scientist: ideas, code, experiments, paper, review",
      "Full papers for under US$15 each", "Literature used to check novelty, not synthesised or verified"]),
    (2024,
     ["Shao et al. [{n}]", "Write long, Wikipedia-like articles from scratch",
      "Research planning through multi-perspective questions and simulated expert conversations",
      "Editors rated its articles better organised and broader in coverage than baselines",
      "Shows that planning the research improves the breadth of synthesis",
      "Grounded in web sources, not scholarly papers; no scope-aware conflict handling"],
     ["Shao et al. (2024)", "Long-form grounded writing", "STORM: multi-perspective research before drafting",
      "More organised, broader articles than baselines", "Web sources, not scholarly papers; no conflict handling"]),
]

PAPER_PARA = (
    "The most recent systems close part of this gap. PaperQA2 [{a}] searches, follows citations, summarises "
    "and flags contradictions at the level of subject experts, and OpenScholar [{b}] answers scientific questions "
    "with citation-backed synthesis over 45 million open papers. STORM [{c}], The AI Scientist [{d}], Agent "
    "Laboratory [{e}] and Co-Scientist [{f}] automate larger parts of the research workflow, from planning and "
    "writing to experiments and hypotheses. As described in their papers, none of them requires every extracted "
    "claim to pass a verbatim quotation check before it is kept, and none reports research gaps together with the "
    "papers that bound them. ")

BB_PARA = (
    "Six recent systems, published in 2024 and 2025, were added to the review because they are the closest "
    "current work. PaperQA2 (Skarlinski et al., 2024) searches, follows citations, summarises and flags "
    "contradictions at the level of subject experts, and OpenScholar (Asai et al., 2024) answers scientific "
    "questions with citation-backed synthesis. STORM (Shao et al., 2024), The AI Scientist (Lu et al., 2024), "
    "Agent Laboratory (Schmidgall et al., 2025) and Co-Scientist (Gottweis et al., 2025) automate larger parts of "
    "the research workflow. As described in their papers, none of them requires every extracted claim to pass a "
    "verbatim quotation check, and none reports research gaps together with the papers that bound them, which is "
    "the space this project occupies.")

SDG_BODY = [
    "ATLAS supports Sustainable Development Goal 9, which calls on countries to build resilient infrastructure, "
    "promote inclusive and sustainable industrialisation and foster innovation. The two targets closest to this "
    "project are Target 9.5, which asks for enhanced scientific research and upgraded technological capability, "
    "and Target 9.b, which asks for support to domestic technology development, research and innovation in "
    "developing countries.",
    "How ATLAS complements SDG 9",
    "Research infrastructure (Target 9.5). The reading stage of research today depends on how much one person "
    "can read. ATLAS turns it into a repeatable, checkable process: it builds a persistent knowledge graph in "
    "which every claim is tied to an exact quotation from its source, so later projects can reuse and verify the "
    "work instead of starting again. A replayed run reproduced its results exactly, which is what reliable "
    "infrastructure needs.",
    "Innovation (Target 9.5). The gap detectors point researchers towards questions the literature has not yet "
    "answered, and name the papers that bound each gap, shortening the path from reading to a new research idea. "
    "Our evaluation shows this part still needs work, and Chapter 6 sets out how to improve it.",
    "Low-cost access (Target 9.b). ATLAS runs on an ordinary laptop without a GPU, uses open data sources "
    "(OpenAlex, arXiv, PubMed and Semantic Scholar) and open-weight models, and costs at most about US$0.05 per "
    "15-paper run at paid rates. Students and researchers at institutions without paid databases or computing "
    "clusters can therefore carry out a structured literature review.",
    "The contribution is to research practice rather than to physical infrastructure, and the evaluated runs "
    "were small (9 to 15 papers). Its wider impact depends on the larger Deep and Extra Deep runs described as "
    "future work.",
]

EM = "—"
EN = "–"
DASH = re.compile(r"\s*" + EM + r"\s*")


def _pairwise(sentence: str) -> str:
    parts = DASH.split(sentence)
    if len(parts) == 1:
        return sentence
    out = parts[0]
    i = 1
    while i < len(parts):
        if i + 1 < len(parts):  # an enclosed aside: A - aside - B
            aside, rest = parts[i], parts[i + 1]
            out += (" (" + aside + ")" if "," in aside else ", " + aside + ",") + (
                "" if rest[:1] in ",.;:)" else " ") + rest.lstrip()
            i += 2
        else:  # a single dash: introduce what follows
            tail = parts[i]
            if re.match(r"(and|but|or|so|which|while|yet)\b", tail):
                out = out.rstrip() + ", " + tail
            elif ":" in out and "," in tail:  # after a colon, a list reads best in brackets
                end = "." if tail.endswith(".") else ""
                out = out.rstrip() + " (" + tail.rstrip(".") + ")" + end
            else:
                out = out.rstrip() + (", " if ":" in out else ": ") + tail
            i += 1
    return out.replace(",,", ",").replace(", .", ".").replace(",.", ".")


def dedash(s: str, reference: bool = False) -> str:
    if EM not in s and EN not in s:
        return s
    if reference:
        return s.replace(EM, ", ").replace(EN, "-")
    s = re.sub(r"(\d)\s*" + EN + r"\s*(\d)", r"\1 to \2", s)
    s = s.replace(EN, "-")
    if EM in s:
        pieces = re.split(r"(?<=[.!?])\s+", s)
        s = " ".join(_pairwise(p) for p in pieces)
    return s


def dedash_doc(doc) -> int:
    n = 0
    parts = [doc.element.body] + [sec.header._element for sec in doc.sections] + \
            [sec.footer._element for sec in doc.sections]
    for root in parts:
        for p in root.iter(W + "p"):
            ref = bool(re.match(r"\s*\[\d+\]", text_of(p)))
            for t in p.iter(W + "t"):
                if t.text and (EM in t.text or EN in t.text):
                    new = dedash(t.text, ref)
                    if new != t.text:
                        t.text = new
                        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                        n += 1
    return n


def images(doc):
    return [p for p in body(doc) if p.tag == W + "p" and image_info(doc, p)]


def lit_table(doc, header_part):
    return next(t for t in doc.element.body.iter(W + "tbl") if header_part in "|".join(cell_texts(t)[0]))


def row_year(txt: str, table_years: dict[str, int]) -> int:
    for k, v in table_years.items():
        if txt.startswith(k):
            return v
    years = [int(y) for y in re.findall(r"(19\d\d|20\d\d)", txt)]
    return max(years) if years else 0


def add_and_sort(tbl, rows_new, years_by_prefix):
    trs = tbl.findall(W + "tr")
    header, data = trs[0], trs[1:]
    template = data[0]
    for vals in rows_new:
        tr = copy.deepcopy(template)
        tbl.append(tr)
        for c, v in enumerate(vals):
            set_cell(tbl, len(tbl.findall(W + "tr")) - 1, c, v)
    data = tbl.findall(W + "tr")[1:]
    keyed = [(row_year("".join(text_of(p) for p in tr.findall(W + "tc")[0].iter(W + "p")), years_by_prefix), i, tr)
             for i, tr in enumerate(data)]
    for _, _, tr in keyed:
        tbl.remove(tr)
    for _, _, tr in sorted(keyed, key=lambda k: (-k[0], k[1])):
        tbl.append(tr)
    return [row_year("".join(text_of(p) for p in tr.findall(W + "tc")[0].iter(W + "p")), years_by_prefix)
            for tr in tbl.findall(W + "tr")[1:]]


def append_refs(doc, start_no: int) -> int:
    ref_ps = [p for p in doc.element.body.iter(W + "p") if re.match(r"\[\d+\]", text_of(p).strip())]
    last = ref_ps[-1]
    last_no = int(re.match(r"\[(\d+)\]", text_of(last).strip()).group(1))
    assert last_no + 1 == start_no, (last_no, start_no)
    sep = "  " if text_of(last).startswith(f"[{last_no}]  ") else " "
    anchor = last
    for k, (_, ref) in enumerate(REFS):
        anchor = insert_par_after(anchor, last, f"[{start_no + k}]{sep}{ref}")
    return start_no


# ═══════════════════ research paper ═══════════════════
doc = Document(str(PAPER))
imgs = images(doc)
for i, name in enumerate(["f1_pipeline", "f3_gate", "f4_grounding", "f5_pairs", "f7_detectors", "f9_architecture",
                          "f10_v0", "f11_results", "f12_results"]):
    replace_image(doc, imgs[i], str(FIG / f"{name}.png"), width_in=7.0)
cap = next(p for p in doc.element.body.iter(W + "p") if text_of(p).startswith("Fig. 10."))
t = text_of(cap)
set_par_text(cap, t[:t.index("(c)")].rstrip() if "(c)" in t else t)  # redrawn figure has panels (a), (b)
first = 24
append_refs(doc, first)
tbl = lit_table(doc, "Novelties used")
paper_years = {"Edge": 2024, "Cohan": 2023, "Yao": 2023, "Priem": 2022, "Wadden": 2020, "Pirolli": 1999,
               "Gordon": 1996, "Swanson": 1986, "Gottweis": 2025, "Schmidgall": 2025, "Asai": 2024,
               "Skarlinski": 2024, "Lu et": 2024, "Shao": 2024}
refno = {"Gottweis": 29, "Schmidgall": 28, "Asai": 25, "Skarlinski": 24, "Lu": 27, "Shao": 26}
order = [refno[r[1][0].split()[0]] for r in NEW_ROWS]
rows = []
for (_, prow, _), n in zip(NEW_ROWS, order):
    rows.append([prow[0].format(n=n)] + prow[1:])
print("paper table years:", add_and_sort(tbl, rows, paper_years))
p_read = next(p for p in doc.element.body.iter(W + "p") if text_of(p).startswith("Table 1 records"))
old = text_of(p_read)
k = old.index("No system in this table")
set_par_text(p_read, old[:k] + PAPER_PARA.format(a=24, b=25, c=26, d=27, e=28, f=29) + old[k:])
n = dedash_doc(doc)
doc.save(str(PAPER))
print(f"paper: figures replaced, 6 papers added, {n} dash runs rewritten")

# ═══════════════════ Blue Book ═══════════════════
doc = Document(str(BB))
imgs = images(doc)
bb_figs = {3: "b1_gantt", 4: "b2_usecase", 5: "b3_dfd0", 6: "b4_dfd1", 7: "f1_pipeline", 8: "f9_architecture",
           9: "b7_deployment", 10: "f3_gate", 11: "f4_grounding", 12: "f5_pairs", 13: "f7_detectors",
           17: "f11_results", 18: "f12_results"}
assert len(imgs) == 19, len(imgs)
for i, name in bb_figs.items():
    replace_image(doc, imgs[i], str(FIG / f"{name}.png"), width_in=6.3)
for i in (14, 15, 16):  # dashboard screenshots: full text width
    rid, cx, cy = image_info(doc, imgs[i])
    scale = 6.3 * EMU_PER_IN / cx
    for ext in imgs[i].iter("{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}extent"):
        ext.set("cx", str(int(cx * scale)))
        ext.set("cy", str(int(cy * scale)))
    for ext in imgs[i].iter("{http://schemas.openxmlformats.org/drawingml/2006/main}ext"):
        if ext.get("cx") is not None:
            ext.set("cx", str(int(cx * scale)))
            ext.set("cy", str(int(cy * scale)))
tbl = lit_table(doc, "Author(s) / Year")
print("blue book table years:", add_and_sort(tbl, [r[2] for r in NEW_ROWS], {}))
p_intro = next(p for p in doc.element.body.iter(W + "p") if text_of(p).startswith("Eighteen primary sources"))
set_par_text(p_intro, text_of(p_intro).replace(
    "Eighteen primary sources were reviewed across five bodies of work",
    "Primary sources were reviewed across six bodies of work").replace(
    "and agentic and graph-structured retrieval.", "agentic and graph-structured retrieval, and recent "
    "end-to-end research agents (2024 and 2025).").replace(
    "records what nine representative lines", "records what fifteen representative lines"))
p_read = next(p for p in doc.element.body.iter(W + "p") if text_of(p).startswith("Read together, these sources"))
insert_par_after(p_read, p_read, BB_PARA)
# references: continue the numbered list (Blue Book list ends at [21] unless the paper's two were added)
ref_ps = [p for p in doc.element.body.iter(W + "p") if re.match(r"\[\d+\]", text_of(p).strip())]
last_no = int(re.match(r"\[(\d+)\]", text_of(ref_ps[-1]).strip()).group(1))
append_refs(doc, last_no + 1)
# SDG: remove the rule under the heading; keep SDG 9 only, one page
b = body(doc)
h = next(i for i, e in enumerate(b) if text_of(e).strip() == "SDG Alignment")
ppr = b[h].find(W + "pPr")
for bd in ppr.findall(W + "pBdr"):
    ppr.remove(bd)
sdg9_head, sdg9_body = b[h + 1], b[h + 2]
end = next(i for i in range(h + 3, len(b)) if text_of(b[i]).startswith("Target 4.3"))
for e in b[h + 3:end + 1]:
    e.getparent().remove(e)
set_par_text(sdg9_body, SDG_BODY[0])
anchor = sdg9_body
for txt in SDG_BODY[1:]:
    tpl = sdg9_head if txt == "How ATLAS complements SDG 9" else sdg9_body
    anchor = insert_par_after(anchor, tpl, txt)
n = dedash_doc(doc)
doc.save(str(BB))
print(f"blue book: figures replaced, 6 papers added, SDG section rewritten, {n} dash runs rewritten")

for log, extra in ((HERE / "CHANGES_paper.md", "paper"), (HERE / "CHANGES_bluebook.md", "Blue Book")):
    s = log.read_text(encoding="utf-8")
    marker = "\n## Final pass (2026-09-30)"
    s = s.split(marker)[0] + marker + "\n" + (
        "- All figures redrawn at print size (7 in wide, text at least 9 pt) and inserted at full text width.\n"
        "- Six recent papers added (2024 and 2025, each checked against its arXiv page): PaperQA2, OpenScholar, "
        "STORM, The AI Scientist, Agent Laboratory, Co-Scientist. Literature table sorted newest to oldest; "
        "references added; one paragraph added after the table.\n"
        "- Em dashes rewritten as commas, colons or brackets; number ranges written as 'a to b'.\n"
        + ("- SDG section: only SDG 9 kept (with how ATLAS complements it); rule under the heading removed.\n"
           if extra == "Blue Book" else ""))
    log.write_text(s, encoding="utf-8")
