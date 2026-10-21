"""E4 — grounding gate effectiveness (docs/TESTING.md Part 2 E4).

"Report the drop rate per run [already in RunStats]. Then hand-check 50 verified claims:
how many are truly verbatim and correctly attributed? Target >= 95%. Also hand-check 20
dropped claims to show the gate isn't discarding good ones indiscriminately."

This script only prepares the two samples as a reviewable markdown checklist — the
hand-checking itself is a human judgment task, not something to automate away. Verified
claims come from the real `claims` table; dropped claims come from `dropped_claims`
(store/db.py's DroppedClaim — populated going forward from every run since this was
added; it will not contain anything from runs recorded before this feature existed).

Usage:
    PYTHONPATH=src python evaluation/e4_grounding_sample.py --out evaluation/e4_sample.md
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path
from typing import Any

import sqlalchemy as sa

from atlas.config import settings
from atlas.store import db
from atlas.store.db import ClaimRow, session_scope

SEED = 42


def sample_verified_claims(n: int, *, seed: int = SEED) -> list[dict[str, Any]]:
    with session_scope() as s:
        rows = s.execute(sa.select(ClaimRow).where(ClaimRow.verified.is_(True))).scalars().all()
    rng = random.Random(seed)
    picked = rng.sample(rows, min(n, len(rows)))
    return [
        {
            "run_id": r.run_id, "paper_id": r.paper_id, "section": r.section,
            "text": r.text, "quote": r.quote, "verify_method": r.verify_method,
        }
        for r in picked
    ]


def render_markdown(verified: list[dict[str, Any]], dropped: list[dict[str, Any]]) -> str:
    lines = [
        "# E4 grounding-gate hand-check (docs/TESTING.md E4)", "",
        "For each **verified** claim below, check the box only if the quote is genuinely "
        "verbatim in the source paper AND correctly attributed to it. Target: >=95%.",
        "", f"## Verified claims ({len(verified)})", "",
    ]
    for i, c in enumerate(verified, 1):
        lines += [
            f"### {i}. `{c['paper_id']}` — {c['section']} ({c['verify_method']})",
            f"- paraphrase: {c['text']}",
            f'- quote: "{c["quote"]}"',
            "- [ ] genuinely verbatim and correctly attributed", "",
        ]
    lines += [
        f"## Dropped claims ({len(dropped)})", "",
        "For each **dropped** attempt, check the box if the gate was right to drop it "
        "(i.e. it is NOT a real verbatim quote from the paper). An unchecked box here is "
        "evidence the gate is too strict, not too loose.", "",
    ]
    for i, c in enumerate(dropped, 1):
        lines += [
            f"### {i}. `{c['paper_id']}` — {c['section']} ({c['verify_method']})",
            f"- attempted paraphrase: {c['attempted_text']}",
            f'- attempted quote: "{c["attempted_quote"]}"',
            "- [ ] correctly dropped (not a real verbatim quote)", "",
        ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-verified", type=int, default=50)
    ap.add_argument("--n-dropped", type=int, default=20)
    ap.add_argument("--out", required=True, help="markdown path for the hand-check checklist")
    args = ap.parse_args()

    settings.ensure_dirs()
    verified = sample_verified_claims(args.n_verified)
    dropped = db.sample_dropped_claims(args.n_dropped)
    if not dropped:
        print(
            "warning: no rows in dropped_claims yet — this table was only just added "
            "(migration 0003), so runs recorded before it exist have nothing here. "
            "Run `alembic upgrade head`, then a fresh `atlas run`, before using this."
        )

    md = render_markdown(verified, dropped)
    Path(args.out).write_text(md, encoding="utf-8")
    print(f"wrote {len(verified)} verified + {len(dropped)} dropped claims to {args.out}")


if __name__ == "__main__":
    main()
