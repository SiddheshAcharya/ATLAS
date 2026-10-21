"""E5 — a blinded, spreadsheet-friendly labelling sheet for a *human* (docs/TESTING.md E5).

The first E5 sample (evaluation/e5_sample.jsonl) was labelled by an AI assistant with the
model's verdict visible. This writes pairs for a person to label without seeing what ATLAS
said:

- `--csv`: one row per claim pair — both claims, both verbatim quotes, an empty `your_label`
  column (open in Excel / Google Sheets, fill it in, save as CSV)
- `--key`: JSON pair -> the model's verdict, confidence and claim ids, for scoring afterwards

Pairs are pooled from several runs and stratified by the model's label (12 each by default),
because CONTRADICTS / REPLICATES are rare in any one run. Score a filled sheet with:
    PYTHONPATH=src python evaluation/e5_blind_sheet.py --score filled.csv --key key.json

Usage:
    PYTHONPATH=src python evaluation/e5_blind_sheet.py --run-id id1,id2 --csv e5_human.csv \\
        --key e5_human_key.json
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from atlas.judge import eval as je
from atlas.store.db import judged_pairs

INSTRUCTIONS = """How to label (one label per row, in the `your_label` column):
SUPPORTS    - B gives evidence that A's claim is true, in a comparable setting.
CONTRADICTS - B asserts something that cannot be true if A is true, in a comparable setting.
EXTENDS     - B builds on A's own result or method (new setting, method or scale).
REPLICATES  - B directly reproduces A's setup.
DIFF_SCOPE  - related question, but different systems, populations, datasets, metrics or conditions,
              so neither is evidence for or against the other (incl. conflicts explained by scope).
UNRELATED   - different questions.
Two papers that each describe their OWN device are about different things: usually DIFF_SCOPE
(same question) or UNRELATED - not SUPPORTS/EXTENDS/CONTRADICTS just because the parts overlap.
"""


def write_sheet(run_ids: list[str], csv_path: Path, key_path: Path, per_label: int) -> int:
    rows = [row for rid in run_ids for row in judged_pairs(rid)]
    sample = je.stratified_sample(rows, per_label=per_label)
    key = {}
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:  # BOM: Excel reads UTF-8
        w = csv.writer(fh)
        w.writerow(["pair", "claim_a", "quote_a", "claim_b", "quote_b", "your_label", "notes"])
        for i, r in enumerate(sample, start=1):
            w.writerow([i, r["a_text"], r["a_quote"], r["b_text"], r["b_quote"], "", ""])
            key[str(i)] = {
                "type": r["type"], "confidence": r["confidence"], "judged_by": r["judged_by"],
                "a_claim_id": r.get("a_claim_id"), "b_claim_id": r.get("b_claim_id"),
            }
    key_path.write_text(json.dumps(key, indent=1), encoding="utf-8")
    return len(sample)


def score(csv_path: Path, key_path: Path) -> dict[str, object]:
    key = json.loads(key_path.read_text(encoding="utf-8"))
    rows = []
    with csv_path.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            gold = (r.get("your_label") or "").strip().upper().replace(" ", "_")
            if gold and r["pair"] in key:
                rows.append({"type": key[r["pair"]]["type"], "gold": gold})
    tmp = csv_path.with_suffix(".scored.jsonl")
    tmp.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return je.score(tmp)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", help="comma-separated runs to pool pairs from")
    ap.add_argument("--csv", help="sheet to write (with --run-id) or to score (with --score)")
    ap.add_argument("--key", required=True, help="answer-key JSON (written, or read to score)")
    ap.add_argument("--per-label", type=int, default=12)
    ap.add_argument("--score", help="a filled-in CSV to score against --key")
    args = ap.parse_args()
    if args.score:
        print(json.dumps(score(Path(args.score), Path(args.key)), indent=2))
        return
    if not (args.run_id and args.csv):
        raise SystemExit("pass --run-id and --csv to write a sheet, or --score and --key")
    n = write_sheet(
        [r.strip() for r in args.run_id.split(",")], Path(args.csv), Path(args.key),
        args.per_label,
    )
    Path(args.csv).with_suffix(".instructions.txt").write_text(INSTRUCTIONS, encoding="utf-8")
    print(f"wrote {n} blinded pairs to {args.csv} (+ instructions, key {args.key})")


if __name__ == "__main__":
    main()
