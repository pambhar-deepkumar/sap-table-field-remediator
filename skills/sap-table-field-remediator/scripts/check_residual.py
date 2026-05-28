#!/usr/bin/env python3
"""Residual-reference checker — the computational migration sensor (course w04).

Scans ABAP text for references that should NOT survive an S/4HANA remediation:
  - obsolete tables (status ABOLISHED or COMPATIBILITY VIEW in the knowledge base)
  - MATNR legacy length access (offset `+..(18)`, `LENGTH 18`)
  - the renamed field-length token `VBTYP` (should be `VBTYPL`)

Still-valid tables (RESTRUCTURED / not in the KB, e.g. MARA, VBAK, MSEG) are NOT
flagged — that guards against the World-A/B false-positive failure mode.

Dual use:
  - DETECT (pre-rewrite): list obsolete references in legacy code.
  - VERIFY (post-rewrite): exit non-zero if any residual obsolete reference remains.

Usage:
  python3 check_residual.py <file.abap>        # human summary, exit 1 if residuals
  python3 check_residual.py - < snippet.abap   # read stdin
  python3 check_residual.py <file> --json      # machine-readable findings
"""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REF_DIR = os.path.normpath(os.path.join(HERE, "..", "references"))

# Statuses meaning "must not appear in remediated S/4 code".
MUST_REPLACE_STATUS = {"ABOLISHED", "COMPATIBILITY VIEW"}


def load_obsolete_tables() -> dict[str, dict]:
    with open(os.path.join(REF_DIR, "table-mappings.json")) as fh:
        rows = json.load(fh)
    out = {}
    for r in rows:
        status = (r.get("status") or "").upper()
        if any(s in status for s in MUST_REPLACE_STATUS):
            out[r["ecc_table"].upper()] = r
    return out


def strip_comments(line: str) -> str:
    """Drop ABAP comments: full-line '*' and inline '"'."""
    s = line.lstrip()
    if s.startswith("*"):
        return ""
    # remove inline " comment (naive; fine for detection)
    q = line.find('"')
    return line[:q] if q != -1 else line


def scan(text: str) -> list[dict]:
    obsolete = load_obsolete_tables()
    findings: list[dict] = []
    for n, raw in enumerate(text.splitlines(), start=1):
        line = strip_comments(raw)
        if not line.strip():
            continue
        upper = line.upper()

        # obsolete tables (word-boundary token match)
        for tbl, meta in obsolete.items():
            if re.search(rf"\b{re.escape(tbl)}\b", upper):
                findings.append({
                    "type": "obsolete_table", "token": tbl, "line": n,
                    "status": meta.get("status"), "replacement": meta.get("s4_replacement"),
                    "cds_view": meta.get("cds_view"), "world": meta.get("world"),
                    "release_dependent": meta.get("release_dependent"),
                    "text": raw.strip(),
                })

        # MATNR legacy length access
        if re.search(r"MATNR\b.*\+\s*\d*\s*\(\s*18\s*\)", upper) or re.search(r"\+\s*0\s*\(\s*18\s*\)", upper):
            findings.append({"type": "matnr_offset_18", "token": "matnr+0(18)", "line": n,
                             "release_dependent": True, "world": "A", "text": raw.strip()})
        if re.search(r"\bLENGTH\s+18\b", upper) or re.search(r"\bCHAR18\b", upper):
            findings.append({"type": "char18_decl", "token": "LENGTH 18", "line": n,
                             "release_dependent": True, "world": "A", "text": raw.strip()})

        # VBTYP not yet migrated to VBTYPL
        if re.search(r"\bVBTYP\b", upper):
            findings.append({"type": "field_length_vbtyp", "token": "VBTYP", "line": n,
                             "replacement_field": "VBTYPL", "release_dependent": True,
                             "world": "A", "text": raw.strip()})
    return findings


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    as_json = "--json" in sys.argv
    if not args:
        print("usage: check_residual.py <file.abap|-> [--json]", file=sys.stderr)
        return 2
    src = args[0]
    text = sys.stdin.read() if src == "-" else open(src).read()

    findings = scan(text)
    if as_json:
        print(json.dumps({"residual_count": len(findings), "findings": findings}, indent=2))
    else:
        if not findings:
            print("CLEAN: no residual obsolete table/field references.")
        else:
            print(f"RESIDUAL: {len(findings)} obsolete reference(s) remain:")
            for f in findings:
                rd = " [release-dependent]" if f.get("release_dependent") else ""
                print(f"  L{f['line']:>4} {f['type']:<20} {f['token']}{rd}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
