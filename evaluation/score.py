#!/usr/bin/env python3
"""Objective scorer for both skill branches against the labeled gold set.

Reads a predictions file (one normalized prediction per gold case) and
snippets-gold.json, and reports per-case correctness + aggregate metrics.
Same scorer for Branch A and Branch B -> apples-to-apples.

Prediction schema (per case id):
  {
    "flagged_tables":      ["BSEG", ...],   # obsolete/changed tables the skill flagged
    "replacement_table":   "ACDOCA",        # primary replacement it named (or null)
    "field_maps_named":    ["RACCT","DOCLN","RBUKRS"],  # new field names it produced
    "blocker":             true|false,       # did it mark a BLOCKER / manual-redesign?
    "world_b_overflagged": true|false,       # did it wrongly mark a working BAPI as must-fix?
    "residual_count":      0                  # residual obsolete refs after its rewrite
  }

Usage: python3 score.py <predictions.json> [path-to-snippets-gold.json]
"""
from __future__ import annotations
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
GOLD = os.path.join(HERE, "ground-truth", "snippets-gold.json")


def up(x): return (x or "").upper()


def score_case(gold: dict, pred: dict) -> dict:
    exp_tables = {up(t) for t in gold.get("expected_obsolete_tables", [])}
    got_tables = {up(t) for t in pred.get("flagged_tables", [])}
    detect_ok = exp_tables.issubset(got_tables) if exp_tables else True

    exp_repl = up(gold.get("expected_replacement_table"))
    repl_ok = True if not exp_repl else exp_repl in up(pred.get("replacement_table"))

    # expected NEW field names that actually differ from the old name (renames only)
    exp_fields = {up(v) for k, v in gold.get("expected_field_maps", {}).items() if up(v) != up(k)}
    got_fields = {up(f) for f in pred.get("field_maps_named", [])}
    fields_ok = exp_fields.issubset(got_fields) if exp_fields else True

    blocker_ok = bool(gold.get("blocker")) == bool(pred.get("blocker"))
    precision_ok = not pred.get("world_b_overflagged", False)
    # residual only meaningful when a rewrite is expected (non-blocker)
    residual_ok = True if gold.get("blocker") else (pred.get("residual_count", 0) == 0)

    return {
        "detect": detect_ok, "replacement": repl_ok, "fields": fields_ok,
        "blocker": blocker_ok, "precision": precision_ok, "residual": residual_ok,
    }


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: score.py <predictions.json> [snippets-gold.json]", file=sys.stderr)
        return 2
    preds = json.load(open(sys.argv[1]))
    gold = json.load(open(sys.argv[2] if len(sys.argv) > 2 else GOLD))["cases"]

    dims = ["detect", "replacement", "fields", "blocker", "precision", "residual"]
    agg = {d: 0 for d in dims}
    n = 0
    print(f"{'case':<7}{'detect':<8}{'repl':<7}{'field':<7}{'block':<7}{'prec':<7}{'resid':<7}")
    for g in gold:
        cid = g["id"]
        if cid not in preds:
            print(f"{cid:<7}(no prediction)")
            continue
        n += 1
        s = score_case(g, preds[cid])
        for d in dims:
            agg[d] += 1 if s[d] else 0
        row = "".join(("Y" if s[d] else "·").ljust(8 if d == "detect" else 7) for d in dims)
        print(f"{cid:<7}{row}")
    print("-" * 50)
    print(f"{'TOTAL':<7}" + "".join(f"{agg[d]}/{n}".ljust(8 if d == 'detect' else 7) for d in dims))
    overall = sum(agg.values())
    print(f"\noverall checks passed: {overall}/{n*len(dims)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
