# SPEC — SAP Table & Field Remediator (Skill 3)

Shared specification for **both** implementation branches (`feat/skill-A-deterministic`,
`feat/skill-B-agentic`). Requirements use EARS notation (course w02). Both skills are
generated from this spec; the evaluation scores against these requirements.

## 1. Overview

A Claude Code skill that detects, in custom ECC ABAP, references to **tables and
fields that change in an S/4HANA brownfield conversion**, and produces a
**remediation report** (and rewritten ABAP where deterministic) to accelerate a
human reviewer. It does not deploy; a human signs off on every change.

The skill operates on ABAP **text** (exported source or an ATC finding list) — no
running SAP system required. The offline correctness signal is a residual-reference
check + abaplint syntax parse; the real signal (SAP syntax check / ATC) is dropped
in when a sandbox is available.

## 2. Goals / Non-Goals

**Goals**
- Detect removed/replaced tables, field renames/relocations, MATNR length, and
  field-length changes (e.g. `VBTYP→VBTYPL`).
- Classify each finding **World A** (ATC-forced, must fix) vs **World B** (clean-core
  modernization, key-only) and flag **release-dependent** ones honestly.
- Recommend the released CDS view replacement where one exists (the gap ATC leaves).
- Emit a structured, source-citing remediation report.

**Non-Goals**
- No statement-level performance/correctness rewriting (SELECT *, FAE guards, DB-in-LOOP,
  native EXEC SQL) — **detect and route** to the sibling skill, do not fix.
- No World-B rewrite asserted as ATC-forced (a working released BAPI is not a finding).
- No authorization/permission logic; no live-system mutation; no auto-deploy.
- Not activation-verified (no compiler in our environment) — say so in output.

## 3. Architecture (per branch)

Shared: knowledge base (`references/*.json`), verifier harness
(`scripts/check_residual.py` + `validator/` abaplint wrapper + LLM-judge rubric).
- **Branch A (deterministic-first workflow):** Detect→Classify→Rewrite(rule-engine)→Verify→Report.
- **Branch B (agentic ReAct):** per-finding reason→lookup→classify→rewrite→verify→self-correct (call cap).

## 4. Requirements (EARS)

- **REQ-001 (Ubiquitous):** The skill SHALL flag every `SELECT`/`TABLES`/`TYPE … OF`
  reference to a table present in `references/table-mappings.json`.
- **REQ-002 (Ubiquitous):** For each flagged table, the skill SHALL state its S/4HANA
  replacement and, when `cds_view` is non-null, recommend that released CDS view.
- **REQ-003 (Event):** WHEN a flagged statement references a field present in
  `references/field-mappings.json`, the skill SHALL map it to its S/4HANA field
  (e.g. `HKONT→RACCT`, `BUZEI→DOCLN`, `BUKRS→RBUKRS`).
- **REQ-004 (Event):** WHEN rewriting FI reads to ACDOCA, the skill SHALL add the
  leading-ledger filter `RLDNR = '0L'` and map `MONAT→POPER`.
- **REQ-005 (State):** WHILE a finding's table `status` is `ABOLISHED` with no clean
  replacement (e.g. `S001`, `RFBLG`, `PCL*`), the skill SHALL mark it **BLOCKER** and
  route to manual redesign.
- **REQ-006 (Ubiquitous):** The skill SHALL tag every finding `world: A|B` and
  `release_dependent: true|false`.
- **REQ-007 (Unwanted):** The skill SHALL NOT report a working released BAPI/FM listed
  in `references/world-b-allowlist.json` as an ATC-forced finding; it MAY note a
  key-only modernization target.
- **REQ-008 (Unwanted):** The skill SHALL NOT flag a still-valid table (one not in
  `table-mappings.json`, e.g. `MARA`, `MAKT`, `LIKP`, `VBRK`) as removed/obsolete.
- **REQ-009 (Event):** WHEN MATNR is accessed via offset/CHAR18 (`matnr+0(18)`,
  `TYPE c LENGTH 18`), the skill SHALL flag a length-extension finding and mark it
  `release_dependent` (priority depends on extended material number being active).
- **REQ-010 (Event):** WHEN a statement-level issue (SELECT *, FAE without guard,
  DB-in-LOOP, native EXEC SQL) is present, the skill SHALL detect and route it to the
  sibling skill WITHOUT rewriting it.
- **REQ-011 (Ubiquitous):** Each finding SHALL cite the triggering table/field and its
  knowledge-base source (no uncited recommendations — w03 hallucination mitigation).
- **REQ-012 (Event):** WHEN a remediation is produced, `check_residual.py` SHALL report
  zero residual obsolete table/field references for the rewritten code.
- **REQ-013 (Ubiquitous):** Output SHALL state that code is not activation-verified and
  that release-dependent findings need confirmation on the target system.

## 5. Testing strategy

- **Tier 1 (labeled):** `deliverables/03-evaluation/ground-truth/snippets-gold.json` —
  12 snippets with answer keys. Score detection, replacement, field maps, blocker.
- **Tier 2 (realistic):** `input-program.abap` vs `input-program-expected.md` —
  World-A recall, **World-A/B precision (no over-flag)**, false-positive guard (D-list).
- **Computational sensors first** (`check_residual.py`, abaplint), **semantic** (LLM-judge
  rubric) only for remediation quality — course w04.
- Spec-as-oracle: every REQ-NNN maps to at least one eval check.

## 6. Milestones

- **Jun 8 (Mon):** prototype testable in Deloitte system (Input Program remediation ready).
- **Jun 10 (Wed):** mid-term — architecture debate + head-to-head eval (real numbers).
- **Phase 3:** winner → final skill; real ATC/sandbox integration; broaden catalog.
