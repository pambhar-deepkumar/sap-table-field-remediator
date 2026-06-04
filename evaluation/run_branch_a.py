#!/usr/bin/env python3
"""Run Branch A (deterministic remediate.py) over the 12 gold snippets and the
Input Program, emit normalized predictions for score.py, and print an
Input-Program finding summary.

Usage: python3 run_branch_a.py
Writes: predictions-a.json (next to this script)
"""
from __future__ import annotations
import json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
GOLD = os.path.join(HERE, "ground-truth", "snippets-gold.json")
INPUT_PROG = os.path.join(HERE, "ground-truth", "input-program.abap")
REMEDIATE = "/Users/deep/Uni/ss2026/ai-coding/project/wt-skill-A/skills/sap-table-field-remediator/scripts/remediate.py"
WORLD_B_JSON = "/Users/deep/Uni/ss2026/ai-coding/project/wt-skill-A/skills/sap-table-field-remediator/references/world-b-allowlist.json"

WORLD_B = {e["object"].upper() for e in json.load(open(WORLD_B_JSON))["entries"]}


def run_remediate(code: str) -> dict:
    p = subprocess.run([sys.executable, REMEDIATE, "-", "--json"],
                       input=code, capture_output=True, text=True)
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        return {"findings": [], "rewrite_notes": [], "residual_count": -1, "rewritten": "", "_err": p.stderr}


def tokens(*texts) -> set[str]:
    out = set()
    for t in texts:
        out |= {w.upper() for w in re.split(r"[^A-Za-z0-9_]+", t or "") if w}
    return out


def normalize(res: dict) -> dict:
    findings = res.get("findings", [])
    tbl = [f for f in findings if f.get("kind") == "table"]
    flagged_tables = [f.get("token", "") for f in tbl]
    repl_blob = " ".join(
        f"{f.get('replacement','')} {f.get('cds_view','')} {f.get('category','')} {f.get('fix_pattern','')}"
        for f in tbl
    ) + " " + res.get("rewritten", "")
    notes = " ".join(res.get("rewrite_notes", []))
    field_named = tokens(res.get("rewritten", ""), notes)
    world_b_over = any(
        f.get("token", "").upper() in WORLD_B and (f.get("world") == "A" or f.get("blocker"))
        for f in findings
    )
    return {
        "flagged_tables": flagged_tables,
        "replacement_table": repl_blob,
        "field_maps_named": sorted(field_named),
        "blocker": any(f.get("blocker") for f in findings),
        "world_b_overflagged": world_b_over,
        "residual_count": res.get("residual_count", -1),
    }


def main() -> int:
    gold = json.load(open(GOLD))["cases"]
    preds = {}
    for g in gold:
        preds[g["id"]] = normalize(run_remediate(g["ecc_code"]))
    out = os.path.join(HERE, "predictions-a.json")
    json.dump(preds, open(out, "w"), indent=2)
    print(f"wrote {out} ({len(preds)} cases)")

    # Input Program summary (Tier 2)
    res = run_remediate(open(INPUT_PROG).read())
    f = res.get("findings", [])
    by_kind = {}
    for x in f:
        by_kind[x.get("kind", "?")] = by_kind.get(x.get("kind", "?"), 0) + 1
    world_a = sorted({x["token"] for x in f if x.get("world") == "A" and x.get("kind") in ("table", "field")})
    routed = sorted({x.get("category", "?") for x in f if x.get("kind") == "statement"})
    blockers = sorted({x["token"] for x in f if x.get("blocker")})
    print("\nInput Program (Branch A):")
    print("  findings by kind:", by_kind)
    print("  World-A table/field tokens:", world_a)
    print("  routed statement categories:", routed)
    print("  blockers:", blockers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
