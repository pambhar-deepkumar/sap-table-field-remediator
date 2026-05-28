#!/usr/bin/env python3
"""Build the Skill 3 knowledge base from Deloitte's curated Excel attachments.

Faithfully parses "Skill3 Attachment 1 & 2.xlsx" (no third-party deps -- stdlib
zipfile + xml only, since the machine's Homebrew Python is externally managed and
openpyxl is not installed) and merges:

  1. raw rows from the xlsx  (source="deloitte-attachment-1/2")
  2. a small research-sourced SUPPLEMENT for tables/fields that appear in the
     realistic Input Program (ZR_SD_OPEN_ORDER_MARGIN_COCKPIT) but are NOT in
     Deloitte's curated 15-table list -- VBUK, VBUP, VAPMA, KNKK, VBTYP length.
     These are flagged source="research-supplement" so provenance is explicit.
  3. ENRICHMENT (world A/B, release-dependence, released CDS view, fix pattern).

Outputs (pretty, sorted JSON) into ../references/:
  - table-mappings.json
  - field-mappings.json

Re-runnable and deterministic: rerun after editing the xlsx, SUPPLEMENT, or
ENRICH dicts. CDS view names marked (research) are confirmed/refined by the
research pass (working-notes/research/EVIDENCE-POOL.md).

Usage:
  python3 load_mappings.py [path-to-xlsx]
"""
from __future__ import annotations

import json
import os
import re
import sys
import zipfile
from xml.etree import ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
REF_DIR = os.path.normpath(os.path.join(HERE, "..", "references"))
DEFAULT_XLSX = os.path.normpath(os.path.join(
    HERE, "..", "..", "..", "..",
    "deloitte_resources_and_materials", "additional-skill-3-docs",
    "Skill3 Attachment 1 & 2.xlsx",
))

NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
}


# --------------------------------------------------------------------------- #
# Minimal stdlib XLSX reader
# --------------------------------------------------------------------------- #
def _col_to_idx(cell_ref: str) -> int:
    """'B7' -> 1 (zero-based column index)."""
    letters = re.match(r"[A-Z]+", cell_ref).group(0)
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx - 1


def read_xlsx(path: str) -> dict[str, list[list[str]]]:
    """Return {sheet_name: rows}, each row a list of cell strings (gaps -> '')."""
    with zipfile.ZipFile(path) as z:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            sst = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in sst.findall("m:si", NS):
                # concatenate all text nodes (handles rich-text runs)
                shared.append("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))

        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        rid_to_target = {
            rel.get("Id"): rel.get("Target")
            for rel in rels.findall("pr:Relationship", NS)
        }
        sheets: list[tuple[str, str]] = []
        for sh in wb.find("m:sheets", NS).findall("m:sheet", NS):
            name = sh.get("name")
            rid = sh.get(f"{{{NS['r']}}}id")
            target = rid_to_target.get(rid, "")
            if not target.startswith("xl/"):
                target = "xl/" + target.lstrip("/")
            sheets.append((name, target))

        result: dict[str, list[list[str]]] = {}
        for name, target in sheets:
            ws = ET.fromstring(z.read(target))
            rows_out: list[list[str]] = []
            for row in ws.iter(f"{{{NS['m']}}}row"):
                cells: list[str] = []
                for c in row.findall("m:c", NS):
                    idx = _col_to_idx(c.get("r"))
                    while len(cells) < idx:
                        cells.append("")
                    ctype = c.get("t")
                    v = c.find("m:v", NS)
                    if ctype == "s":  # shared string
                        text = shared[int(v.text)] if v is not None else ""
                    elif ctype == "inlineStr":
                        is_el = c.find("m:is", NS)
                        text = "".join(t.text or "" for t in is_el.iter(f"{{{NS['m']}}}t")) if is_el is not None else ""
                    else:
                        text = v.text if v is not None else ""
                    cells.append((text or "").strip())
                rows_out.append(cells)
            result[name] = rows_out
        return result


def rows_to_records(rows: list[list[str]]) -> list[dict[str, str]]:
    """First non-empty row = headers; subsequent non-empty rows = records."""
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        return []
    headers = [h.strip() for h in rows[0]]
    out = []
    for r in rows[1:]:
        rec = {}
        for i, h in enumerate(headers):
            if h:
                rec[h] = r[i].strip() if i < len(r) else ""
        out.append(rec)
    return out


# --------------------------------------------------------------------------- #
# Research-sourced supplement (NOT in Deloitte's curated xlsx, but referenced by
# the Input Program). CDS names confirmed by the research pass.
# --------------------------------------------------------------------------- #
SUPPLEMENT_TABLES = [
    {"ECC Table Name": "VBUK", "ECC Purpose": "Sales document header status",
     "Status in S/4HANA": "ABOLISHED",
     "S/4HANA Replacement": "Status fields folded into VBAK (use I_SalesOrder)",
     "Functional Area": "Sales (SD)"},
    {"ECC Table Name": "VBUP", "ECC Purpose": "Sales document item status",
     "Status in S/4HANA": "ABOLISHED",
     "S/4HANA Replacement": "Status fields folded into VBAP (use I_SalesOrderItem)",
     "Functional Area": "Sales (SD)"},
    {"ECC Table Name": "VAPMA", "ECC Purpose": "Sales index by material (SD index table)",
     "Status in S/4HANA": "ABOLISHED",
     "S/4HANA Replacement": "Eliminated index table; read VBAP / use released CDS",
     "Functional Area": "Sales (SD)"},
    {"ECC Table Name": "KNKK", "ECC Purpose": "Customer master credit control area data (classic credit mgmt)",
     "Status in S/4HANA": "ABOLISHED",
     "S/4HANA Replacement": "SAP Credit Management (FSCM/UKM): UKMBP / UKM_ITEM",
     "Functional Area": "Finance / Credit (FIN-FSCM-CR)"},
]

SUPPLEMENT_FIELDS = [
    {"ECC Table": "VBAK", "ECC Field Name": "VBTYP", "ECC Field Purpose": "SD document category",
     "Change Type": "LENGTH_CHANGE", "S/4HANA Table": "VBAK", "S/4HANA Field Name": "VBTYPL",
     "Notes / Action Required": "Field-length change CHAR1 VBTYP -> CHAR4 VBTYPL; verify on target release"},
    {"ECC Table": "VBUK", "ECC Field Name": "GBSTK", "ECC Field Purpose": "Overall processing status (header)",
     "Change Type": "MOVED", "S/4HANA Table": "VBAK", "S/4HANA Field Name": "GBSTK",
     "Notes / Action Required": "VBUK abolished; status now on VBAK / I_SalesOrder"},
    {"ECC Table": "VBUP", "ECC Field Name": "GBSTA", "ECC Field Purpose": "Overall processing status (item)",
     "Change Type": "MOVED", "S/4HANA Table": "VBAP", "S/4HANA Field Name": "GBSTA",
     "Notes / Action Required": "VBUP abolished; status now on VBAP / I_SalesOrderItem"},
]

# Per-table enrichment. cds_view marked (research) where confirmed by the
# research pass; null = no clean released CDS read API -> manual review.
ENRICH_TABLE = {
    "BSEG":  {"cds_view": "I_JournalEntryItem", "release_dependent": False,
              "fix_pattern": "Read via ACDOCA / I_JournalEntryItem; RBUKRS, RACCT, BUZEI->DOCLN, add RLDNR='0L'."},
    "RFBLG": {"cds_view": "I_JournalEntryItem", "release_dependent": False,
              "fix_pattern": "Physical FI cluster container for BSEG; data now in ACDOCA Universal Journal."},
    "KONV":  {"cds_view": None, "release_dependent": False,
              "fix_pattern": "Replace table KONV -> PRCD_ELEMENTS (transparent, same fields)."},
    "CDPOS": {"cds_view": None, "release_dependent": True,
              "fix_pattern": "Cluster abolished; read CDPOS_STR / CDPOS_UID. Verify on target release."},
    "CDHDR": {"cds_view": None, "release_dependent": True,
              "fix_pattern": "Restructured; verify field set via SE11 on target."},
    "MSEG":  {"cds_view": "I_MaterialDocumentItem", "release_dependent": False,
              "fix_pattern": "Still readable; new data model MATDOC; prefer released CDS."},
    "MKPF":  {"cds_view": "I_MaterialDocumentHeader", "release_dependent": False,
              "fix_pattern": "Still readable; header data in MATDOC; prefer released CDS."},
    "VBAK":  {"cds_view": "I_SalesOrder", "release_dependent": False,
              "fix_pattern": "Still exists; status fields from former VBUK folded in."},
    "VBAP":  {"cds_view": "I_SalesOrderItem", "release_dependent": False,
              "fix_pattern": "Still exists; status fields from former VBUP folded in."},
    "VBUK":  {"cds_view": "I_SalesOrder", "release_dependent": False,
              "fix_pattern": "Header status now on VBAK; read I_SalesOrder."},
    "VBUP":  {"cds_view": "I_SalesOrderItem", "release_dependent": False,
              "fix_pattern": "Item status now on VBAP; read I_SalesOrderItem."},
    "VAPMA": {"cds_view": None, "release_dependent": True,
              "fix_pattern": "Index table eliminated; read VBAP / released CDS; verify."},
    "KNKK":  {"cds_view": None, "release_dependent": True,
              "fix_pattern": "Classic credit removed; use FSCM Credit Mgmt (UKM). Redesign; verify."},
    "S001":  {"cds_view": None, "release_dependent": False,
              "fix_pattern": "LIS abolished; use Embedded Analytics / CDS (Note 2267463)."},
    "S061":  {"cds_view": None, "release_dependent": False,
              "fix_pattern": "LIS abolished; use Embedded Analytics / CDS (Note 2267463)."},
    "PCL1":  {"cds_view": None, "release_dependent": True, "fix_pattern": "HR cluster -> transparent per infotype (Note 2409530)."},
    "PCL2":  {"cds_view": None, "release_dependent": True, "fix_pattern": "HR cluster -> transparent per infotype (Note 2409530)."},
    "PCL3":  {"cds_view": None, "release_dependent": True, "fix_pattern": "HR cluster -> transparent per infotype (Note 2409530)."},
    "PCL4":  {"cds_view": None, "release_dependent": True, "fix_pattern": "HR cluster -> transparent per infotype (Note 2409530)."},
}


def norm_table(rec: dict, source: str) -> dict:
    name = rec.get("ECC Table Name", "").strip().upper()
    enr = ENRICH_TABLE.get(name, {})
    return {
        "ecc_table": name,
        "ecc_purpose": rec.get("ECC Purpose", "").strip(),
        "status": rec.get("Status in S/4HANA", "").strip(),
        "s4_replacement": rec.get("S/4HANA Replacement", "").replace("\n", " ").strip(),
        "functional_area": rec.get("Functional Area", "").strip(),
        "cds_view": enr.get("cds_view"),
        "world": "A",  # removed/replaced tables are ATC-forced (World A)
        "release_dependent": enr.get("release_dependent", False),
        "fix_pattern": enr.get("fix_pattern", ""),
        "source": source,
    }


def norm_field(rec: dict, source: str) -> dict:
    return {
        "ecc_table": rec.get("ECC Table", "").strip().upper(),
        "ecc_field": rec.get("ECC Field Name", "").strip().upper(),
        "ecc_purpose": rec.get("ECC Field Purpose", "").strip(),
        "change_type": rec.get("Change Type", "").strip().upper(),
        "s4_table": rec.get("S/4HANA Table", "").strip().upper(),
        "s4_field": rec.get("S/4HANA Field Name", "").strip().upper(),
        "notes": rec.get("Notes / Action Required", "").replace("\n", " ").strip(),
        "world": "A",
        "release_dependent": "MATNR" in rec.get("ECC Field Name", "").upper()
                             or "LENGTH" in rec.get("Change Type", "").upper(),
        "source": source,
    }


def main() -> int:
    xlsx = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_XLSX
    if not os.path.exists(xlsx):
        print(f"ERROR: xlsx not found: {xlsx}", file=sys.stderr)
        return 1

    sheets = read_xlsx(xlsx)
    sheet_names = list(sheets)
    # Identify the two sheets robustly by header content.
    table_sheet = next((n for n in sheet_names if "table" in n.lower()), sheet_names[0])
    field_sheet = next((n for n in sheet_names if "field" in n.lower()), sheet_names[-1])

    table_recs = [norm_table(r, "deloitte-attachment-1") for r in rows_to_records(sheets[table_sheet])]
    field_recs = [norm_field(r, "deloitte-attachment-2") for r in rows_to_records(sheets[field_sheet])]

    table_recs += [norm_table(r, "research-supplement") for r in SUPPLEMENT_TABLES]
    field_recs += [norm_field(r, "research-supplement") for r in SUPPLEMENT_FIELDS]

    table_recs.sort(key=lambda r: r["ecc_table"])
    field_recs.sort(key=lambda r: (r["ecc_table"], r["ecc_field"]))

    os.makedirs(REF_DIR, exist_ok=True)
    tpath = os.path.join(REF_DIR, "table-mappings.json")
    fpath = os.path.join(REF_DIR, "field-mappings.json")
    with open(tpath, "w") as fh:
        json.dump(table_recs, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    with open(fpath, "w") as fh:
        json.dump(field_recs, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    n_deloitte_t = sum(1 for r in table_recs if r["source"] == "deloitte-attachment-1")
    n_deloitte_f = sum(1 for r in field_recs if r["source"] == "deloitte-attachment-2")
    print(f"sheets: {sheet_names}")
    print(f"tables: {len(table_recs)} total ({n_deloitte_t} deloitte + {len(table_recs)-n_deloitte_t} supplement)")
    print(f"fields: {len(field_recs)} total ({n_deloitte_f} deloitte + {len(field_recs)-n_deloitte_f} supplement)")
    print(f"wrote: {tpath}")
    print(f"wrote: {fpath}")

    assert n_deloitte_t == 15, f"expected 15 Deloitte tables, got {n_deloitte_t}"
    assert n_deloitte_f == 23, f"expected 23 Deloitte fields, got {n_deloitte_f}"
    print("OK: Deloitte counts match (15 tables / 23 fields)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
