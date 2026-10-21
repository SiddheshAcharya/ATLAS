"""E6 — gap plausibility, the R3 tripwire (docs/TESTING.md Part 2 E6).

"Top 10 gaps per query, rated by a domain-familiar person as plausible / trivial /
wrong. Report the counts. Blind them to which detector produced each gap."

Writes two files:
- a blinded reviewer sheet (`--out`): statement + bounding papers + a blank rating box,
  with `type`/`found_by` deliberately withheld so the rating can't be influenced by
  knowing which detector found it
- an answer key (`--key-out`): gap_id -> detector type/rank, for scoring the filled-in
  sheet later without needing to re-run detection or un-blind anything by hand

The actual rating is a human judgment task — this only prepares the artifact.

Usage:
    PYTHONPATH=src python evaluation/e6_gap_review.py --run-id <id> --out sheet.md \\
        --key-out key.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from atlas.config import settings
from atlas.store.graph import GraphStore


def render_sheet(gaps: list[dict[str, object]]) -> str:
    lines = [
        "# E6 gap plausibility review (blinded)", "",
        "Rate each gap below: **plausible** (a real, non-obvious gap worth pursuing), "
        "**trivial** (technically true but not interesting), or **wrong** (not actually "
        "a gap — e.g. the corpus does address it, or the claim is misread). You are not "
        "told which detector found each one — that's deliberate.", "",
    ]
    for i, g in enumerate(gaps, 1):
        bounding = g.get("bounding_papers")
        papers = bounding if isinstance(bounding, list) else []
        lines.append(f"## Gap {i}")
        lines.append(f"\n{g['statement']}\n")
        lines.append("**Bounding papers:**")
        for p in papers:
            if isinstance(p, dict):
                role, title, year = p.get("role", "evidence"), p.get("title"), p.get("year", "n.d.")
                lines.append(f"- [{role}] {title} ({year})")
        lines.append("\n**Rating:** [ ] plausible  [ ] trivial  [ ] wrong\n")
        lines.append("**Notes:**\n")
        lines.append("---\n")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--out", required=True, help="blinded reviewer sheet (markdown)")
    ap.add_argument("--key-out", required=True, help="answer key: gap_id -> detector type (JSON)")
    args = ap.parse_args()

    settings.ensure_dirs()
    if not settings.neo4j_configured:
        raise SystemExit("neo4j not configured — no gaps to review")

    with GraphStore() as g:
        rows = g.gaps_for(args.run_id)
    top = sorted(rows, key=lambda r: r.get("rank") or 0)[: args.top]
    if not top:
        raise SystemExit(f"no gaps found for run {args.run_id!r} — run `atlas gaps` first")

    Path(args.out).write_text(render_sheet(top), encoding="utf-8")
    key = {
        str(g["gap_id"]): {"type": g["type"], "rank": g["rank"], "found_by": g.get("found_by")}
        for g in top
    }
    Path(args.key_out).write_text(json.dumps(key, indent=2), encoding="utf-8")
    print(f"wrote {len(top)} blinded gaps to {args.out}, answer key to {args.key_out}")


if __name__ == "__main__":
    main()
