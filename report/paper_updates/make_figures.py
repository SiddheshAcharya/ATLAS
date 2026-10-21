"""Redraw the paper / Blue Book figures to match the system as built (2026-09-29).

Every number drawn here is measured (evaluation/*.json, the run database, docs/TESTING.md);
the one illustrative panel (Fig. 5b) says so on the figure. Output: report/paper_updates/fig/.
    .venv/Scripts/python report/paper_updates/make_figures.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Polygon

OUT = Path(__file__).parent / "fig"
OUT.mkdir(exist_ok=True)
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9})

INK = "#1f2937"
MUTED = "#4b5563"
BLUE, BLUE_BG = "#5b7fc7", "#eef2fa"
GREEN, GREEN_BG = "#5f9e6e", "#eaf4ec"
RED, RED_BG = "#c46b6b", "#fbeaea"
PURPLE, PURPLE_BG = "#8a74c0", "#f1ecf8"
ORANGE, ORANGE_BG = "#d08a2e", "#fdf3e3"
GREY, GREY_BG = "#9ca3af", "#f3f4f6"
MAGENTA = "#b0418f"
C_ATLAS, C_BASE = "#2f4b8a", "#8fa8d8"


def canvas(w, h):
    fig = plt.figure(figsize=(w, h), dpi=220)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.axis("off")
    return fig, ax


def box(ax, x, y, w, h, title="", body="", edge=INK, fill="white", tsize=8.2, bsize=7.2,
        dashed=False, tcolor=None, radius=0.08, lw=1.1):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={radius}",
                                fc=fill, ec=edge, lw=lw, ls="--" if dashed else "-"))
    if title and body:
        ax.text(x + w / 2, y + h * 0.70, title, ha="center", va="center", fontsize=tsize,
                weight="bold", color=tcolor or INK)
        ax.text(x + w / 2, y + h * 0.33, body, ha="center", va="center", fontsize=bsize,
                color=MUTED, linespacing=1.25)
    elif title:
        ax.text(x + w / 2, y + h / 2, title, ha="center", va="center", fontsize=tsize,
                weight="bold", color=tcolor or INK, linespacing=1.25)


def panel(ax, x, y, w, h, label, edge, fill, sub=""):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.1",
                                fc=fill, ec=edge, lw=1.2))
    ax.text(x + 0.12, y + h - 0.16, label, fontsize=8.5, weight="bold", color=edge, va="center")
    if sub:
        ax.text(x + 0.12 + 0.068 * len(label) + 0.35, y + h - 0.16, sub, fontsize=8,
                weight="bold", color=edge, va="center", style="italic")


def arrow(ax, x1, y1, x2, y2, color=INK, lw=1.0):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color=color, lw=lw, mutation_scale=9))


def save(fig, name):
    fig.savefig(OUT / name, dpi=220, facecolor="white")
    plt.close(fig)
    print("wrote", OUT / name)


# ── Fig. 1 — pipeline as built (ratio ~1.47) ───────────────────────────────────
def fig_pipeline():
    W, H = 10.3, 7.0
    fig, ax = canvas(W, H)
    ax.text(W / 2, 6.82, "RESEARCH QUESTION  +  READING MODE", ha="center", fontsize=10, weight="bold")
    box(ax, W / 2 - 2.1, 6.42, 4.2, 0.26, "Standard 25  ·  Deep 75  ·  Extra Deep 200 papers",
        edge=GREY, fill=GREY_BG, tsize=7.5, tcolor=MUTED, radius=0.13)
    arrow(ax, W / 2, 6.42, W / 2, 6.2)

    panel(ax, 0.2, 5.0, W - 0.4, 1.18, "PHASE I   ACQUISITION & SEEDING", BLUE, BLUE_BG)
    items = [("LLM keyword expansion", "8–20 search strings"),
             ("4 scholarly APIs", "OpenAlex · arXiv · PubMed ·\nSemantic Scholar  (~500–575)"),
             ("Dedup + embed", "canonical IDs · bge-base\ncosine to the question"),
             ("Seed the frontier F", "top 20 by relevance;\n0.20 / 0.35 admission bands")]
    for i, (t, b) in enumerate(items):
        box(ax, 0.42 + i * 2.43, 5.1, 2.2, 0.72, t, b, edge=BLUE)
    arrow(ax, W / 2, 5.0, W / 2, 4.84)

    panel(ax, 0.2, 2.62, W - 0.4, 2.2, "PHASE II   THE FORAGING LOOP", GREEN, GREEN_BG,
          "one paper per iteration")
    row1 = [("1  SCORE F", "5 weighted signals\n(metadata + abstracts)", GREEN),
            ("2  READ TOP", "PDF: source · arXiv · Unpaywall\n· Europe PMC → GROBID", GREEN),
            ("3  EXTRACT", "gpt-oss-120b: claim,\nverbatim quote, scope", GREEN),
            ("4  GROUND", "quote must match the\nsource — else DROP", ORANGE),
            ("5  JUDGE", "kNN claim pairs →\ngpt-oss-20b, 6 labels", GREEN)]
    for i, (t, b, c) in enumerate(row1):
        x = 0.62 + i * 1.9
        box(ax, x, 3.72, 1.72, 0.74, t, b, edge=c, fill=ORANGE_BG if c == ORANGE else "white",
            tcolor=c if c == ORANGE else None)
        if i < 4:
            arrow(ax, x + 1.72, 4.09, x + 1.9, 4.09)
    row2 = [("8  STOP?", "budget · EMA saturation ·\nno candidate ≥ 0.25"),
            ("7  EXPAND", "≤ 60 references +\n≤ 60 citing works"),
            ("6b  PAGERANK + LOUVAIN", "every 10 papers;\nbridge promotion"),
            ("6a  GRAPH WRITE", "Neo4j, paper by paper —\nstreamed live")]
    for i, (t, b) in enumerate(row2):
        x = 0.62 + (i + 1) * 1.9
        box(ax, x, 2.8, 1.72, 0.74, t, b, edge=PURPLE if i == 3 else GREEN,
            fill=PURPLE_BG if i == 3 else "white", tsize=7.6)
        if i > 0:
            arrow(ax, x, 3.17, x - 0.18, 3.17)
    arrow(ax, 0.62 + 5 * 1.9 - 0.9, 3.72, 0.62 + 5 * 1.9 - 0.9, 3.54)
    ax.plot([0.42, 0.42], [3.17, 4.09], color=MAGENTA, lw=2)
    arrow(ax, 2.52, 3.17, 0.42, 3.17, color=MAGENTA)
    arrow(ax, 0.42, 4.09, 0.62, 4.09, color=MAGENTA)
    ax.text(0.3, 3.63, "re-score F", rotation=90, ha="center", va="center", color=MAGENTA,
            fontsize=7.5, weight="bold")
    ax.text(W / 2, 2.68, "the loop exits when a stopping rule fires", ha="center", fontsize=7,
            style="italic", color=GREEN)
    arrow(ax, 3.3, 2.62, 3.3, 2.44)

    panel(ax, 0.2, 1.02, 6.0, 1.4, "PHASE III   GAP DISCOVERY", RED, RED_BG, "on the finished graph")
    dets = [("D1", "Unlinked\nconcepts"), ("D2", "Predicted\nlinks"), ("D3", "Empty\ncombos"),
            ("D4", "Unanswered\ncalls"), ("D5", "Unresolved\nconflicts"), ("D6", "Shared\nweaknesses")]
    for i, (t, b) in enumerate(dets):
        off = t == "D2"
        box(ax, 0.36 + i * 0.97, 1.5, 0.86, 0.62, t, b + ("\n(not built)" if off else ""),
            edge=GREY if off else RED, dashed=off, tsize=7.4, bsize=6.2,
            tcolor=GREY if off else None)
    box(ax, 0.36, 1.1, 5.7, 0.3, "FUSION — weighted reciprocal-rank fusion + corroboration · "
        "no bounding papers → dropped", edge=RED, tsize=6.8)
    panel(ax, 6.4, 1.02, W - 6.6, 1.4, "PHASE IV   SYNTHESIS", PURPLE, PURPLE_BG)
    box(ax, 6.58, 1.12, W - 6.96, 0.98, "Gemini 2.5 Flash, one pass",
        "agreement · contradictions ·\nmethods over time · gap brief\n(citations built in code)",
        edge=PURPLE, tsize=7.6, bsize=6.8)
    ax.plot([6.2, 6.4], [1.72, 1.72], color=INK, lw=1)
    arrow(ax, W / 2, 1.02, W / 2, 0.84)
    box(ax, 1.5, 0.22, W - 3.0, 0.6, "DASHBOARD   live graph · cited report · grounded chat",
        "every claim shown with its verbatim quote highlighted in the text ATLAS read ·\n"
        "every LLM and API call cached, so a run replays exactly", edge=GREY, fill=GREY_BG,
        tsize=7.8, bsize=6.8)
    save(fig, "fig1_pipeline.png")


# ── Fig. 4 — grounding contract as built (ratio ~2.73) ─────────────────────────
def fig_grounding():
    W, H = 11.0, 4.03
    fig, ax = canvas(W, H)
    ax.text(2.6, 3.85, "(a)  The claim record returned by the extraction model", ha="center",
            fontsize=9, weight="bold")
    code = ("class Claim(BaseModel):\n"
            "    text:        str     # the claim, paraphrased\n"
            "    quote:       str     # VERBATIM from the source\n"
            "    section:     str     # GROBID section or 'abstract'\n"
            "    scope:       ClaimScope\n"
            "        # what_was_tested · population_or_setting\n"
            "        # method · dataset_or_context · metric · conditions\n"
            "    polarity, confidence\n"
            "    quote_char_start, quote_char_end   # set by the gate")
    ax.add_patch(FancyBboxPatch((0.15, 1.2), 4.95, 2.45, boxstyle="round,pad=0,rounding_size=0.08",
                                fc="#f8fafc", ec=INK, lw=1))
    ax.text(0.3, 3.5, code, family="DejaVu Sans Mono", fontsize=8.2, va="top", linespacing=2.0)
    box(ax, 0.15, 0.12, 4.95, 0.95, "Output is JSON validated against this schema; a malformed "
        "record is rejected,\na truncated one retried once with twice the length. Every call is "
        "cached on\n(job, model, parameters, prompt version, input), so a re-run is identical.",
        edge=GREY, fill=GREY_BG, tsize=6.8, tcolor=MUTED)

    ax.text(8.1, 3.85, "(b)  Verification — a string comparison, not a hope", ha="center",
            fontsize=9, weight="bold")
    steps = ["source normalised once: ligatures, hyphenated line breaks,\nrepeated headers, page numbers",
             "search the normalised text for the model's quote"]
    for i, s in enumerate(steps):
        box(ax, 5.7, 3.28 - i * 0.55, 4.8, 0.42, s, edge=INK, tsize=6.8)
        arrow(ax, 8.1, 3.28 - i * 0.55, 8.1, 3.28 - i * 0.55 - 0.13)
    d = Polygon([(8.1, 2.4), (9.0, 2.12), (8.1, 1.84), (7.2, 2.12)], closed=True, fc=ORANGE_BG,
                ec=ORANGE, lw=1.1)
    ax.add_patch(d)
    ax.text(8.1, 2.12, "exact match?", ha="center", va="center", fontsize=7, weight="bold")
    box(ax, 5.55, 1.1, 1.75, 0.5, "no → exact once spacing,\nhyphens, quote marks, case,\n[n] markers are ignored?",
        edge=ORANGE, fill=ORANGE_BG, tsize=5.9)
    ax.plot([7.2, 6.42], [2.12, 2.12], color=ORANGE, lw=1)
    arrow(ax, 6.42, 2.12, 6.42, 1.6, color=ORANGE)
    box(ax, 7.55, 1.1, 1.8, 0.45, "yes → STORE with offsets\n+ provenance row", edge=GREEN,
        fill=GREEN_BG, tsize=6.4)
    arrow(ax, 8.1, 1.84, 8.3, 1.55, color=GREEN)
    arrow(ax, 7.3, 1.33, 7.55, 1.33, color=GREEN)
    ax.text(7.42, 1.4, "yes", fontsize=6, color=GREEN)
    box(ax, 9.5, 1.1, 1.35, 0.5, "no → DROP and log.\nNever repaired\nby the model.", edge=RED,
        fill=RED_BG, tsize=6.2)
    ax.annotate("", xy=(9.5, 1.2), xytext=(7.3, 1.2), arrowprops=dict(
        arrowstyle="-|>", color=RED, lw=1, connectionstyle="arc3,rad=0.25", mutation_scale=9))
    box(ax, 5.55, 0.12, 5.3, 0.82, "MEASURED",
        "49 of 50 audited quotes verbatim (98 %; target 95 %); the one miss was a page number\n"
        "the PDF parser kept — now stripped. The gate rejected 0/73, 0/65, 1/98 and 3/198\n"
        "proposed claims on the four evaluated runs.", edge=GREEN, fill=GREEN_BG, tsize=7,
        bsize=6.5)
    save(fig, "fig4_grounding.png")


# ── Fig. 5 — pair reduction (measured) + DIFF_SCOPE (illustrative) (ratio ~2.3) ─
def fig_pairs():
    fig = plt.figure(figsize=(11.0, 4.78), dpi=220)
    ax = fig.add_axes((0.07, 0.17, 0.38, 0.66))
    runs = ["IoT safety\n(73 claims)", "IoT safety\n(65 claims)", "Fed. learning\n(97 claims)", "Gut microbiome\n(136 claims)"]
    possible, judged = [2628, 2080, 4656, 9180], [132, 132, 88, 84]
    x = range(4)
    ax.bar([i - 0.2 for i in x], possible, 0.38, color=C_BASE, label="all claim pairs")
    ax.bar([i + 0.2 for i in x], judged, 0.38, color=C_ATLAS, label="pairs sent to the judge")
    for i in x:
        ax.text(i, possible[i] + 700, f"{100 * (1 - judged[i] / possible[i]):.1f} % never\njudged",
                ha="center", fontsize=7.5, weight="bold", color=INK)
        ax.text(i + 0.2, judged[i] + 40, str(judged[i]), ha="center", fontsize=7)
        ax.text(i - 0.2, possible[i] + 40, f"{possible[i]:,}", ha="center", fontsize=7)
    ax.set_xticks(list(x), runs, fontsize=7.5)
    ax.set_ylim(0, 11500)
    ax.set_ylabel("claim pairs")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(fontsize=7, frameon=False, loc="upper left")
    fig.text(0.26, 0.93, "(a)  Candidate-pair reduction — measured", ha="center", fontsize=9,
             weight="bold")
    fig.text(0.26, 0.03, "k = 10 nearest stored claims from other papers, cosine ≥ 0.55,\n"
             "≤ 12 pairs per paper (reached in every run), ≤ 400 judge calls per run", ha="center", fontsize=7, color=MUTED)

    ax2 = fig.add_axes((0.5, 0.0, 0.5, 1.0))
    ax2.set_xlim(0, 5.5)
    ax2.set_ylim(0, 4.78)
    ax2.axis("off")
    ax2.text(2.75, 4.45, "(b)  Why DIFF_SCOPE is the load-bearing verdict", ha="center",
             fontsize=9, weight="bold")
    ax2.text(2.75, 4.18, "illustrative example — not from the evaluated corpus", ha="center",
             fontsize=7, style="italic", color=MUTED)
    box(ax2, 0.2, 3.1, 2.4, 0.9, "PAPER A", "\"LoRA matches full fine-tuning.\"\nscope — method: LoRA;\nsetting: 355 M-parameter model",
        edge=BLUE, fill=BLUE_BG, tsize=7.5, bsize=6.6)
    box(ax2, 2.9, 3.1, 2.4, 0.9, "PAPER B", "\"LoRA underperforms full fine-tuning.\"\nscope — method: LoRA;\nsetting: 175 B-parameter model",
        edge=RED, fill=RED_BG, tsize=7.5, bsize=6.6)
    box(ax2, 0.2, 2.05, 5.1, 0.8, "A polarity-only detector reports CONTRADICTS. The judge sees both "
        "quotes and both scope\nrecords, sees the setting differs, and must answer DIFF_SCOPE — the "
        "studies never tested\nthe same thing.", edge=INK, tsize=6.8)
    arrow(ax2, 2.75, 3.1, 2.75, 2.85)
    box(ax2, 0.2, 0.2, 5.1, 1.6, "MEASURED ON THE EVALUATED RUNS",
        "DIFF_SCOPE was returned for 20–24 % of judged pairs.\n"
        "In the IoT runs the only CONTRADICTS verdict (NodeMCU vs Raspberry Pi Pico) was false:\n"
        "two independent devices, not a disagreement. Annotators themselves disagreed on\n"
        "SUPPORTS / EXTENDS vs DIFF_SCOPE (human vs AI annotator, κ = −0.17), so judge\n"
        "accuracy could not yet be established (Section 4.5).", edge=ORANGE, fill=ORANGE_BG,
        tsize=7.4, bsize=6.6)
    arrow(ax2, 2.75, 2.05, 2.75, 1.8)
    save(fig, "fig5_pairs.png")


# ── Fig. 7 — detectors as built (ratio ~2.36) ──────────────────────────────────
def fig_detectors():
    W, H = 11.0, 4.66
    fig, ax = canvas(W, H)
    ax.text(2.7, 4.45, "(a)  Swanson's ABC model, automated as detector D1", ha="center",
            fontsize=9, weight="bold")
    for (x, lab, name, c) in [(0.8, "A", "fish oil\nliterature", BLUE), (2.7, "B", "blood viscosity\n(the bridge term)", ORANGE),
                              (4.6, "C", "Raynaud's\nliterature", RED)]:
        y = 3.75 if lab == "B" else 3.05
        ax.add_patch(plt.Circle((x, y), 0.27, fc="white", ec=c, lw=1.6))
        ax.text(x, y, lab, ha="center", va="center", fontsize=10, weight="bold", color=c)
        ax.text(x if lab != "B" else x + 0.42, y - 0.47 if lab != "B" else y, name, ha="center" if lab != "B" else "left", va="center", fontsize=6.8, color=MUTED)
    ax.plot([1.05, 2.45], [3.15, 3.65], color=INK, lw=1)
    ax.plot([2.95, 4.35], [3.65, 3.15], color=INK, lw=1)
    ax.plot([1.07, 4.33], [3.05, 3.05], color=MAGENTA, lw=1.2, ls="--")
    ax.text(2.7, 2.87, "NEVER CO-OCCUR  →  candidate gap", ha="center", fontsize=7, weight="bold", color=MAGENTA)
    box(ax, 0.2, 0.85, 5.0, 1.35, "HOW D1 IS IMPLEMENTED",
        "Concepts are extracted locally (spaCy + KeyBERT) and normalised\n"
        "(lemmas, alias list, embedding clustering at cosine ≥ 0.85). A co-occurrence\n"
        "graph is built in Python; A–B and B–C must co-occur above chance\n"
        "(positive PMI) while A–C never co-occur.", edge=GREY, fill=GREY_BG, tsize=7.2, bsize=6.5)
    box(ax, 0.2, 0.12, 5.0, 0.58, "Measured weakness: wording. \"continuous monitoring\" and \"panic button\" "
        "ideas were\nreported as unlinked though the corpus links them under other words.",
        edge=RED, fill=RED_BG, tsize=6.5)

    ax.text(8.25, 4.45, "(b)  Six detectors specified, five built, fused into one list",
            ha="center", fontsize=9, weight="bold")
    dets = [("D1", "Unlinked concepts", "A–B, B–C linked; A–C never", RED, False),
            ("D2", "Predicted links", "specified; not implemented", GREY, True),
            ("D3", "Empty combinations", "method × dataset cell nobody tried", RED, False),
            ("D4", "Unanswered calls", "future-work sentence never followed up", RED, False),
            ("D5", "Unresolved conflicts", "CONTRADICTS with no later resolver", RED, False),
            ("D6", "Shared weaknesses", "limitation recurring across ≥ 4 papers", RED, False)]
    for i, (k, t, b, c, off) in enumerate(dets):
        y = 3.85 - i * 0.44
        ax.add_patch(FancyBboxPatch((5.7, y), 5.1, 0.36, boxstyle="round,pad=0,rounding_size=0.06",
                                    fc=GREY_BG if off else "white", ec=c, lw=1, ls="--" if off else "-"))
        ax.text(5.82, y + 0.18, k, fontsize=7.6, weight="bold", va="center", color=c)
        ax.text(6.2, y + 0.18, t, fontsize=7.3, weight="bold", va="center", color=GREY if off else INK)
        ax.text(7.9, y + 0.18, b, fontsize=6.6, va="center", color=MUTED)
    arrow(ax, 8.25, 1.2, 8.25, 1.06)
    box(ax, 5.7, 0.7, 5.1, 0.34, "FUSION — normalise within detector · merge duplicates · weighted RRF + corroboration",
        edge=INK, tsize=6.4)
    box(ax, 5.7, 0.12, 5.1, 0.48, "THE HARD RULE — a gap that cannot name the papers bounding it\n"
        "is dropped before ranking, reporting or display. No override.", edge=ORANGE, fill=ORANGE_BG,
        tsize=6.6, tcolor="#8a5a14")
    save(fig, "fig7_detectors.png")


# ── Fig. 9 — architecture as built (ratio ~1.68) ───────────────────────────────
def fig_architecture():
    W, H = 10.3, 6.13
    fig, ax = canvas(W, H)
    layers = [("L0", "CLIENT", "Watch the agent read, live",
               "React · Vite · Cytoscape.js — live graph, cited report, grounded chat, light/dark theme", BLUE, BLUE_BG),
              ("L1", "API", "Thin: starts runs, streams events, holds no business logic",
               "FastAPI · Pydantic contracts · Server-Sent Events · offline snapshot mode for demos", "#4f8a8b", "#e8f3f3"),
              ("L2", "ORCHESTRATION", "An ordinary Python loop — every stage runnable on its own",
               "asyncio loop + typer CLI (atlas run / forage / gaps / report …) · replay from cache instead of a workflow engine", GREEN, GREEN_BG),
              ("L3", "SERVICES", "The work itself",
               "harvest · PDF resolve · GROBID / PyMuPDF · claims · grounding gate · kNN pairing · judge · concepts · 5 detectors · fusion · synthesis", ORANGE, ORANGE_BG),
              ("L4", "MODELS", "Language models are tools called at fixed points, never the controller",
               "LiteLLM → Groq gpt-oss-120b (claims) · gpt-oss-20b (keywords, judge, chat) · Gemini 2.5 Flash (synthesis) · local bge-base, spaCy, KeyBERT", PURPLE, PURPLE_BG),
              ("L5", "OBSERVABILITY", "Every call is traceable",
               "structlog bound to run_id and paper_id · per-call token and cost table · full event log", RED, RED_BG)]
    for i, (k, t, sub, tech, c, bg) in enumerate(layers):
        y = 5.35 - i * 0.66
        ax.add_patch(FancyBboxPatch((0.2, y), W - 0.4, 0.56, boxstyle="round,pad=0,rounding_size=0.08",
                                    fc=bg, ec=c, lw=1.2))
        ax.text(0.38, y + 0.28, k, fontsize=10, weight="bold", color=c, va="center")
        ax.text(0.9, y + 0.4, t, fontsize=8.6, weight="bold", color=c, va="center")
        ax.text(0.9 + 0.085 * len(t) + 0.25, y + 0.4, sub, fontsize=7.4, style="italic", color=INK, va="center")
        ax.text(0.9, y + 0.15, tech, fontsize=6.9, color=c, va="center")
    ax.text(0.2, 1.52, "PERSISTENCE — four stores, one job each", fontsize=8.6, weight="bold")
    stores = [("SQLite / PostgreSQL", "source of truth: papers, claims,\nrelations, events, LLM + API cache"),
              ("Neo4j (AuraDB)", "the knowledge graph; PageRank and\nLouvain computed in Python"),
              ("Qdrant (embedded)", "paper and claim vectors;\nrun-filtered search"),
              ("Local disk", "PDFs, GROBID TEI,\noffline demo snapshots")]
    for i, (t, b) in enumerate(stores):
        box(ax, 0.2 + i * 2.5, 0.62, 2.3, 0.78, t, b, edge=INK, tsize=7.8, bsize=6.5)
    box(ax, 0.8, 0.08, W - 1.6, 0.42, "Every LLM call is cached on (job, model, parameters, prompt version, input); "
        "every API response on disk.\nA re-run of the same question and configuration replays exactly — measured "
        "on a 15-paper run: identical output, 0 new model calls.", edge=GREY, fill=GREY_BG, tsize=6.8, tcolor=MUTED)
    save(fig, "fig9_architecture.png")


# ── Blue Book Fig. 7 — deployment as used (ratio ~1.0) ──────────────────────────
def fig_deployment():
    W, H = 7.6, 7.5
    fig, ax = canvas(W, H)
    ax.text(W / 2, 7.25, "ATLAS — deployment as used for the evaluation", ha="center", fontsize=10, weight="bold")
    panel(ax, 0.2, 3.3, 3.6, 3.7, "DEVELOPMENT LAPTOP", GREEN, GREEN_BG, "")
    ax.text(0.32, 6.62, "Windows, 5.9 GB RAM, no GPU", fontsize=7, color=MUTED)
    local = [("ATLAS API + foraging loop", "Python · FastAPI · typer CLI"),
             ("Dashboard", "React build, served by the API"),
             ("SQLite (or PostgreSQL)", "runs, claims, relations, caches"),
             ("Qdrant (embedded)", "paper and claim vectors"),
             ("Local models", "bge-base · spaCy · KeyBERT")]
    for i, (t, b) in enumerate(local):
        box(ax, 0.4, 5.85 - i * 0.62, 3.2, 0.52, t, b, edge=GREEN, tsize=7.4, bsize=6.4)
    panel(ax, 4.1, 3.3, 3.3, 3.7, "CLOUD SERVICES", PURPLE, PURPLE_BG, "")
    ax.text(4.22, 6.62, "free tiers, except the GROBID host", fontsize=7, color=MUTED)
    cloud = [("Groq API", "gpt-oss-120b · gpt-oss-20b"),
             ("Google Gemini API", "Gemini 2.5 Flash (synthesis)"),
             ("GROBID", "Hugging Face Space (Docker)"),
             ("Neo4j AuraDB Free", "the knowledge graph"),
             ("LiteLLM", "one client for all models")]
    for i, (t, b) in enumerate(cloud):
        box(ax, 4.3, 5.85 - i * 0.62, 2.9, 0.52, t, b, edge=PURPLE, tsize=7.4, bsize=6.4)
    panel(ax, 0.2, 1.3, 7.2, 1.75, "SCHOLARLY SOURCES", BLUE, BLUE_BG, "metadata, citations, open PDFs")
    srcs = ["OpenAlex", "arXiv", "PubMed", "Semantic\nScholar", "Unpaywall", "Europe PMC"]
    for i, s in enumerate(srcs):
        box(ax, 0.35 + i * 1.18, 1.45, 1.05, 0.9, s, edge=BLUE, tsize=7.2)
    box(ax, 1.4, 0.2, 4.8, 0.8, "BROWSER",
        "live graph · report · chat · works offline on saved snapshots", edge=GREY, fill=GREY_BG,
        tsize=8, bsize=6.8)
    arrow(ax, 3.8, 5.2, 4.1, 5.2)
    arrow(ax, 4.1, 4.6, 3.8, 4.6)
    arrow(ax, 2.0, 3.3, 2.0, 3.05)
    arrow(ax, 3.8, 1.0, 3.8, 1.3)
    ax.text(3.95, 4.9, "HTTPS", fontsize=6.5, color=MUTED, ha="center")
    save(fig, "figB7_deployment.png")


# ── Fig. 11 — measured results I (ratio ~2.77) ─────────────────────────────────
def fig_results1():
    fig = plt.figure(figsize=(11.0, 3.97), dpi=220)
    labels = ["IoT\n15", "IoT\n15", "Fed. learn.\n14", "Fed. learn.\n13 (GROBID)", "Gut micro.\n9 (GROBID)"]
    atlas, base = [115, 147, 355, 452, 381], [92, 92, 332, 332, 365]
    overlap = [53, 40, 36, 38, 56]
    ax = fig.add_axes((0.06, 0.2, 0.34, 0.62))
    x = range(5)
    ax.bar([i - 0.2 for i in x], atlas, 0.38, color=C_ATLAS, label="ATLAS")
    ax.bar([i + 0.2 for i in x], base, 0.38, color=C_BASE, label="cosine top-k baseline")
    for i in x:
        ax.text(i - 0.2, atlas[i] + 8, str(atlas[i]), ha="center", fontsize=6.8)
        ax.text(i + 0.2, base[i] + 8, str(base[i]), ha="center", fontsize=6.8)
    ax.set_xticks(list(x), [f"{lab}\noverlap {o} %" for lab, o in zip(labels, overlap)], fontsize=6.0)
    ax.set_ylabel("references reached")
    ax.set_ylim(0, 520)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(fontsize=7, frameon=False, loc="upper left")
    ax.set_title("(a) Foraging vs similarity retrieval,\nsame number of papers", fontsize=8.5, weight="bold")

    ax = fig.add_axes((0.47, 0.2, 0.19, 0.62))
    ax.bar([0], [98], 0.55, color=GREEN)
    ax.axhline(95, color=RED, ls="--", lw=1)
    ax.text(-0.58, 95.25, "target 95 %", color=RED, fontsize=7, ha="left")
    ax.text(0, 98.2, "98 %\n(49 / 50)", ha="center", fontsize=8, weight="bold")
    ax.set_ylim(90, 100.5)
    ax.set_xlim(-0.6, 0.6)
    ax.set_xticks([0], ["audited quotes\nfound verbatim"], fontsize=7)
    ax.set_ylabel("% of sampled claims")
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title("(b) Grounding accuracy", fontsize=8.5, weight="bold")

    ax = fig.add_axes((0.72, 0.2, 0.26, 0.62))
    red = [95.0, 93.7, 98.1, 99.1]
    ax.bar(range(4), red, 0.55, color=C_ATLAS)
    for i, v in enumerate(red):
        ax.text(i, v + 0.3, f"{v} %", ha="center", fontsize=7.5, weight="bold")
    ax.set_ylim(85, 100.5)
    ax.set_xticks(range(4), ["IoT\n73 claims", "IoT\n65 claims", "Fed. learn.\n97 claims", "Gut micro.\n136 claims"], fontsize=6.6)
    ax.set_ylabel("% of claim pairs never judged")
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title("(c) Pairs excluded before\nany model call", fontsize=8.5, weight="bold")
    save(fig, "fig11_results.png")


# ── Fig. 12 — measured results II (ratio ~2.44) ────────────────────────────────
def fig_results2():
    fig = plt.figure(figsize=(11.0, 4.5), dpi=220)
    ax = fig.add_axes((0.08, 0.2, 0.36, 0.62))
    names = ["human vs\nAI annotator", "human vs\nATLAS judge", "AI annotator vs\nATLAS judge"]
    kappa, agree = [-0.17, -0.05, 0.22], ["2 / 12", "2 / 12", "5 / 12"]
    cols = [RED if k < 0 else C_ATLAS for k in kappa]
    ax.bar(range(3), kappa, 0.55, color=cols)
    ax.axhline(0, color=INK, lw=0.8)
    for i, k in enumerate(kappa):
        ax.text(i, k + (0.02 if k >= 0 else -0.05), f"κ = {k:+.2f}\nagree {agree[i]}", ha="center",
                fontsize=7, va="bottom" if k >= 0 else "top")
    ax.set_ylim(-0.4, 0.45)
    ax.set_xticks(range(3), names, fontsize=7.2)
    ax.set_ylabel("Cohen's κ (12 single-label pairs)")
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title("(a) Relation labels — annotator agreement", fontsize=8.5, weight="bold")

    ax = fig.add_axes((0.56, 0.2, 0.4, 0.62))
    runs = ["IoT run A\n(10 gaps)", "IoT run B\n(6 gaps)"]
    pl, tr, wr = [2, 0], [4, 1], [4, 5]
    ax.barh(runs, pl, color=GREEN, label="plausible")
    ax.barh(runs, tr, left=pl, color="#e0b64f", label="trivial")
    ax.barh(runs, wr, left=[a + b for a, b in zip(pl, tr)], color=RED, label="wrong")
    for i in range(2):
        acc = 0
        for v in (pl[i], tr[i], wr[i]):
            if v:
                ax.text(acc + v / 2, i, str(v), ha="center", va="center", color="white", fontsize=8, weight="bold")
            acc += v
    ax.set_xlabel("gaps (rated blind to the detector, by an AI annotator)")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(fontsize=7, frameon=False, ncol=3, loc="lower right", bbox_to_anchor=(1, 1.0))
    ax.set_title("(b) Gap quality", fontsize=8.5, weight="bold", pad=18)
    save(fig, "fig12_results.png")


if __name__ == "__main__":
    fig_pipeline()
    fig_grounding()
    fig_pairs()
    fig_detectors()
    fig_architecture()
    fig_deployment()
    fig_results1()
    fig_results2()
