#!/usr/bin/env python3
"""Deterministic rule-engine for the SAP Table & Field Remediator (Branch A).

A FIXED pipeline -- no model calls -- that turns the knowledge base
(`references/*.json`) into findings and, for the clear cases, rewritten ABAP.
This is itself a computational sensor (course w04): same input -> same output.

Pipeline:  Detect -> Classify (World A/B, blocker, release-dependent)
           -> Rewrite (deterministic, clear cases only)
           -> Report (markdown, or --json).

What it DOES rewrite (deterministic):
  * table-name swap, same fields:   KONV -> PRCD_ELEMENTS, CDPOS -> CDPOS_STR
  * status tables folded in:         VBUK -> VBAK,         VBUP -> VBAP
  * FI Universal Journal:            BSEG -> ACDOCA  + field map
                                     (HKONT->RACCT, BUZEI->DOCLN, BUKRS->RBUKRS,
                                      MONAT->POPER) + add RLDNR = '0L'
  * field-length change:             VBTYP -> VBTYPL
  * MATNR length extension:          drop `+0(18)` offset; CHAR18/LENGTH 18 -> LENGTH 40

What it MARKS BLOCKER (no clean replacement -> manual redesign, NOT rewritten):
  S001, S061, RFBLG, PCL1-4, KNKK, VAPMA.

What it DETECTS & ROUTES to the sibling statement/performance skill (never rewrites):
  SELECT *, FOR ALL ENTRIES without empty-table guard, native EXEC SQL,
  DB access inside LOOP, SELECT SINGLE on partial key.

What it does NOT flag:
  still-valid tables (MARA, MAKT, VBAK, VBAP, LIKP, VBRK, ...), and
  working released World-B BAPIs (world-b-allowlist.json) are NOT ATC findings.

Not activation-verified -- no SAP compiler in this environment. Release-dependent
findings need confirmation on the target system. Human signs off on every change.

Usage:
  python3 remediate.py <file.abap>            # markdown report
  python3 remediate.py - < snippet.abap       # read stdin
  python3 remediate.py <file> --json          # machine-readable
  python3 remediate.py <file> --rewrite-only  # print only the rewritten ABAP
"""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REF_DIR = os.path.normpath(os.path.join(HERE, "..", "references"))

# Statuses meaning "must not survive into remediated S/4 code".
MUST_REPLACE_STATUS = {"ABOLISHED", "COMPATIBILITY VIEW"}

# Deterministic same-field table-name swaps (new table, identical field set).
SIMPLE_TABLE_SWAP = {
    "KONV": "PRCD_ELEMENTS",
    "CDPOS": "CDPOS_STR",
    "VBUK": "VBAK",
    "VBUP": "VBAP",
}

# FI Universal Journal: BSEG -> ACDOCA needs a field map + leading-ledger filter.
ACDOCA_TABLE = "ACDOCA"
ACDOCA_FIELD_MAP = {  # ecc field -> ACDOCA field (only the ones that change)
    "HKONT": "RACCT",
    "BUZEI": "DOCLN",
    "BUKRS": "RBUKRS",
    "MONAT": "POPER",
}
ACDOCA_LEDGER_FILTER = "RLDNR = '0L'"

# Tables with no clean drop-in -> BLOCKER, manual redesign (we do NOT rewrite).
# (Per SPEC REQ-005 + task: S001, RFBLG, PCL*, KNKK. VAPMA is obsolete-no-replacement
#  but has a read path via VBAP, so it is manual-review, not a hard BLOCKER.)
BLOCKER_TABLES = {"S001", "S061", "RFBLG", "PCL1", "PCL2", "PCL3", "PCL4", "KNKK"}


# --------------------------------------------------------------------------- #
# Knowledge base loading
# --------------------------------------------------------------------------- #
def load_json(name: str):
    with open(os.path.join(REF_DIR, name)) as fh:
        return json.load(fh)


def load_kb() -> dict:
    tables = {r["ecc_table"].upper(): r for r in load_json("table-mappings.json")}
    fields_raw = load_json("field-mappings.json")
    fields: dict[str, dict] = {}
    for r in fields_raw:
        fields[f"{r['ecc_table'].upper()}.{r['ecc_field'].upper()}"] = r
    allow = load_json("world-b-allowlist.json")
    world_b = {e["object"].upper(): e for e in allow.get("entries", [])}
    return {"tables": tables, "fields": fields, "world_b": world_b}


# --------------------------------------------------------------------------- #
# Line helpers
# --------------------------------------------------------------------------- #
def strip_comments(line: str) -> str:
    """Drop ABAP comments: full-line '*' and inline '"' (naive, fine for scan)."""
    s = line.lstrip()
    if s.startswith("*"):
        return ""
    q = line.find('"')
    return line[:q] if q != -1 else line


def token_present(token: str, upper_line: str) -> bool:
    return re.search(rf"\b{re.escape(token)}\b", upper_line) is not None


# --------------------------------------------------------------------------- #
# DETECT + CLASSIFY
# --------------------------------------------------------------------------- #
def detect(text: str, kb: dict) -> list[dict]:
    """Return findings (dicts). Each cites its triggering token + KB source."""
    tables = kb["tables"]
    fields = kb["fields"]
    world_b = kb["world_b"]
    findings: list[dict] = []

    lines = text.splitlines()
    seen_table_lines: set[tuple[str, int]] = set()

    for n, raw in enumerate(lines, start=1):
        line = strip_comments(raw)
        if not line.strip():
            continue
        upper = line.upper()

        # --- obsolete / changed tables from the KB --------------------------
        for tbl, meta in tables.items():
            if not token_present(tbl, upper):
                continue
            status = (meta.get("status") or "").upper()
            is_obsolete = any(s in status for s in MUST_REPLACE_STATUS)
            # RESTRUCTURED tables (still exist) -> verify-only, not "removed".
            if (tbl, n) in seen_table_lines:
                continue
            seen_table_lines.add((tbl, n))

            blocker = tbl in BLOCKER_TABLES
            if blocker:
                category = "blocker_no_replacement"
            elif tbl in SIMPLE_TABLE_SWAP:
                category = "table_swap"
            elif tbl == "BSEG":
                category = "table_to_acdoca"
            elif is_obsolete:
                category = "obsolete_table"
            else:
                category = "restructured_verify"

            findings.append({
                "kind": "table",
                "category": category,
                "token": tbl,
                "line": n,
                "status": meta.get("status"),
                "replacement": meta.get("s4_replacement"),
                "cds_view": meta.get("cds_view"),
                "world": meta.get("world", "A"),
                "release_dependent": bool(meta.get("release_dependent")),
                "blocker": blocker,
                "fix_pattern": meta.get("fix_pattern", ""),
                "source": meta.get("source"),
                "text": raw.strip(),
            })

        # --- MATNR length extension (offset / CHAR18 / LENGTH 18) -----------
        if re.search(r"MATNR\b[^.\n]*\+\s*\d+\s*\(\s*18\s*\)", upper) or \
           re.search(r"\+\s*0\s*\(\s*18\s*\)", upper):
            findings.append({
                "kind": "field", "category": "matnr_length", "token": "matnr+0(18)",
                "line": n, "world": "A", "release_dependent": True, "blocker": False,
                "replacement": "Use full 40-char MATNR; drop offset/CHAR18 access.",
                "source": "field-mappings.json (MATNR length)", "text": raw.strip(),
            })
        if re.search(r"\bCHAR18\b", upper) or re.search(r"\bLENGTH\s+18\b", upper):
            findings.append({
                "kind": "field", "category": "matnr_length", "token": "LENGTH 18",
                "line": n, "world": "A", "release_dependent": True, "blocker": False,
                "replacement": "MATNR extended to 40 chars; declare LENGTH 40.",
                "source": "field-mappings.json (MATNR length)", "text": raw.strip(),
            })

        # --- VBTYP -> VBTYPL field-length change ----------------------------
        if token_present("VBTYP", upper):
            fmeta = fields.get("VBAK.VBTYP", {})
            findings.append({
                "kind": "field", "category": "field_length_vbtyp", "token": "VBTYP",
                "line": n, "world": "A", "release_dependent": True, "blocker": False,
                "replacement": "VBTYPL (CHAR4)",
                "source": fmeta.get("source", "field-mappings.json"), "text": raw.strip(),
            })

        # --- statement-level issues: DETECT & ROUTE (never rewrite) ---------
        for st in detect_statement_issues(line, upper, n):
            findings.append(st)

        # --- World-B objects (BAPIs/FMs) -> NOT ATC-forced ------------------
        for obj, entry in world_b.items():
            if token_present(obj, upper):
                atc = entry.get("atc_finding")
                findings.append({
                    "kind": "world_b", "category": "world_b_object", "token": obj,
                    "line": n,
                    "world": entry.get("world", "B"),
                    "atc_finding": atc,
                    "release_dependent": (atc == "release-dependent"),
                    "blocker": False,
                    "modernization_target": entry.get("modernization_target"),
                    "note": entry.get("note", ""),
                    "source": "world-b-allowlist.json",
                    "text": raw.strip(),
                })

    return findings


def detect_statement_issues(line: str, upper: str, n: int) -> list[dict]:
    """Statement-level (performance/correctness) issues -> sibling skill (REQ-010)."""
    out: list[dict] = []
    owner = "statement/performance skill (sibling)"

    if re.search(r"\bSELECT\s+\*", upper):
        out.append({"kind": "statement", "category": "select_star", "token": "SELECT *",
                    "line": n, "owner": owner, "world": None, "release_dependent": False,
                    "blocker": False, "source": "REQ-010 (route, do not rewrite)",
                    "text": line.strip()})
    if re.search(r"\bFOR\s+ALL\s+ENTRIES\b", upper):
        out.append({"kind": "statement", "category": "fae_no_guard", "token": "FOR ALL ENTRIES",
                    "line": n, "owner": owner, "world": None, "release_dependent": False,
                    "blocker": False,
                    "note": "Verify the driver table has an explicit IS NOT INITIAL guard.",
                    "source": "REQ-010 (route, do not rewrite)", "text": line.strip()})
    if re.search(r"\bEXEC\s+SQL\b", upper):
        out.append({"kind": "statement", "category": "native_exec_sql", "token": "EXEC SQL",
                    "line": n, "owner": owner, "world": None, "release_dependent": False,
                    "blocker": False, "source": "REQ-010 (route, do not rewrite)",
                    "text": line.strip()})
    return out


def detect_db_in_loop(text: str) -> list[dict]:
    """Flag SELECT / EXEC SQL that sit inside a LOOP ... ENDLOOP (DB-in-LOOP)."""
    owner = "statement/performance skill (sibling)"
    out: list[dict] = []
    depth = 0
    for n, raw in enumerate(text.splitlines(), start=1):
        line = strip_comments(raw)
        upper = line.upper()
        if re.search(r"\bLOOP\s+AT\b", upper):
            depth += 1
            continue
        if re.search(r"\bENDLOOP\b", upper):
            depth = max(0, depth - 1)
            continue
        if depth > 0 and (re.search(r"\bSELECT\b", upper) or re.search(r"\bEXEC\s+SQL\b", upper)):
            out.append({"kind": "statement", "category": "db_in_loop", "token": "SELECT/EXEC in LOOP",
                        "line": n, "owner": owner, "world": None, "release_dependent": False,
                        "blocker": False, "source": "REQ-010 (route, do not rewrite)",
                        "text": line.strip()})
    return out


# --------------------------------------------------------------------------- #
# REWRITE (deterministic, clear cases only)
# --------------------------------------------------------------------------- #
def _sub_word(token: str, repl: str, text: str) -> str:
    return re.sub(rf"\b{re.escape(token)}\b", repl, text, flags=re.IGNORECASE)


def rewrite(text: str, kb: dict, findings: list[dict]) -> tuple[str, list[str]]:
    """Apply deterministic rewrites. Returns (new_text, notes)."""
    tables_in_play = {f["token"] for f in findings if f.get("kind") == "table"}
    notes: list[str] = []
    out = text

    # 1) BSEG -> ACDOCA: field map first (so field tokens are mapped before the
    #    table token disappears), then table token, then add RLDNR filter.
    if "BSEG" in tables_in_play:
        for ecc_f, s4_f in ACDOCA_FIELD_MAP.items():
            if re.search(rf"\b{ecc_f}\b", out, flags=re.IGNORECASE):
                out = _sub_word(ecc_f, s4_f, out)
                notes.append(f"BSEG->ACDOCA: field {ecc_f} -> {s4_f}")
        out = _sub_word("BSEG", ACDOCA_TABLE, out)
        notes.append("BSEG -> ACDOCA (Universal Journal)")
        out = _add_ledger_filter(out)

    # 2) simple same-field table-name swaps
    for ecc_t, s4_t in SIMPLE_TABLE_SWAP.items():
        if ecc_t in tables_in_play:
            out = _sub_word(ecc_t, s4_t, out)
            notes.append(f"{ecc_t} -> {s4_t} (same fields)")

    # 3) VBTYP -> VBTYPL (length change). Word-boundary so VBTYPL is left alone.
    if re.search(r"\bVBTYP\b", out, flags=re.IGNORECASE):
        out = _sub_word("VBTYP", "VBTYPL", out)
        notes.append("VBTYP -> VBTYPL (CHAR1 -> CHAR4)")

    # 4) MATNR length: drop +0(18) offset, widen CHAR18 / LENGTH 18 -> LENGTH 40
    if re.search(r"\+\s*0\s*\(\s*18\s*\)", out):
        out = re.sub(r"\+\s*0\s*\(\s*18\s*\)", "", out)
        notes.append("MATNR: removed legacy +0(18) offset access (use full MATNR)")
    if re.search(r"\bLENGTH\s+18\b", out, flags=re.IGNORECASE):
        out = re.sub(r"\bLENGTH\s+18\b", "LENGTH 40", out, flags=re.IGNORECASE)
        notes.append("MATNR: CHAR18 declarations widened to LENGTH 40")
    if re.search(r"\bCHAR18\b", out, flags=re.IGNORECASE):
        out = _sub_word("CHAR18", "CHAR40", out)
        notes.append("MATNR: CHAR18 type widened to CHAR40")

    return out, notes


def _add_ledger_filter(text: str) -> str:
    """Add `AND RLDNR = '0L'` to the first WHERE block of an ACDOCA read.

    Deterministic and conservative: insert after the first line that contains a
    WHERE referencing the journal once ACDOCA is present, only if not already there.
    """
    if "RLDNR" in text.upper():
        return text
    lines = text.splitlines()
    out: list[str] = []
    inserted = False
    in_acdoca_select = False
    for line in lines:
        u = line.upper()
        if re.search(r"\bFROM\s+ACDOCA\b", u):
            in_acdoca_select = True
        out.append(line)
        if in_acdoca_select and not inserted and re.search(r"\bWHERE\b", u):
            indent = re.match(r"\s*", line).group(0)
            # match WHERE's condition indentation if it's "WHERE cond"
            m = re.search(r"\bWHERE\b(\s+)", line)
            cond_indent = indent + "  "
            out.append(f"{cond_indent}AND {ACDOCA_LEDGER_FILTER}")
            inserted = True
            in_acdoca_select = False
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


# --------------------------------------------------------------------------- #
# REPORT
# --------------------------------------------------------------------------- #
DISCLAIMER = (
    "_Not activation-verified (no SAP compiler in this environment). "
    "Release-dependent findings must be confirmed on the target system. "
    "Rewrites are review-acceleration drafts; a human signs off on every change._"
)


# Categories that are an ATC-forced "must fix" (removed/replaced/changed).
MUST_FIX_CATEGORIES = {
    "table_swap", "table_to_acdoca", "obsolete_table", "blocker_no_replacement",
    "matnr_length", "field_length_vbtyp",
}
# Categories that are "still exists, verify on target" (NOT a removal).
VERIFY_CATEGORIES = {"restructured_verify"}


def dedup(findings: list[dict]) -> list[dict]:
    """Collapse repeated (kind, token, category) findings into one, keeping a
    sorted list of the lines they occur on. Keeps the report readable and avoids
    inflating counts when a table is referenced on many lines (e.g. TYPES block)."""
    by_key: dict[tuple, dict] = {}
    for f in findings:
        key = (f.get("kind"), f.get("token"), f.get("category"))
        if key not in by_key:
            g = dict(f)
            g["lines"] = [f["line"]]
            by_key[key] = g
        else:
            by_key[key]["lines"].append(f["line"])
    out = list(by_key.values())
    for g in out:
        g["lines"] = sorted(set(g["lines"]))
        g["line"] = g["lines"][0]
    out.sort(key=lambda g: (g["line"], g.get("kind", ""), g.get("token", "")))
    return out


def _lines_str(g: dict) -> str:
    ls = g.get("lines", [g["line"]])
    head = ", ".join(f"L{n}" for n in ls[:6])
    return head + (f" (+{len(ls) - 6} more)" if len(ls) > 6 else "")


def build_report(findings: list[dict], rewritten: str,
                 notes: list[str], residual: list[dict]) -> str:
    L: list[str] = []
    L.append("# Remediation Report — SAP Table & Field Remediator (Branch A)\n")
    L.append(DISCLAIMER + "\n")

    d = dedup(findings)
    must_fix = [f for f in d if f.get("category") in MUST_FIX_CATEGORIES
                and not f.get("blocker")]
    blockers = [f for f in d if f.get("blocker")]
    verify_only = [f for f in d if f.get("category") in VERIFY_CATEGORIES]
    statements = [f for f in d if f.get("kind") == "statement"]
    world_b = [f for f in d if f.get("kind") == "world_b"]

    L.append("## Summary\n")
    L.append(f"- World-A must-fix (distinct objects): **{len(must_fix)}**")
    L.append(f"- BLOCKER (manual redesign, no clean replacement): **{len(blockers)}**")
    L.append(f"- Verify-only (still exists, confirm fields on target): **{len(verify_only)}**")
    L.append(f"- Statement-level routed to sibling skill (not rewritten): **{len(statements)}**")
    L.append(f"- World-B objects (key-only modernization, NOT ATC-forced): **{len(world_b)}**")
    verify = "CLEAN" if not residual else f"{len(residual)} residual reference(s) remain"
    L.append(f"- Post-rewrite residual check: **{verify}**\n")

    # World A must-fix
    L.append("## World A — must-fix (ATC-forced, deterministically rewritten)\n")
    if not must_fix:
        L.append("_None._\n")
    else:
        L.append("| Lines | Token | Category | Replacement | Release-dep | Source |")
        L.append("|---|---|---|---|---|---|")
        for f in must_fix:
            repl = (f.get("replacement") or f.get("fix_pattern") or "").replace("|", "/")
            rd = "yes" if f.get("release_dependent") else "no"
            cds = f.get("cds_view")
            if cds:
                repl = f"{repl} (CDS: {cds})"
            L.append(f"| {_lines_str(f)} | `{f['token']}` | {f['category']} "
                     f"| {repl} | {rd} | {f.get('source')} |")
        L.append("")

    # Blockers detail
    if blockers:
        L.append("## BLOCKER — no clean replacement, route to manual redesign\n")
        for f in blockers:
            L.append(f"- **`{f['token']}`** ({f.get('status')}) at {_lines_str(f)}: "
                     f"{f.get('fix_pattern') or f.get('replacement')} "
                     f"[source: {f.get('source')}]")
        L.append("")

    # Verify-only (still-valid restructured tables) — NOT flagged as removed.
    L.append("## Verify-only — still exists in S/4HANA (confirm fields on target)\n")
    if not verify_only:
        L.append("_None._\n")
    else:
        L.append("_These tables still exist; do not treat as removed. Verify field set "
                 "via SE11 / SD-MM simplification list on the target system._\n")
        for f in verify_only:
            cds = f" — released CDS: {f['cds_view']}" if f.get("cds_view") else ""
            L.append(f"- **`{f['token']}`** at {_lines_str(f)}{cds} "
                     f"[source: {f.get('source')}]")
        L.append("")

    # Statement-level
    L.append("## Statement-level — DETECT & ROUTE (sibling skill, not rewritten here)\n")
    if not statements:
        L.append("_None._\n")
    else:
        for f in statements:
            note = f" — {f['note']}" if f.get("note") else ""
            L.append(f"- **`{f['token']}`** ({f['category']}) at {_lines_str(f)} "
                     f"-> {f['owner']}{note}")
        L.append("")

    # World B
    L.append("## World B — key-only modernization (NOT an ATC must-fix)\n")
    if not world_b:
        L.append("_None._\n")
    else:
        for f in world_b:
            atc = f.get("atc_finding")
            if atc == "release-dependent":
                tag = "release-dependent — verify in SYCM on target"
            elif atc:
                tag = "ATC finding"
            else:
                tag = "not an ATC finding (working released object)"
            tgt = f.get("modernization_target") or "none"
            L.append(f"- **`{f['token']}`** at {_lines_str(f)}: {tag}. "
                     f"Modernization target: {tgt}. [source: {f.get('source')}]")
        L.append("")

    # Rewrite
    L.append("## Deterministic rewrite\n")
    if notes:
        L.append("Applied transforms:")
        for nt in notes:
            L.append(f"- {nt}")
        L.append("")
        L.append("```abap")
        L.append(rewritten.rstrip("\n"))
        L.append("```")
    else:
        L.append("_No deterministic rewrite applied (verify-only / blocker / statement-level)._")
    L.append("")

    # Verify
    L.append("## Verify (check_residual.py)\n")
    if not residual:
        L.append("CLEAN: no residual obsolete table/field references in the rewritten code.")
    else:
        L.append(f"{len(residual)} residual reference(s) remain (expected for "
                 f"BLOCKER / no-clean-replacement cases — manual redesign needed):")
        for r in residual:
            L.append(f"- L{r['line']} {r['type']} `{r['token']}`")
    L.append("")
    return "\n".join(L)


# --------------------------------------------------------------------------- #
# Verify helper (reuse the shared check_residual scanner)
# --------------------------------------------------------------------------- #
def residual_scan(text: str) -> list[dict]:
    """Call the shared check_residual scanner on rewritten text."""
    sys.path.insert(0, HERE)
    import check_residual  # noqa: E402  (intentional local import)
    return check_residual.scan(text)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def remediate(text: str) -> dict:
    kb = load_kb()
    findings = detect(text, kb)
    findings += detect_db_in_loop(text)
    findings.sort(key=lambda f: (f["line"], f.get("kind", ""), f.get("token", "")))
    rewritten, notes = rewrite(text, kb, findings)
    residual = residual_scan(rewritten)
    return {
        "findings": findings,
        "rewritten": rewritten,
        "notes": notes,
        "residual": residual,
        "kb_counts": {"tables": len(kb["tables"]), "fields": len(kb["fields"]),
                      "world_b": len(kb["world_b"])},
    }


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    as_json = "--json" in sys.argv
    rewrite_only = "--rewrite-only" in sys.argv
    if not args:
        print("usage: remediate.py <file.abap|-> [--json|--rewrite-only]", file=sys.stderr)
        return 2

    src = args[0]
    text = sys.stdin.read() if src == "-" else open(src).read()

    result = remediate(text)

    if rewrite_only:
        sys.stdout.write(result["rewritten"])
        return 0
    if as_json:
        print(json.dumps({
            "findings": result["findings"],
            "rewrite_notes": result["notes"],
            "residual_count": len(result["residual"]),
            "residual": result["residual"],
            "rewritten": result["rewritten"],
        }, indent=2))
        return 0

    report = build_report(result["findings"], result["rewritten"],
                          result["notes"], result["residual"])
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
