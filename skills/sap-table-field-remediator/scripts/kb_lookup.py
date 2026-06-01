#!/usr/bin/env python3
"""kb_lookup — cheap KB lookups for the ReAct loop (Branch B).

This is a *retrieval* helper, NOT a rule engine. It only fetches and prints rows
from the knowledge base so the model's per-finding lookup step is one call instead
of re-reading whole JSON files. All classification/rewrite reasoning lives in
SKILL.md; this script never decides "World A vs B" or proposes a fix on its own —
it returns the cited KB row and the model reasons over it (w03 hallucination
mitigation: every recommendation must trace to a row this prints).

Usage:
  python3 kb_lookup.py --table BSEG          # one table row (status, replacement, cds_view, world, source)
  python3 kb_lookup.py --field BSEG.HKONT    # one field row (ecc->s4 field map)
  python3 kb_lookup.py --field HKONT         # field by name across all tables
  python3 kb_lookup.py --bapi BAPI_SALESORDER_CHANGE   # world-b allowlist entry
  python3 kb_lookup.py --table BSEG --fields # table row + all its field rows
  python3 kb_lookup.py --all-tables          # list every obsolete/changed table token
  add --json for machine-readable output.

Exit 0 if found, 3 if the token is NOT in the KB (i.e. likely a still-valid
table like MARA/VBAK — caller MUST NOT flag it as removed; REQ-008).
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.normpath(os.path.join(HERE, "..", "references"))


def _load(name: str):
    with open(os.path.join(REF, name)) as fh:
        return json.load(fh)


def find_table(tbl: str):
    tbl = tbl.upper()
    for r in _load("table-mappings.json"):
        if r["ecc_table"].upper() == tbl:
            return r
    return None


def find_fields(tbl: str | None, fld: str | None):
    out = []
    for r in _load("field-mappings.json"):
        if tbl and r["ecc_table"].upper() != tbl.upper():
            continue
        if fld and r["ecc_field"].upper() != fld.upper():
            continue
        out.append(r)
    return out


def find_bapi(obj: str):
    doc = _load("world-b-allowlist.json")
    for r in doc.get("entries", []):
        if r["object"].upper() == obj.upper():
            return r
    return None


def main() -> int:
    args = sys.argv[1:]
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    with_fields = "--fields" in args
    args = [a for a in args if a != "--fields"]

    def emit(obj, human):
        if as_json:
            print(json.dumps(obj, indent=2, ensure_ascii=False))
        else:
            print(human)

    if not args:
        print(__doc__)
        return 2

    if args[0] == "--all-tables":
        rows = _load("table-mappings.json")
        if as_json:
            print(json.dumps([r["ecc_table"] for r in rows], indent=2))
        else:
            for r in rows:
                print(f"{r['ecc_table']:<8} {r['status']:<20} world={r['world']} "
                      f"rel_dep={r['release_dependent']} cds={r['cds_view']}")
        return 0

    if args[0] == "--table" and len(args) > 1:
        tbl = args[1]
        row = find_table(tbl)
        if row is None:
            emit({"found": False, "token": tbl,
                  "note": "NOT in KB -> treat as still-valid (do NOT flag removed; REQ-008)"},
                 f"NOT-IN-KB: {tbl.upper()} is not an obsolete/changed table. "
                 f"Do NOT flag it as removed (REQ-008). Still-valid; at most 'verify fields on target'.")
            return 3
        result = {"table": row}
        if with_fields:
            result["fields"] = find_fields(tbl, None)
        if as_json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            cds = row["cds_view"] or "(none — manual review)"
            print(f"TABLE {row['ecc_table']}  status={row['status']}  world={row['world']}  "
                  f"release_dependent={row['release_dependent']}")
            print(f"  replacement : {row['s4_replacement']}")
            print(f"  cds_view    : {cds}")
            print(f"  fix_pattern : {row['fix_pattern']}")
            print(f"  source      : {row['source']}")
            if with_fields:
                for f in find_fields(tbl, None):
                    print(f"  field {f['ecc_field']:<10} -> {f['s4_table']}.{f['s4_field']:<8} "
                          f"({f['change_type']}; {f['notes']}) [src:{f['source']}]")
        return 0

    if args[0] == "--field" and len(args) > 1:
        spec = args[1]
        tbl, fld = (spec.split(".", 1) + [None])[:2] if "." in spec else (None, spec)
        rows = find_fields(tbl, fld)
        if not rows:
            emit({"found": False, "token": spec,
                  "note": "field not in KB -> not a known rename/move; verify on target"},
                 f"NOT-IN-KB: field {spec} has no KB mapping. Not a known rename/move.")
            return 3
        if as_json:
            print(json.dumps(rows, indent=2, ensure_ascii=False))
        else:
            for f in rows:
                print(f"FIELD {f['ecc_table']}.{f['ecc_field']} -> {f['s4_table']}.{f['s4_field']}  "
                      f"({f['change_type']}; world={f['world']}; rel_dep={f['release_dependent']}; "
                      f"{f['notes']}) [src:{f['source']}]")
        return 0

    if args[0] == "--bapi" and len(args) > 1:
        obj = args[1]
        row = find_bapi(obj)
        if row is None:
            emit({"found": False, "token": obj,
                  "note": "not in World-B allowlist; if it is a working released BAPI it is still not ATC-forced"},
                 f"NOT-IN-ALLOWLIST: {obj.upper()} not listed. If working+released it is World B (key-only), not ATC-forced (REQ-007).")
            return 3
        if as_json:
            print(json.dumps(row, indent=2, ensure_ascii=False))
        else:
            print(f"BAPI/FM {row['object']}  world={row['world']}  atc_finding={row['atc_finding']}")
            print(f"  modernization_target : {row['modernization_target']}")
            print(f"  note                 : {row['note']}")
        return 0

    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
