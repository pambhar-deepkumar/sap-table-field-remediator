# Remediation rules — Branch A deterministic engine

Detailed reference for `scripts/remediate.py`. The `SKILL.md` body orients; this
file holds the full rule tables. Read only when you need the exact mapping or the
reason a finding was classified a given way.

## Classification (what each category means)

| Category | Meaning | Engine action |
|---|---|---|
| `table_swap` | Obsolete table, new table has the **same fields** | Rewrite: rename table token |
| `table_to_acdoca` | `BSEG` → `ACDOCA` (Universal Journal) | Rewrite: field map + `RLDNR='0L'` |
| `obsolete_table` | Removed, replacement exists but not a same-field swap | Report; no auto-rewrite |
| `blocker_no_replacement` | No clean replacement — manual redesign | Report **BLOCKER**; no rewrite |
| `restructured_verify` | Still exists in S/4HANA (RESTRUCTURED) | Verify-only; **not** a removal |
| `matnr_length` | MATNR 18→40 extension (offset / CHAR18 / LENGTH 18) | Rewrite: drop offset, widen to 40 |
| `field_length_vbtyp` | `VBTYP` CHAR1 → `VBTYPL` CHAR4 | Rewrite: rename field token |
| statement-level | SELECT *, FAE-no-guard, EXEC SQL, DB-in-LOOP | **Route** to sibling skill; never rewrite |
| `world_b_object` | Working released BAPI/FM | **Not** an ATC must-fix; note key-only target |

## Deterministic rewrites the engine applies

### Same-field table swaps
`KONV → PRCD_ELEMENTS`, `CDPOS → CDPOS_STR`, `VBUK → VBAK`, `VBUP → VBAP`.
Field names are unchanged, so only the table token is renamed.

### BSEG → ACDOCA (FI Universal Journal)
Field map applied before the table token is renamed:
`HKONT→RACCT`, `BUZEI→DOCLN`, `BUKRS→RBUKRS`, `MONAT→POPER`. Other BSEG fields keep
their names (`BELNR, GJAHR, DMBTR, WRBTR, KOSTL, ZUONR`). The engine then adds
`AND RLDNR = '0L'` (leading ledger) to the first `WHERE` of the ACDOCA read.

### MATNR length extension (18 → 40)
`+0(18)` offset access is removed (use the full field); `LENGTH 18` → `LENGTH 40`;
`CHAR18` → `CHAR40`. Marked **release-dependent** — only a real fix once the extended
material number is active on the target system.

### VBTYP → VBTYPL
Word-boundary rename. `VBTYPL` already contains `VBTYP`, so the boundary match avoids
double-rewriting. Release-dependent.

## BLOCKER tables (no clean replacement → manual redesign)
`S001`, `S061` (LIS abolished → Embedded Analytics, Note 2267463), `RFBLG` (FI cluster →
ACDOCA, full redesign), `PCL1–PCL4` (HR clusters → transparent per infotype, Note 2409530),
`KNKK` (classic credit → FSCM/UKM). The engine does **not** rewrite these; it emits a
BLOCKER finding. `check_residual.py` will therefore still report them — that is expected,
not a failure.

`VAPMA` (eliminated SD index) is `obsolete_table` (read `VBAP`/CDS), reported but not
auto-rewritten — it has a path but no same-field drop-in.

## False-positive guards (must NOT be flagged as removed)
Tables not in `table-mappings.json` (`MARA, MAKT, LIKP, VBRK`, …) are never touched.
`VBAK`/`VBAP` are RESTRUCTURED → `restructured_verify` (verify fields on target), never
"removed". World-B BAPIs in `world-b-allowlist.json` (`BAPI_SALESORDER_CHANGE`,
`BAPI_TRANSACTION_COMMIT`, …) are never reported as ATC-forced.

## Verification contract (against `scripts/check_residual.py`)
`check_residual` flags obsolete tables (status ABOLISHED / COMPATIBILITY VIEW), MATNR
offset/CHAR18/LENGTH 18, and bare `VBTYP`. After the engine's rewrite, every
**deterministically-fixed** case is CLEAN. BLOCKER cases intentionally remain flagged.

## Requirement traceability (SPEC.md EARS)
REQ-001/002 → table detection + CDS recommendation. REQ-003/004 → ACDOCA field map +
`RLDNR='0L'`/`MONAT→POPER`. REQ-005 → BLOCKER tables. REQ-006 → `world` + `release_dependent`
on every finding. REQ-007 → World-B allowlist not ATC-forced. REQ-008 → still-valid tables
not flagged. REQ-009 → MATNR length. REQ-010 → statement-level detect-and-route, no rewrite.
REQ-011 → every finding cites token + KB source. REQ-012 → check_residual CLEAN for fixed
cases. REQ-013 → "not activation-verified" + release-dependent hedging in the report.
