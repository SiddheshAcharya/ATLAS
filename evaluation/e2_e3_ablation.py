"""E2 (ablation of scoring components) + E3 (bridge promotion value), docs/TESTING.md
Part 2.

Runs standard mode once per config, each config transiently editing config/scoring.yaml
(backed up and always restored, even on failure/Ctrl-C) so each `atlas run` subprocess
reads a fresh, correctly-configured file. Subprocess, not an in-process loop.run() call,
specifically so config_files.scoring()'s @lru_cache never goes stale between configs —
each config gets a genuinely fresh Python process, identical to a real `atlas run`.

E2 configs: full, -pagerank, -novelty, -contest, -recency, relevance_only (all four
zeroed). E3 configs: bridge_on (already the repo default), bridge_off.

Scope note: TESTING.md doesn't fix a paper count for the sweep, only "standard mode"
(default cap 25). Run with --max-papers to cap lower — this script defaults to 10 to
keep an 8-config sweep tractable on free-tier LLM pacing + this laptop (~15-45 min/run
at 25 papers per earlier E7 data; a firm number matters less here than every config
seeing the *same* number).

Usage:
    PYTHONPATH=src python evaluation/e2_e3_ablation.py --query "IoT devices for women safety" \
        --max-papers 10 --out evaluation/e2_e3_results.json
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SCORING_PATH = REPO_ROOT / "config" / "scoring.yaml"
SWEEP_BACKUP = REPO_ROOT / "config" / ".scoring.yaml.sweep-backup"

E2_ZERO_KEYS: dict[str, list[str]] = {
    "full": [],
    "-pagerank": ["pagerank"],
    "-novelty": ["novelty"],
    "-contest": ["contest"],
    "-recency": ["recency"],
    "relevance_only": ["pagerank", "novelty", "contest", "recency"],
}


def _load_scoring() -> dict[str, Any]:
    return dict(yaml.safe_load(SCORING_PATH.read_text(encoding="utf-8")))


def _write_scoring(cfg: dict[str, Any]) -> None:
    SCORING_PATH.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")


def _e2_variant(base: dict[str, Any], zero_keys: list[str]) -> dict[str, Any]:
    cfg = copy.deepcopy(base)
    for k in zero_keys:
        cfg["weights"][k] = 0.0
    return cfg


def _e3_variant(base: dict[str, Any], *, bridge_enabled: bool) -> dict[str, Any]:
    cfg = copy.deepcopy(base)
    cfg["bridge"]["enabled"] = bridge_enabled
    return cfg


def run_atlas(query: str, max_papers: int, timeout_s: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable, "-m", "atlas.cli", "run", query,
            "--mode", "standard", "--max-papers", str(max_papers),
        ],
        cwd=REPO_ROOT, capture_output=True, timeout=timeout_s,
        env={**os.environ, "PYTHONPATH": "src"},
        # Windows: subprocess.run's text-mode decoding otherwise falls back to the
        # console's cp1252 default, but the child (atlas.cli, console_encoding.py)
        # writes UTF-8 — a real UnicodeDecodeError in subprocess's internal reader
        # thread on the first live run of this script (noisy, and lost that config's
        # captured stdout, though not the run itself — results come from querying the
        # DB, not from parsing stdout).
        encoding="utf-8", errors="replace",
    )


def latest_run_id() -> str:
    from atlas.store import db

    runs = db.list_runs(limit=1)
    if not runs:
        raise RuntimeError("no runs found after invoking atlas run — something went wrong")
    return str(runs[0]["run_id"])


def run_config(label: str, query: str, max_papers: int, timeout_s: int) -> dict[str, Any]:
    print(f"--- {label}: starting ---", flush=True)
    started = time.monotonic()
    proc = run_atlas(query, max_papers, timeout_s)
    elapsed = time.monotonic() - started
    if proc.returncode != 0:
        print(f"--- {label}: FAILED (exit {proc.returncode}) ---", flush=True)
        # Printing the child's captured output straight to this console can itself crash
        # (Windows console default codepage can't encode everything structlog/Rich emit),
        # which used to mask the real failure behind a UnicodeEncodeError. Write it to a
        # file instead — that's never lossy — and only best-effort echo to the console.
        dump_path = REPO_ROOT / "evaluation" / f"_failure_{label.replace(':', '_')}.log"
        dump_path.write_text(
            f"exit code: {proc.returncode}\n\n--- stdout (tail) ---\n{proc.stdout[-4000:]}\n"
            f"\n--- stderr (tail) ---\n{proc.stderr[-4000:]}\n",
            encoding="utf-8",
        )
        try:
            print(proc.stdout[-2000:], proc.stderr[-2000:])
        except UnicodeEncodeError:
            print(f"(console can't render it — see {dump_path})", flush=True)
        return {
            "label": label, "ok": False, "elapsed_s": round(elapsed, 1),
            "error": f"exit {proc.returncode} — see {dump_path.name}",
        }

    run_id = latest_run_id()
    from atlas.config import settings
    from atlas.store import db

    summary = db.run_summary(run_id)
    reads = summary["reads"] if summary else []
    result: dict[str, Any] = {
        "label": label, "ok": True, "run_id": run_id, "elapsed_s": round(elapsed, 1),
        "papers_read": len(reads),
        "stop_reason": summary["stop_reason"] if summary else None,
        "relations_judged": sum((summary["relations_by_type"] or {}).values()) if summary else 0,
        "contradictions": (summary["relations_by_type"] or {}).get("CONTRADICTS", 0)
        if summary else 0,
    }
    if settings.neo4j_configured:
        from atlas.store.graph import GraphStore

        with GraphStore() as g:
            attrs = g.paper_attrs(run_id)
        clusters = {a.get("cluster_id") for a in attrs.values() if a.get("cluster_id") is not None}
        result["clusters_covered"] = len(clusters)
    print(f"--- {label}: done in {elapsed:.0f}s, {result['papers_read']} papers ---", flush=True)
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--query", required=True)
    ap.add_argument("--max-papers", type=int, default=10)
    ap.add_argument(
        "--timeout-s", type=int, default=15000,
        help="per-run subprocess timeout — standard mode's own budget is 14400s "
        "(scoring.yaml modes.standard.max_minutes: 240), so this must stay comfortably above "
        "that or a run finishing near its own budget gets killed by this timeout instead",
    )
    ap.add_argument("--out", required=True)
    ap.add_argument(
        "--skip-e3", action="store_true", help="E2 (ablation) only, skip the bridge on/off pair"
    )
    ap.add_argument(
        "--resume", help="path to a previous --out JSON to keep and append to (skips its labels)"
    )
    ap.add_argument(
        "--only", help="comma-separated subset of E2 config labels to run (e.g. -recency,"
        "relevance_only) — for resuming a partial sweep without re-running finished configs"
    )
    args = ap.parse_args()

    # A prior run of this script killed externally (not Ctrl-C, not a Python exception —
    # e.g. the whole host process torn down) skips the `finally` block entirely and can
    # leave scoring.yaml stuck mid-sweep. Happened once already (2026-09-15 session
    # restart). Refuse to adopt a dirty file as "the original" to restore back to later.
    # The backup file is the guard (works without git): it exists only while a sweep is
    # running, so finding one at startup means the last sweep died without restoring.
    if SWEEP_BACKUP.exists():
        raise SystemExit(
            f"{SWEEP_BACKUP} exists — a previous sweep died before restoring "
            "config/scoring.yaml. Copy it back over config/scoring.yaml (it is the "
            "pre-sweep original), delete it, then re-run."
        )

    original = SCORING_PATH.read_text(encoding="utf-8")
    SWEEP_BACKUP.write_text(original, encoding="utf-8")
    base = _load_scoring()
    results: list[dict[str, Any]] = (
        json.loads(Path(args.resume).read_text(encoding="utf-8")) if args.resume else []
    )
    already_done = {r["label"] for r in results}
    only = set(args.only.split(",")) if args.only else None

    def run_and_record(label: str) -> None:
        # one config's failure (timeout, transient network blip, ...) must not lose
        # every config after it — record the failure and keep going.
        try:
            results.append(run_config(label, args.query, args.max_papers, args.timeout_s))
        except subprocess.TimeoutExpired:
            print(f"--- {label}: TIMED OUT after {args.timeout_s}s ---", flush=True)
            results.append({"label": label, "ok": False, "error": "timeout"})
        except Exception as e:  # broad and deliberate — must not abort the sweep
            print(f"--- {label}: FAILED — {e} ---", flush=True)
            results.append({"label": label, "ok": False, "error": str(e)})
        Path(args.out).write_text(json.dumps(results, indent=2), encoding="utf-8")  # checkpoint

    try:
        for label, zero_keys in E2_ZERO_KEYS.items():
            if f"e2:{label}" in already_done or (only is not None and label not in only):
                continue
            _write_scoring(_e2_variant(base, zero_keys))
            run_and_record(f"e2:{label}")

        if not args.skip_e3:
            for label, enabled in (("e3:bridge_on", True), ("e3:bridge_off", False)):
                if label in already_done:
                    continue
                _write_scoring(_e3_variant(base, bridge_enabled=enabled))
                run_and_record(label)
    finally:
        SCORING_PATH.write_text(original, encoding="utf-8")
        SWEEP_BACKUP.unlink(missing_ok=True)
        print("--- scoring.yaml restored to original ---", flush=True)

    Path(args.out).write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
