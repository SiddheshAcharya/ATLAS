"""E7 — cost and time, per mode (docs/TESTING.md Part 2 E7).

Aggregates every run already in the local store, grouped by mode, into the table
TESTING.md asks for: wall-clock, USD, tokens, API calls, cache hit rate, full-text
ratio, and — the "genuinely useful contribution" TESTING.md calls out — cost per paper.

Usage:
    PYTHONPATH=src python evaluation/e7_cost.py [--out evaluation/e7_cost.json]
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any

from atlas.config import settings
from atlas.store import db


def _wall_clock_seconds(summary: dict[str, Any]) -> float:
    started, finished = summary.get("started_at"), summary.get("finished_at")
    if not isinstance(started, str) or not isinstance(finished, str):
        return 0.0
    try:
        return (datetime.fromisoformat(finished) - datetime.fromisoformat(started)).total_seconds()
    except ValueError:
        return 0.0


def collect() -> list[dict[str, Any]]:
    rows = []
    for item in db.list_runs(limit=1000):
        summary = db.run_summary(item["run_id"])
        if summary is None or summary["status"] != "completed":
            continue
        reads = summary["reads"]
        n_read = len(reads)
        full_text = sum(1 for r in reads if r["depth"] == "full_text")
        breakdown = db.run_cost_breakdown(item["run_id"])
        rows.append(
            {
                "run_id": item["run_id"],
                "mode": summary["mode"],
                "papers_read": n_read,
                "full_text_ratio": round(full_text / n_read, 3) if n_read else 0.0,
                "wall_clock_seconds": _wall_clock_seconds(summary),
                **breakdown,
                "usd_per_paper": round(breakdown["usd"] / n_read, 5) if n_read else None,
            }
        )
    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_mode: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_mode[r["mode"]].append(r)

    out: dict[str, Any] = {}
    for mode, group in by_mode.items():
        out[mode] = {
            "n_runs": len(group),
            "mean_papers_read": round(mean(r["papers_read"] for r in group), 1),
            "mean_wall_clock_seconds": round(mean(r["wall_clock_seconds"] for r in group), 1),
            "mean_usd": round(mean(r["usd"] for r in group), 4),
            "mean_usd_per_paper": round(
                mean(r["usd_per_paper"] for r in group if r["usd_per_paper"] is not None), 5
            )
            if any(r["usd_per_paper"] is not None for r in group)
            else None,
            "mean_prompt_tokens": round(mean(r["prompt_tokens"] for r in group), 0),
            "mean_output_tokens": round(mean(r["output_tokens"] for r in group), 0),
            "mean_cache_hit_rate": round(mean(r["cache_hit_rate"] for r in group), 3),
            "mean_full_text_ratio": round(mean(r["full_text_ratio"] for r in group), 3),
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", help="path to save the JSON result (default: print only)")
    args = ap.parse_args()

    settings.ensure_dirs()
    rows = collect()
    result = {"per_run": rows, "per_mode": summarize(rows)}
    text = json.dumps(result, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
