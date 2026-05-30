---
name: sap-table-field-remediator
description: Remediates custom SAP ECC ABAP for an S/4HANA Brownfield conversion. Detects obsolete/changed tables and fields (e.g. BSEG, KONV, CDPOS, VBUK/VBUP, MATNR length, VBTYP), classifies each as World A (ATC must-fix) vs World B (key-only modernization), deterministically rewrites the clear cases, and emits a source-cited remediation report a human reviews. Use when you have legacy ABAP (exported source or an ATC finding list) and need to know what breaks after S/4HANA and what to use instead. Trigger phrases - "remediate this ABAP for S/4HANA", "is this SELECT obsolete in S/4", "S/4HANA table/field migration", "ECC to S/4HANA custom code", "check this report for simplification items".
---

# SAP Table & Field Remediator (Branch A — deterministic-first)

Accelerates a human reviewer doing ECC→S/4HANA custom-code remediation. It is a
**fixed, deterministic pipeline** keyed off a curated knowledge base — no per-finding
model reasoning. Same input gives the same output, so a reviewer can trust and
diff it. This is the "simplest workflow that works first" arm of the project
(course w03); the engine is itself a computational sensor (course w04).

**This skill does not deploy and is not activation-verified** (no SAP compiler in
this environment). It produces draft rewrites + a report. A human signs off on
every change. Release-dependent findings must be confirmed on the target system.

## When to use

- You have custom ECC ABAP (a program, include, or snippet) and want the S/4HANA
  readiness findings plus deterministic rewrites for the clear cases.
- You want World-A (ATC must-fix) cleanly separated from World-B (clean-core,
  key-only) so you don't waste review time on working released BAPIs.

## When NOT to use

- Statement-level performance/correctness fixes (SELECT *, FAE guards, DB-in-LOOP,
  native EXEC SQL). This skill **detects and routes** those to the sibling
  statement/performance skill; it never rewrites them.
- Anything requiring a live system: authorization logic, deployment, ATC execution.

## Workflow (fixed: Detect → Classify → Rewrite → Verify → Report)

Run the engine, then the verifier. Do not improvise steps — the value of Branch A
is that the steps are fixed.

### 1. Run the remediation engine

```
python3 scripts/remediate.py <file.abap>            # markdown report (default)
python3 scripts/remediate.py - < snippet.abap       # read from stdin
python3 scripts/remediate.py <file.abap> --json     # machine-readable findings
python3 scripts/remediate.py <file.abap> --rewrite-only   # only the rewritten ABAP
```

The engine performs Detect → Classify → Rewrite internally:

- **Detect** every table/field in `references/table-mappings.json` and
  `references/field-mappings.json`, plus MATNR length access, `VBTYP`, statement-level
  issues, and World-B objects from `references/world-b-allowlist.json`.
- **Classify** each finding: `world: A|B`, `release_dependent: true|false`, and whether
  it is a BLOCKER. World-B working BAPIs are never reported as ATC-forced.
- **Rewrite** the clear cases deterministically:
  - table-name swap (same fields): `KONV→PRCD_ELEMENTS`, `CDPOS→CDPOS_STR`,
    `VBUK→VBAK`, `VBUP→VBAP`
  - `BSEG→ACDOCA` with field map `HKONT→RACCT`, `BUZEI→DOCLN`, `BUKRS→RBUKRS`,
    `MONAT→POPER`, and add `RLDNR = '0L'`
  - `VBTYP→VBTYPL`; MATNR offset/CHAR18/LENGTH 18 → full 40-char access
  - BLOCKER tables (`S001`, `RFBLG`, `PCL*`, `KNKK`) are **not** rewritten — manual redesign
  - statement-level issues are **detected and routed**, never rewritten

Full rule tables and requirement traceability: `references/remediation-rules.md`.

### 2. Verify the rewrite (computational sensor)

Pipe the rewritten ABAP through the shared residual checker:

```
python3 scripts/remediate.py <file.abap> --rewrite-only | python3 scripts/check_residual.py -
```

- **Expected for deterministically-fixed cases:** `CLEAN`.
- **Expected for BLOCKER cases:** residual references remain — that is correct, the
  table has no clean replacement and routes to manual redesign. Do not "fix" this by
  inventing a replacement (that is the AI-slop failure mode the rubric penalizes).

If a sandbox is available, additionally run `validator/lint_snippet.py` (abaplint
syntax parse) and, when an SAP system is reachable, the real ATC / syntax check.
abaplint degrades gracefully offline (exit 2) — fall back to `check_residual` only.

### 3. Report and hand off

The default markdown report is the reviewer's worklist. It separates:

- **World A — must-fix** (deterministically rewritten, with replacement + CDS view)
- **BLOCKER** — no clean replacement, manual redesign
- **Verify-only** — still exists (e.g. `VBAK`, `VBAP`), confirm fields on target
- **Statement-level** — routed to the sibling skill, not rewritten
- **World B** — key-only modernization, NOT an ATC must-fix

Every finding cites its triggering table/field and KB source (no uncited
recommendations — w03 hallucination mitigation). Present the rewritten ABAP as a
**draft diff** for human sign-off; never auto-apply.

## Inputs and outputs

- **Input:** ABAP text — a file path or stdin. Exported source or an ATC finding list.
- **Output:** a markdown remediation report (default), or `--json` for tooling, or
  `--rewrite-only` for the rewritten ABAP. None of it is activation-verified.

## Error handling

- **No findings:** the report says so; the code is already S/4-ready for our scope
  (still confirm on target if it touches RESTRUCTURED tables).
- **Residual after rewrite on a non-blocker:** treat as a bug — check that the table
  is in `references/table-mappings.json` and the rewrite rule covers it. Do not
  hand-edit the rewritten output to hide it.
- **abaplint unavailable (offline):** expected; rely on `check_residual` and note in
  the hand-off that syntax was not parse-verified.
- **A table/field not in the KB:** the engine will not flag it. If you believe it is a
  real simplification item, add it via `scripts/load_mappings.py` (re-derives the KB
  from Deloitte's attachments + supplement) — do not hardcode it in the report.

## Knowledge base

- `references/table-mappings.json` — ECC→S/4 table catalog (status, replacement, CDS view).
- `references/field-mappings.json` — field renames/relocations/length changes.
- `references/world-b-allowlist.json` — working released BAPIs/FMs that must NOT be
  reported as ATC-forced.
- `references/remediation-rules.md` — full rule tables + EARS requirement traceability.
