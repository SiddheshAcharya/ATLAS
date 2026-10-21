"""Print-legible figures for the paper and Blue Book (v2, 2026-09-30).

Every figure is drawn at its printed width (7.0 in) with text of at least 9 pt, so nothing is
shrunk on the page. Content is unchanged from v1 and from the team's originals (Gantt, use case,
DFDs, deflection gate, v0 measurements); only layout and wording are simplified. Numbers are
measured (evaluation/*.json, run database, docs/TESTING.md). Colours: the dataviz reference
palette (series #2a78d6 / #eb6834, validated), status colours with text labels.
    python report/paper_updates/make_figures_v2.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Ellipse, FancyBboxPatch

OUT = Path(__file__).parent / "fig2"
OUT.mkdir(exist_ok=True)
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9.5})

INK, MUTED, AXIS = "#0b0b0b", "#52514e", "#c3c2b7"
S1, S2 = "#2a78d6", "#eb6834"  # ATLAS / baseline
GOOD, WARN, CRIT = "#0ca30c", "#fab219", "#d03b3b"
BLUE, BLUE_BG = "#3b67b8", "#eef3fb"
GREEN, GREEN_BG = "#3f8a52", "#ecf6ee"
RED, RED_BG = "#b94a4a", "#fbeeee"
PURPLE, PURPLE_BG = "#6d59b0", "#f2eef9"
ORANGE, ORANGE_BG = "#b8741a", "#fdf4e6"
GREY, GREY_BG = "#8a8a8a", "#f4f4f2"
MAG = "#a8367f"
MEMBERS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#8a8a8a"]


def canvas(w, h, y0=0.0):
    fig = plt.figure(figsize=(w, h - y0), dpi=300)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, w)
    ax.set_ylim(y0, h)
    ax.axis("off")
    return fig, ax


def box(ax, x, y, w, h, title="", body="", edge=INK, fill="white", ts=9.8, bs=9.0, dashed=False,
        tcolor=None, bold_body=False, lw=1.2, align="center"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.06", fc=fill,
                                ec=edge, lw=lw, ls="--" if dashed else "-"))
    tx = x + w / 2 if align == "center" else x + 0.12
    if title and body:
        if h <= 0.95:
            ty, by = y + h * 0.7, y + h * 0.3
        else:
            ty, by = y + h - 0.22, y + (h - 0.36) / 2
        ax.text(tx, ty, title, ha=align, va="center", fontsize=ts, weight="bold", color=tcolor or INK)
        ax.text(tx, by, body, ha=align, va="center", fontsize=bs, color=INK if bold_body else MUTED,
                linespacing=1.3)
    elif title:
        ax.text(tx, y + h / 2, title, ha=align, va="center", fontsize=ts, weight="bold",
                color=tcolor or INK, linespacing=1.3)


def panel(ax, x, y, w, h, label, edge, fill, sub=""):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.08", fc=fill,
                                ec=edge, lw=1.3))
    ax.text(x + 0.14, y + h - 0.2, label + (f"   {sub}" if sub else ""), fontsize=10.2,
            weight="bold", color=edge, va="center")


def arrow(ax, x1, y1, x2, y2, color=INK, lw=1.3, style="-|>", rad=0.0):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(
        arrowstyle=style, color=color, lw=lw, mutation_scale=11, connectionstyle=f"arc3,rad={rad}"))


def label(ax, x, y, s, size=8.8, color=MUTED, **kw):
    ax.text(x, y, s, fontsize=size, color=color, ha=kw.pop("ha", "center"), va=kw.pop("va", "center"), **kw)


def save(fig, name):
    fig.savefig(OUT / name, dpi=300, facecolor="white")
    plt.close(fig)
    print("wrote", name)


def style_axes(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.yaxis.label.set_color(MUTED)


# ── Fig. 1 pipeline ─────────────────────────────────────────────────────────────
def fig_pipeline():
    W, H = 7.0, 8.9
    fig, ax = canvas(W, H)
    box(ax, 0.2, 8.38, 6.6, 0.42, "RESEARCH QUESTION + MODE  (Standard 25, Deep 75, Extra Deep 200 papers)",
        edge=GREY, fill=GREY_BG, ts=9.4)
    arrow(ax, 3.5, 8.38, 3.5, 8.2)
    panel(ax, 0.1, 6.5, 6.8, 1.7, "PHASE I   ACQUISITION AND SEEDING", BLUE, BLUE_BG)
    items = [("Expand the question", "an LLM writes 8 to 20 search strings"),
             ("Search four open APIs", "OpenAlex, arXiv, PubMed, Semantic Scholar"),
             ("De-duplicate and embed", "canonical IDs, bge-base vectors"),
             ("Seed the frontier F", "top 20 by relevance, 0.20 / 0.35 bands")]
    for i, (t, b) in enumerate(items):
        box(ax, 0.3 + (i % 2) * 3.3, 7.28 - (i // 2) * 0.68, 3.1, 0.6, t, b, edge=BLUE)
    arrow(ax, 3.5, 6.5, 3.5, 6.32)

    panel(ax, 0.1, 2.72, 6.8, 3.6, "PHASE II   THE FORAGING LOOP", GREEN, GREEN_BG, "one paper per turn")
    left = [("1  Score the frontier", "five weighted signals"),
            ("2  Read the top paper", "GROBID full text, else abstract"),
            ("3  Extract claims", "gpt-oss-120b: quote and scope"),
            ("4  Ground every quote", "not found in the source: dropped")]
    right = [("8  Stop?", "budget, saturation, nothing left"),
             ("7  Expand the frontier", "up to 60 references, 60 citers"),
             ("6  Write to the graph", "Neo4j, streamed live"),
             ("5  Judge claim pairs", "nearest neighbours, 6 labels")]
    ys = [4.98, 4.3, 3.62, 2.94]
    for i, (t, b) in enumerate(left):
        g = t.startswith("4")
        box(ax, 0.55, ys[i], 2.8, 0.56, t, b, edge=ORANGE if g else GREEN, fill=ORANGE_BG if g else "white",
            tcolor=ORANGE if g else None)
        if i < 3:
            arrow(ax, 1.95, ys[i], 1.95, ys[i + 1] + 0.56)
    for i, (t, b) in enumerate(right):
        w6 = t.startswith("6")
        box(ax, 3.9, ys[i], 2.8, 0.56, t, b, edge=PURPLE if w6 else GREEN, fill=PURPLE_BG if w6 else "white")
        if i < 3:
            arrow(ax, 5.3, ys[i + 1] + 0.56, 5.3, ys[i])
    arrow(ax, 3.35, ys[3] + 0.28, 3.9, ys[3] + 0.28)
    ax.plot([6.7, 6.85, 6.85, 0.3, 0.3], [5.26, 5.26, 5.78, 5.78, 5.26], color=MAG, lw=1.8)
    arrow(ax, 0.3, 5.26, 0.55, 5.26, color=MAG, lw=1.8)
    ax.text(3.5, 5.78, " re-score: what was just read changes what is read next ", ha="center", va="center",
            fontsize=9, color=MAG, weight="bold", bbox=dict(fc=GREEN_BG, ec="none", pad=1.5))
    arrow(ax, 2.3, 2.72, 2.3, 2.54)
    ax.text(4.3, 2.62, "the loop exits when the stop rule fires", fontsize=8.8, color=GREEN, style="italic",
            va="center")

    panel(ax, 0.1, 0.9, 4.4, 1.64, "PHASE III   GAP DISCOVERY", RED, RED_BG)
    dets = ["D1 Unlinked\nconcepts", "D2 Predicted\nlinks (not built)", "D3 Empty\ncombinations",
            "D4 Unanswered\ncalls", "D5 Unresolved\nconflicts", "D6 Shared\nweaknesses"]
    for i, d in enumerate(dets):
        off = "not built" in d
        box(ax, 0.25 + (i % 3) * 1.38, 1.66 - (i // 3) * 0.5, 1.28, 0.44, d, edge=GREY if off else RED,
            dashed=off, ts=8.6, tcolor=GREY if off else None)
    label(ax, 2.3, 1.02, "rank fusion; a gap without bounding papers is dropped", size=8.6, color=RED)
    panel(ax, 4.65, 0.9, 2.25, 1.64, "PHASE IV   SYNTHESIS", PURPLE, PURPLE_BG)
    box(ax, 4.8, 1.02, 1.95, 1.2, "Gemini 2.5 Flash", "one pass: agreement,\ncontradictions,\nmethods, gaps",
        edge=PURPLE)
    ax.plot([4.5, 4.65], [1.72, 1.72], color=INK, lw=1.2)
    arrow(ax, 3.5, 0.9, 3.5, 0.74)
    box(ax, 0.6, 0.1, 5.8, 0.62, "DASHBOARD: live graph, cited report, grounded chat",
        "each claim shown with its exact quote in the text ATLAS read", edge=GREY, fill=GREY_BG)
    save(fig, "f1_pipeline.png")


# ── Fig. 3 deflection gate ──────────────────────────────────────────────────────
def fig_gate():
    W, H = 7.0, 5.0
    fig, ax = canvas(W, H)
    ax.text(0.15, 4.8, "(a)  The two-threshold deflection gate", fontsize=10.5, weight="bold", va="center")
    x0, x1 = 0.4, 6.7
    sx = lambda c: x0 + (x1 - x0) * c  # noqa: E731
    for a, b, fc, ec, head, body in [(0, 0.2, RED_BG, RED, "DISCARD", "never\ntracked"),
                                     (0.2, 0.35, ORANGE_BG, ORANGE, "BRIDGE\nPOOL", "kept as an\nunread node"),
                                     (0.35, 1.0, GREEN_BG, GREEN, "FULLY SCORED", "enters the frontier and competes\nfor the reading budget")]:
        ax.add_patch(FancyBboxPatch((sx(a), 3.0), sx(b) - sx(a), 1.5, boxstyle="square,pad=0", fc=fc, ec=ec, lw=1.2))
        ax.text((sx(a) + sx(b)) / 2, 4.15, head, ha="center", va="center", fontsize=9.6, weight="bold", color=ec)
        ax.text((sx(a) + sx(b)) / 2, 3.45, body, ha="center", va="center", fontsize=8.8, color=MUTED, linespacing=1.25)
    ax.plot([x0, x1], [3.0, 3.0], color=INK, lw=1)
    for c in (0, 0.2, 0.35, 0.6, 0.8, 1.0):
        ax.plot([sx(c)] * 2, [2.95, 3.0], color=INK, lw=1)
        label(ax, sx(c), 2.8, f"{c:.2f}".rstrip("0").rstrip(".") if c not in (0.2, 0.35) else f"{c:.2f}",
              size=9, color=INK)
    label(ax, 3.55, 2.55, "cosine similarity between the candidate paper and the question", size=9)

    ax.text(0.15, 2.18, "(b)  Promotion on discovery", fontsize=10.5, weight="bold", va="center")
    for cx, lab, col in [(1.0, "cluster A", BLUE), (6.0, "cluster B", RED)]:
        ax.add_patch(Ellipse((cx, 1.35), 1.5, 0.75, fc="none", ec=col, lw=1.4, ls="--"))
        label(ax, cx, 1.35, lab + "\n(being read)", size=9, color=col, weight="bold")
    ax.add_patch(Circle((3.5, 1.35), 0.12, fc=ORANGE, ec=ORANGE))
    ax.plot([1.75, 3.38], [1.35, 1.35], color=INK, lw=1.2)
    ax.plot([3.62, 5.25], [1.35, 1.35], color=INK, lw=1.2)
    label(ax, 3.5, 1.72, "parked paper, cosine 0.27", size=9, color=ORANGE, weight="bold")
    label(ax, 3.5, 0.72, "At least two citation links into at least two clusters being read:"
          "\nthe parked paper is a connector, so it is promoted and read in full.", size=9, color=INK)
    label(ax, 3.5, 0.2, "Why two thresholds: a bridge term (Swanson's blood viscosity) is unlike the "
          "question by construction.", size=8.6, style="italic")
    save(fig, "f3_gate.png")


# ── Fig. 4 grounding ────────────────────────────────────────────────────────────
def fig_grounding():
    W, H = 7.0, 5.95
    fig, ax = canvas(W, H)
    ax.text(0.15, 5.78, "(a)  The claim record returned by the extraction model", fontsize=10.5, weight="bold", va="center")
    code = ("class Claim(BaseModel):\n"
            "    text:     str         # the claim, in plain words\n"
            "    quote:    str         # copied exactly from the source\n"
            "    section:  str         # GROBID section, or 'abstract'\n"
            "    scope:    ClaimScope  # what was tested, setting, method,\n"
            "                          # dataset, metric, conditions\n"
            "    quote_char_start, quote_char_end   # set by the gate")
    ax.add_patch(FancyBboxPatch((0.15, 3.98), 6.7, 1.58, boxstyle="round,pad=0,rounding_size=0.06", fc="#f7f7f5", ec=INK, lw=1))
    ax.text(0.32, 5.45, code, family="DejaVu Sans Mono", fontsize=8.9, va="top", linespacing=1.55)
    ax.text(0.15, 3.72, "(b)  Verification: a string comparison, not a hope", fontsize=10.5, weight="bold", va="center")
    box(ax, 0.15, 2.66, 2.1, 0.8, "1  Normalise", "ligatures, line breaks,\nheaders, page numbers", edge=INK)
    box(ax, 2.45, 2.66, 2.1, 0.8, "2  Find the quote", "search the normalised\nsource text", edge=INK)
    box(ax, 4.75, 2.66, 2.1, 0.8, "3  Exact match?", "yes: store it with its\ncharacter offsets", edge=GREEN,
        fill=GREEN_BG, tcolor=GREEN)
    arrow(ax, 2.25, 3.06, 2.45, 3.06)
    arrow(ax, 4.55, 3.06, 4.75, 3.06)
    box(ax, 2.95, 1.46, 3.9, 0.86, "4  Tolerant match?", "exact once spacing, hyphens, quote marks,\n"
        "case and [n] markers are ignored; yes: store it", edge=ORANGE, fill=ORANGE_BG, tcolor=ORANGE)
    box(ax, 0.15, 1.46, 2.5, 0.86, "5  Still no match", "drop and log it;\nnever repaired", edge=RED,
        fill=RED_BG, tcolor=RED)
    arrow(ax, 5.8, 2.66, 5.8, 2.32)
    label(ax, 5.95, 2.49, "no", size=9, ha="left")
    arrow(ax, 2.95, 1.89, 2.65, 1.89)
    label(ax, 2.8, 2.05, "no", size=9)
    box(ax, 0.15, 0.1, 6.7, 1.1, "Measured",
        "49 of 50 audited quotes were verbatim (98 %, target 95 %). The one miss was a page\n"
        "number the PDF reader kept; page numbers are now removed. The gate rejected\n"
        "0 of 73, 0 of 65, 1 of 98, 3 of 198 and 5 of 141 proposed claims across five runs.",
        edge=GREEN, fill=GREEN_BG, bs=9.0)
    save(fig, "f4_grounding.png")


# ── Fig. 5 pair reduction + DIFF_SCOPE ─────────────────────────────────────────
def fig_pairs():
    fig = plt.figure(figsize=(7.0, 6.8), dpi=300)
    ax = fig.add_axes((0.11, 0.665, 0.86, 0.27))
    runs = ["IoT A\n73 claims", "IoT B\n65 claims", "Fed. learning\n97 claims", "Gut microbiome\n136 claims"]
    possible, judged = [2628, 2080, 4656, 9180], [132, 132, 88, 84]
    x = range(4)
    ax.bar([i - 0.2 for i in x], possible, 0.38, color=AXIS, label="all claim pairs")
    ax.bar([i + 0.2 for i in x], judged, 0.38, color=S1, label="pairs sent to the judge")
    for i in x:
        ax.text(i - 0.2, possible[i] + 150, f"{possible[i]:,}", ha="center", fontsize=8.8, color=MUTED)
        ax.text(i + 0.2, judged[i] + 180, str(judged[i]), ha="center", fontsize=8.8, color=INK)
        ax.text(i, possible[i] + 1250, f"{100 * (1 - judged[i] / possible[i]):.1f} %\nnever judged",
                ha="center", fontsize=8.8, weight="bold", color=INK)
    ax.set_xticks(list(x), runs, fontsize=9)
    ax.set_ylim(0, 12600)
    ax.set_ylabel("claim pairs", fontsize=9.5)
    style_axes(ax)
    ax.legend(fontsize=9, frameon=False, loc="upper left")
    fig.text(0.02, 0.965, "(a)  Candidate pair reduction, measured", fontsize=10.5, weight="bold")
    fig.text(0.5, 0.555, "10 nearest stored claims from other papers (cosine at least 0.55), at most 12 pairs per "
             "paper;\nthat cap was reached in every run, so it shapes these figures as much as the search does.",
             ha="center", fontsize=8.8, color=MUTED)
    ax2 = fig.add_axes((0, 0, 1, 0.4853))
    ax2.set_xlim(0, 7.0)
    ax2.set_ylim(0, 3.3)
    ax2.axis("off")
    ax2.text(0.15, 3.12, "(b)  Why DIFF_SCOPE matters (an illustrative example)",
             fontsize=10.5, weight="bold", va="center")
    box(ax2, 0.15, 2.0, 3.25, 0.9, "Paper A", "\"LoRA matches full fine-tuning.\"\nsetting: 355 M parameter model",
        edge=BLUE, fill=BLUE_BG)
    box(ax2, 3.6, 2.0, 3.25, 0.9, "Paper B", "\"LoRA underperforms full fine-tuning.\"\nsetting: 175 B parameter model",
        edge=RED, fill=RED_BG)
    box(ax2, 0.15, 1.2, 6.7, 0.6, "A polarity check says CONTRADICTS. The judge compares the scope",
        "records, sees different settings, and must answer DIFF_SCOPE.", edge=INK, bold_body=True, bs=9.2, ts=9.2)
    box(ax2, 0.15, 0.08, 6.7, 0.95, "Measured on the evaluated runs",
        "DIFF_SCOPE: 20 to 24 % of judged pairs. The IoT runs' only CONTRADICTS (NodeMCU vs\n"
        "Raspberry Pi Pico) was false. Annotators disagreed on the labels (kappa = -0.17).",
        edge=ORANGE, fill=ORANGE_BG)
    save(fig, "f5_pairs.png")


# ── Fig. 7 detectors ────────────────────────────────────────────────────────────
def fig_detectors():
    W, H = 7.0, 6.4
    fig, ax = canvas(W, H, y0=0.6)
    ax.text(0.15, 6.2, "(a)  Swanson's ABC model, automated as detector D1", fontsize=10.5, weight="bold", va="center")
    pts = {"A": (1.0, 4.95, BLUE, "fish oil\nliterature"), "B": (3.5, 5.6, ORANGE, "blood viscosity\n(bridge term)"),
           "C": (6.0, 4.95, RED, "Raynaud's\nliterature")}
    for k, (x, y, c, n) in pts.items():
        ax.add_patch(Circle((x, y), 0.26, fc="white", ec=c, lw=1.8))
        label(ax, x, y, k, size=11, color=c, weight="bold")
        label(ax, x + (0.9 if k == "B" else 0), y + (0 if k == "B" else -0.52), n, size=9, ha="left" if k == "B" else "center")
    ax.plot([1.24, 3.26], [5.05, 5.52], color=INK, lw=1.2)
    ax.plot([3.74, 5.76], [5.52, 5.05], color=INK, lw=1.2)
    ax.plot([1.26, 5.74], [4.95, 4.95], color=MAG, lw=1.5, ls="--")
    label(ax, 3.5, 4.77, "A and C never co-occur: a candidate gap", size=9.2, color=MAG, weight="bold")
    box(ax, 0.15, 3.35, 6.7, 0.72, "How D1 is built: concepts are extracted locally (spaCy, KeyBERT) and merged",
        "when they mean the same; A with B and B with C must co-occur above chance.", edge=GREY, fill=GREY_BG,
        ts=9.2, bs=9.0, bold_body=True)
    ax.text(0.15, 3.05, "(b)  Six detectors specified, five built, fused into one list", fontsize=10.5, weight="bold", va="center")
    dets = [("D1", "Unlinked concepts", "A and C never linked", RED, False),
            ("D2", "Predicted links", "specified, not built", GREY, True),
            ("D3", "Empty combinations", "method and dataset never tried", RED, False),
            ("D4", "Unanswered calls", "future work nobody did", RED, False),
            ("D5", "Unresolved conflicts", "a conflict with no resolver", RED, False),
            ("D6", "Shared weaknesses", "a limitation in 4+ papers", RED, False)]
    for i, (k, t, b, c, off) in enumerate(dets):
        x, y = 0.15 + (i % 2) * 3.4, 2.45 - (i // 2) * 0.52
        ax.add_patch(FancyBboxPatch((x, y), 3.3, 0.44, boxstyle="round,pad=0,rounding_size=0.05",
                                    fc=GREY_BG if off else "white", ec=c, lw=1.1, ls="--" if off else "-"))
        ax.text(x + 0.1, y + 0.22, k, fontsize=9.4, weight="bold", color=c, va="center")
        ax.text(x + 0.45, y + 0.29, t, fontsize=9.2, weight="bold", color=GREY if off else INK, va="center")
        ax.text(x + 0.45, y + 0.11, b, fontsize=8.6, color=MUTED, va="center")
    box(ax, 0.15, 0.68, 6.7, 0.6, "Fusion and the hard rule",
        "scores are ranked and fused; a gap that cannot name its bounding papers is dropped", edge=ORANGE,
        fill=ORANGE_BG, tcolor=ORANGE)
    save(fig, "f7_detectors.png")


# ── Fig. 9 architecture ────────────────────────────────────────────────────────
def fig_architecture():
    W, H = 7.0, 7.4
    fig, ax = canvas(W, H)
    layers = [("L0", "CLIENT", "React, Vite, Cytoscape.js dashboard:\nlive graph, cited report, grounded chat", BLUE, BLUE_BG),
              ("L1", "API", "FastAPI, Pydantic contracts, Server-Sent Events,\noffline snapshots for demos", "#3f7f80", "#eaf4f4"),
              ("L2", "ORCHESTRATION", "a plain Python loop; every stage runs alone\nfrom the command line; replay from cache", GREEN, GREEN_BG),
              ("L3", "SERVICES", "harvest, PDF parsing, claims, grounding gate,\npairing, judge, concepts, detectors, synthesis", ORANGE, ORANGE_BG),
              ("L4", "MODELS", "Groq gpt-oss-120b and 20b, Gemini 2.5 Flash (via\nLiteLLM); local bge-base, spaCy, KeyBERT", PURPLE, PURPLE_BG),
              ("L5", "OBSERVABILITY", "structured logs per run and paper;\ntokens and cost recorded for every call", RED, RED_BG)]
    for i, (k, t, tech, c, bg) in enumerate(layers):
        y = 6.6 - i * 0.86
        ax.add_patch(FancyBboxPatch((0.15, y), 6.7, 0.76, boxstyle="round,pad=0,rounding_size=0.06", fc=bg, ec=c, lw=1.3))
        ax.text(0.3, y + 0.38, k, fontsize=11, weight="bold", color=c, va="center")
        ax.text(0.8, y + 0.38, t, fontsize=10, weight="bold", color=c, va="center")
        ax.text(2.55, y + 0.38, tech, fontsize=9, color=INK, va="center", linespacing=1.3)
    ax.text(0.15, 1.82, "PERSISTENCE: four stores, one job each", fontsize=10.2, weight="bold", va="center")
    stores = [("SQLite or PostgreSQL", "source of truth\nand call cache"), ("Neo4j AuraDB", "the knowledge\ngraph"),
              ("Qdrant, embedded", "paper and claim\nvectors"), ("Local disk", "PDFs and demo\nsnapshots")]
    for i, (t, b) in enumerate(stores):
        box(ax, 0.15 + i * 1.7, 0.78, 1.6, 0.88, t, b, edge=INK, ts=9.2, bs=8.8)
    box(ax, 0.15, 0.1, 6.7, 0.54, "Every model and API call is cached, so a run replays exactly",
        edge=GREY, fill=GREY_BG, ts=9.4)
    save(fig, "f9_architecture.png")


# ── Fig. 10 v0 measurements (the team's figure, redrawn) ───────────────────────
def fig_v0():
    fig = plt.figure(figsize=(7.0, 3.3), dpi=300)
    ax = fig.add_axes((0.1, 0.2, 0.36, 0.62))
    ax.bar([0, 1], [65.9, 3.0], 0.55, color=[S1, AXIS])
    for i, v in enumerate([65.9, 3.0]):
        ax.text(i, v + 2, f"{v} %", ha="center", fontsize=9.5, weight="bold")
    ax.set_xticks([0, 1], ["ATLAS v0\n(8 B model, unfiltered)", "typical real\ncitation network"], fontsize=8.8)
    ax.set_ylabel("edge density (%)")
    ax.set_ylim(0, 80)
    style_axes(ax)
    ax.set_title("(a)  Relationship over-assertion", fontsize=10, weight="bold", loc="left")
    ax = fig.add_axes((0.6, 0.2, 0.36, 0.62))
    ax.bar([0, 1], [21, 8], 0.55, color=[S1, AXIS])
    for i, v in enumerate([21, 8]):
        ax.text(i, v + 0.6, f"{v} / 29", ha="center", fontsize=9.5, weight="bold")
    ax.set_xticks([0, 1], ["echoed the input\nverbatim", "genuinely\nsynthesised"], fontsize=8.8)
    ax.set_ylabel("gap statements")
    ax.set_ylim(0, 25)
    style_axes(ax)
    ax.set_title("(b)  Synthesis without a graph", fontsize=10, weight="bold", loc="left")
    save(fig, "f10_v0.png")


# ── Fig. 11 results ─────────────────────────────────────────────────────────────
def fig_results1():
    fig = plt.figure(figsize=(7.0, 6.2), dpi=300)
    ax = fig.add_axes((0.1, 0.58, 0.87, 0.34))
    labels = ["IoT, 15", "IoT, 15", "Fed. learn., 14", "Fed. learn., 13", "Gut micro., 9"]
    atlas, base, ov = [115, 147, 355, 452, 381], [92, 92, 332, 332, 365], [53, 40, 36, 38, 56]
    x = range(5)
    ax.bar([i - 0.19 for i in x], atlas, 0.36, color=S1, label="ATLAS")
    ax.bar([i + 0.19 for i in x], base, 0.36, color=S2, label="similarity baseline, same size")
    for i in x:
        ax.text(i - 0.19, atlas[i] + 8, str(atlas[i]), ha="center", fontsize=8.8)
        ax.text(i + 0.19, base[i] + 8, str(base[i]), ha="center", fontsize=8.8)
    ax.set_xticks(list(x), [f"{a}\noverlap {o} %" for a, o in zip(labels, ov)], fontsize=8.8)
    ax.set_ylabel("references reached")
    ax.set_ylim(0, 540)
    style_axes(ax)
    ax.legend(fontsize=9, frameon=False, loc="upper left")
    fig.text(0.02, 0.965, "(a)  Citation reach of the papers read, against similarity retrieval", fontsize=10.5, weight="bold")

    ax = fig.add_axes((0.1, 0.08, 0.32, 0.32))
    ax.bar([0], [98], 0.5, color=S1)
    ax.axhline(95, color=INK, ls="--", lw=1)
    ax.text(-0.45, 95.3, "target 95 %", fontsize=9, color=INK)
    ax.text(0, 98.25, "98 % (49 of 50)", ha="center", fontsize=9.5, weight="bold")
    ax.set_ylim(90, 100.5)
    ax.set_xlim(-0.6, 0.6)
    ax.set_xticks([0], ["audited quotes found verbatim"], fontsize=8.8)
    ax.set_ylabel("% of sampled claims")
    style_axes(ax)
    fig.text(0.02, 0.45, "(b)  Grounding accuracy", fontsize=10.5, weight="bold")

    ax = fig.add_axes((0.56, 0.08, 0.41, 0.32))
    red = [95.0, 93.7, 98.1, 99.1]
    ax.bar(range(4), red, 0.55, color=S1)
    for i, v in enumerate(red):
        ax.text(i, v + 0.3, f"{v} %", ha="center", fontsize=9, weight="bold")
    ax.set_ylim(85, 101)
    ax.set_xticks(range(4), ["IoT A", "IoT B", "Fed.", "Gut"], fontsize=8.8)
    ax.set_ylabel("% of pairs never judged")
    style_axes(ax)
    fig.text(0.5, 0.45, "(c)  Pairs excluded before any model call", fontsize=10.5, weight="bold")
    save(fig, "f11_results.png")


# ── Fig. 12 results ─────────────────────────────────────────────────────────────
def fig_results2():
    fig = plt.figure(figsize=(7.0, 3.6), dpi=300)
    ax = fig.add_axes((0.11, 0.22, 0.36, 0.6))
    kappa, agree = [-0.17, -0.05, 0.22], ["2 of 12", "2 of 12", "5 of 12"]
    ax.bar(range(3), kappa, 0.55, color=S1)
    ax.axhline(0, color=INK, lw=0.9)
    for i, k in enumerate(kappa):
        ax.text(i, k + (0.03 if k >= 0 else -0.03), f"{k:+.2f}\n{agree[i]}", ha="center",
                va="bottom" if k >= 0 else "top", fontsize=8.8)
    ax.set_ylim(-0.42, 0.45)
    ax.set_xticks(range(3), ["human vs\nAI annotator", "human vs\njudge", "AI annotator\nvs judge"], fontsize=8.6)
    ax.set_ylabel("Cohen's kappa")
    style_axes(ax)
    fig.text(0.02, 0.93, "(a)  Agreement on relation labels", fontsize=10.5, weight="bold")

    ax = fig.add_axes((0.62, 0.22, 0.35, 0.6))
    runs = ["IoT run A\n(10 gaps)", "IoT run B\n(6 gaps)"]
    pl, tr, wr = [2, 0], [4, 1], [4, 5]
    ax.barh(runs, pl, color=GOOD, edgecolor="white", linewidth=2)
    ax.barh(runs, tr, left=pl, color=WARN, edgecolor="white", linewidth=2)
    ax.barh(runs, wr, left=[a + b for a, b in zip(pl, tr)], color=CRIT, edgecolor="white", linewidth=2)
    for i in range(2):
        acc = 0
        for v, name in ((pl[i], "plausible"), (tr[i], "trivial"), (wr[i], "wrong")):
            if v:
                ax.text(acc + v / 2, i, str(v), ha="center", va="center", fontsize=10,
                        color="white" if name != "trivial" else INK, weight="bold")
            acc += v
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in (GOOD, WARN, CRIT)]
    ax.legend(handles, ["plausible", "trivial", "wrong"], ncol=3, fontsize=8.8, frameon=False,
              loc="lower center", bbox_to_anchor=(0.45, 1.0))
    ax.invert_yaxis()
    ax.set_xlabel("gaps, rated blind by an AI annotator")
    ax.tick_params(axis="y", labelsize=8.8)
    style_axes(ax)
    fig.text(0.52, 0.93, "(b)  Gap quality", fontsize=10.5, weight="bold")
    save(fig, "f12_results.png")


# ── Blue Book: deployment ───────────────────────────────────────────────────────
def fig_deployment():
    W, H = 7.0, 7.0
    fig, ax = canvas(W, H)
    box(ax, 1.2, 6.35, 4.6, 0.55, "BROWSER: graph, report, chat (saved runs work offline)", edge=GREY,
        fill=GREY_BG, ts=9.4)
    arrow(ax, 1.65, 6.35, 1.65, 5.95, style="<|-|>")
    for (x, name, sub, col, bg, rows) in (
            (0.1, "DEVELOPMENT LAPTOP", "Windows, 5.9 GB RAM, no GPU", GREEN, GREEN_BG,
             [("ATLAS API and loop", "Python, FastAPI"), ("Dashboard", "served by the API"),
              ("SQLite or PostgreSQL", "runs, claims, caches"), ("Qdrant, embedded", "vectors"),
              ("Local models", "bge-base, spaCy, KeyBERT")]),
            (3.8, "HOSTED SERVICES", "free tiers, except the GROBID host", PURPLE, PURPLE_BG,
             [("Groq API", "gpt-oss-120b and 20b"), ("Gemini API", "Gemini 2.5 Flash"),
              ("GROBID", "Hugging Face container"), ("Neo4j AuraDB", "the knowledge graph"),
              ("LiteLLM", "one client for all models")])):
        panel(ax, x, 2.35, 3.1, 3.6, name, col, bg)
        label(ax, x + 1.55, 5.45, sub, size=8.8)
        for i, (t, b) in enumerate(rows):
            box(ax, x + 0.15, 4.6 - i * 0.54, 2.8, 0.48, t, b, edge=col, ts=9.2, bs=8.4)
    arrow(ax, 3.22, 4.2, 3.78, 4.2, style="<|-|>")
    label(ax, 3.5, 4.42, "HTTPS", size=8.4)
    panel(ax, 0.1, 0.1, 6.8, 1.75, "SCHOLARLY SOURCES", BLUE, BLUE_BG, "metadata, citations, open PDFs")
    for i, s_ in enumerate(["OpenAlex", "arXiv", "PubMed", "Semantic\nScholar", "Unpaywall", "Europe\nPMC"]):
        box(ax, 0.22 + i * 1.12, 0.25, 1.02, 0.95, s_, edge=BLUE, ts=9)
    arrow(ax, 1.65, 2.35, 1.65, 1.85, style="<|-|>")
    save(fig, "b7_deployment.png")


# ── Blue Book: Gantt (the team's plan, redrawn) ────────────────────────────────
def fig_gantt():
    tasks = [("Repository consolidation, key rotation, CI", 0, 1, 0),
             ("Docker Compose stack (seven services)", 0, 1, 0),
             ("Temporal skeleton + PostgreSQL event log", 1, 1, 0),
             ("OpenAlex / arXiv / Semantic Scholar clients", 1, 1, 1),
             ("Canonicalisation and de-duplication", 2, 1, 1),
             ("Unpaywall to PDF to GROBID to TEI pipeline", 2, 1, 2),
             ("SPECTER2 + BGE-M3 embeddings to Qdrant", 3, 1, 2),
             ("Wire frontend to live WebSocket feed", 3, 2, 3),
             ("Neo4j migration + GDS PageRank", 4, 1, 1),
             ("Foraging policy: gate, bridge pool, scorer", 4, 2, 0),
             ("Stopping rule + gain-decay curve", 5, 1, 1),
             ("Evaluation harness: golden survey set", 6, 1, 3),
             ("Review-II demonstration and rehearsal", 7, 1, 4)]
    fig = plt.figure(figsize=(7.0, 5.4), dpi=300)
    ax = fig.add_axes((0.46, 0.2, 0.52, 0.74))
    for i, (name, start, dur, m) in enumerate(tasks):
        ax.barh(i, dur, left=start, color=MEMBERS[m], edgecolor="white", linewidth=2, height=0.7)
    ax.set_yticks(range(len(tasks)), [t[0] for t in tasks], fontsize=8.4)
    ax.invert_yaxis()
    ax.set_xticks([w + 0.5 for w in range(8)], [f"W{w + 1}" for w in range(8)], fontsize=9)
    ax.set_xlabel("project week (W1 begins 17 July)", fontsize=8.8, color=MUTED)
    ax.set_xlim(0, 8)
    for k, w in enumerate((1, 3, 5, 7)):
        ax.axvline(w, color=CRIT, ls="--", lw=1)
        ax.text(w, -1.0, f"M{k + 1}", color=CRIT, ha="center", fontsize=9, weight="bold")
    style_axes(ax)
    ax.tick_params(axis="y", length=0)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in MEMBERS]
    fig.legend(handles, ["Member 1", "Member 2", "Member 3", "Member 4", "All members"], ncol=5, fontsize=8.8,
               frameon=False, loc="lower center", bbox_to_anchor=(0.5, 0.0))
    save(fig, "b1_gantt.png")


# ── Blue Book: use case ────────────────────────────────────────────────────────
def actor(ax, x, y, name):
    ax.add_patch(Circle((x, y + 0.42), 0.12, fc="white", ec=INK, lw=1.3))
    ax.plot([x, x], [y + 0.3, y], color=INK, lw=1.3)
    ax.plot([x - 0.2, x + 0.2], [y + 0.2, y + 0.2], color=INK, lw=1.3)
    ax.plot([x, x - 0.16], [y, y - 0.25], color=INK, lw=1.3)
    ax.plot([x, x + 0.16], [y, y - 0.25], color=INK, lw=1.3)
    label(ax, x, y - 0.45, name, size=9.2, color=INK, weight="bold")


def fig_usecase():
    W, H = 7.0, 5.6
    fig, ax = canvas(W, H)
    ax.add_patch(FancyBboxPatch((1.1, 0.2), 4.8, 5.2, boxstyle="square,pad=0", fc="white", ec=INK, lw=1.2))
    label(ax, 3.5, 5.22, "ATLAS", size=10.5, color=INK, weight="bold")
    user = ["Submit question\nand mode", "Watch the live\nknowledge graph", "Read agreement and\ncontradiction report",
            "Read ranked\nresearch gaps", "Ask the grounded\nchat"]
    system = ["Retrieve candidate\npapers", "Extract and verify\nclaims", "Judge claim\nrelationships", "Run gap detectors\nand rank gaps"]
    uy = [4.55, 3.7, 2.85, 2.0, 1.15]
    sy = [4.3, 3.35, 2.4, 1.45]
    for y, t in zip(uy, user):
        ax.add_patch(Ellipse((2.3, y), 2.0, 0.66, fc=BLUE_BG, ec=BLUE, lw=1.2))
        label(ax, 2.3, y, t, size=8.8, color=INK)
        ax.plot([0.65, 1.3], [2.85, y], color=MUTED, lw=0.9)
    for y, t in zip(sy, system):
        ax.add_patch(Ellipse((4.7, y), 2.0, 0.66, fc=GREEN_BG, ec=GREEN, lw=1.2))
        label(ax, 4.7, y, t, size=8.8, color=INK)
    for a, b in ((4.55, 4.3), (3.7, 3.35), (2.85, 2.4), (2.0, 1.45)):
        arrow(ax, 3.3, a, 3.7, b, color=MUTED, lw=0.9)
    actor(ax, 0.55, 2.8, "Researcher")
    actor(ax, 6.45, 3.9, "Scholarly\nAPIs")
    actor(ax, 6.45, 1.4, "LLM and\nGROBID\nservices")
    ax.plot([5.7, 6.25], [4.3, 4.2], color=MUTED, lw=0.9)
    for y in (3.35, 2.4):
        ax.plot([5.7, 6.25], [y, 1.8], color=MUTED, lw=0.9)
    save(fig, "b2_usecase.png")


# ── Blue Book: DFD level 0 and level 1 ─────────────────────────────────────────
def fig_dfd0():
    W, H = 7.0, 3.8
    fig, ax = canvas(W, H)
    ax.add_patch(Circle((3.5, 1.9), 0.95, fc=BLUE_BG, ec=BLUE, lw=1.5))
    label(ax, 3.5, 1.9, "0\nATLAS\nliterature\nsynthesis agent", size=9.2, color=INK, weight="bold")
    box(ax, 0.1, 1.5, 1.5, 0.8, "Researcher", edge=RED, fill=RED_BG)
    box(ax, 5.4, 2.7, 1.5, 0.9, "Scholarly APIs", "OpenAlex, arXiv,\nPubMed, S2", edge=RED, fill=RED_BG, bs=8.4)
    box(ax, 5.4, 0.2, 1.5, 0.9, "Open-access PDFs", "Unpaywall,\nEurope PMC", edge=RED, fill=RED_BG, ts=9.2, bs=8.4)
    arrow(ax, 1.6, 2.05, 2.55, 2.05)
    label(ax, 2.05, 2.28, "question, mode", size=8.4)
    arrow(ax, 2.55, 1.75, 1.6, 1.75)
    label(ax, 2.05, 1.5, "graph, reports,\nanswers", size=8.4)
    arrow(ax, 4.3, 2.5, 5.4, 3.0)
    label(ax, 4.55, 3.1, "search queries", size=8.4)
    arrow(ax, 5.4, 2.8, 4.4, 2.3)
    label(ax, 5.35, 2.35, "metadata,\ncitations", size=8.4)
    arrow(ax, 4.3, 1.3, 5.4, 0.8)
    label(ax, 4.5, 0.8, "fetch", size=8.4)
    arrow(ax, 5.4, 0.55, 4.1, 1.1)
    label(ax, 4.85, 0.3, "full-text PDF", size=8.4)
    save(fig, "b3_dfd0.png")


def fig_dfd1():
    W, H = 7.0, 5.7
    fig, ax = canvas(W, H, y0=0.8)
    box(ax, 2.3, 5.0, 2.6, 0.55, "Scholarly APIs and PDF sources", edge=RED, fill=RED_BG, ts=9.2)
    box(ax, 0.1, 3.75, 1.45, 0.8, "Researcher", edge=RED, fill=RED_BG)
    P = {"1": (1.9, 3.75, "1.0 Acquisition\nand seeding"), "2": (3.95, 3.75, "2.0 Foraging\nloop"),
         "4": (0.1, 2.35, "4.0 Synthesis\nand chat"), "3": (1.9, 2.35, "3.0 Gap\ndiscovery"),
         "5": (3.95, 2.35, "5.0 Grounding\ngate")}
    for k, (x, y, t) in P.items():
        box(ax, x, y, 1.6 if k != "4" else 1.45, 0.8, t, edge=BLUE, fill=BLUE_BG, ts=9.2)
    arrow(ax, 1.55, 4.15, 1.9, 4.15)
    label(ax, 1.72, 4.32, "question", size=8.4)
    arrow(ax, 3.5, 4.15, 3.95, 4.15)
    label(ax, 3.72, 4.32, "seeds", size=8.4)
    arrow(ax, 3.0, 5.0, 2.7, 4.55)
    label(ax, 2.35, 4.78, "metadata", size=8.4)
    arrow(ax, 4.2, 5.0, 4.6, 4.55)
    label(ax, 4.95, 4.78, "full text", size=8.4)
    arrow(ax, 4.75, 3.75, 4.75, 3.15)
    label(ax, 4.85, 3.45, "claims", size=8.4, ha="left")
    arrow(ax, 1.9, 2.75, 1.55, 2.75)
    label(ax, 1.72, 2.95, "gaps", size=8.4)
    arrow(ax, 0.82, 3.15, 0.82, 3.75)
    label(ax, 0.9, 3.45, "reports,\nanswers", size=8.4, ha="left")
    stores = [(1.7, 1.9, "D2  Neo4j", "knowledge graph"), (3.85, 1.9, "D1  Relational DB", "papers, claims, events"),
              (5.85, 1.1, "D3  Qdrant", "vectors")]
    for x, w, t, b in stores:
        ax.plot([x + w, x, x, x + w], [1.55, 1.55, 0.95, 0.95], color=INK, lw=1.2)
        ax.text(x + 0.1, 1.36, t, fontsize=9, weight="bold", va="center")
        ax.text(x + 0.1, 1.13, b, fontsize=8.4, color=MUTED, va="center")
    arrow(ax, 4.2, 2.35, 3.3, 1.55)
    arrow(ax, 4.75, 2.35, 4.75, 1.55)
    arrow(ax, 5.3, 2.35, 6.3, 1.55)
    label(ax, 5.95, 2.25, "verified claims", size=8.4, ha="left")
    arrow(ax, 2.6, 1.55, 2.6, 2.35)
    label(ax, 2.3, 1.95, "graph", size=8.4)
    save(fig, "b4_dfd1.png")


if __name__ == "__main__":
    for f in (fig_pipeline, fig_gate, fig_grounding, fig_pairs, fig_detectors, fig_architecture, fig_v0,
              fig_results1, fig_results2, fig_deployment, fig_gantt, fig_usecase, fig_dfd0, fig_dfd1):
        f()
