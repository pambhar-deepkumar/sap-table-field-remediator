# Skill Build Brief — Tier-Aware Table & Field Remediator

**For:** a fresh Claude session that will build the skill. **Date:** 2026-06-23 (rev. after design review).
**Read this first. It is self-contained — you do NOT need the long design conversation that preceded it.**

---

## ⛔ THE ONE HARD RULE (blind build — eval integrity depends on it)

**NEVER open `../synthetic-sap-codebase/ground-truth/findings.yaml`.** That is the SECRET answer key.
If this session reads it, every precision/recall number the eval produces becomes meaningless. Build from
the public catalog + general SAP knowledge ONLY. Do not infer or grep for it.

You MAY read:
- `../synthetic-sap-codebase/src/**` — the ABAP code under test.
- `../synthetic-sap-codebase/ground-truth/simplification-list.yaml` — the PUBLIC catalog. **This is the
  KB the skill uses** (it's what the harness copies into the sandbox). See "KB" below.
- `../synthetic-sap-codebase/eval/report-contract.schema.json` + `docs/02-eval-harness-plan.md` — the
  output contract + metrics + scoring rules.
- This repo's existing work.

## Mission
A Claude Code skill that, given custom ECC ABAP, detects references to tables/fields that change in an
S/4HANA brownfield conversion, classifies each, and emits a **machine-readable `remediation-report.json`**
(the contract) routing each finding by *how much human judgment its fix needs*.

## Knowledge base — single source of truth (IMPORTANT — review fix #1)
**The catalog is `simplification-list.yaml`** (key: `object`; statuses include `RESTRUCTURED`,
`ABOLISHED`, `DECLUSTERED_SAME_NAME`, `REDIRECT_BP`, plus `baseline_tier`, `world` ∈ A/A-verify/B).
The old `skills/.../references/*.json` (key: `ecc_table`; status `"COMPATIBILITY VIEW"`) and the old
`check_residual.py` (hard-wired to `r["ecc_table"]` and `MUST_REPLACE_STATUS={"ABOLISHED","COMPATIBILITY
VIEW"}`) are **STALE — a different schema and vocabulary.** If you point the old loader at the YAML it
KeyErrors and silently MISSES BSEG/MKPF/MSEG (their status is `RESTRUCTURED`).
→ **Rewrite the loader to the YAML schema; treat the YAML as truth.** You may keep the old scripts'
*shape* as a starting point, but port them. Bundle a YAML-derived copy inside the skill for production,
but the skill must read whatever catalog is present in its working dir at run time.

## The verdict to build on (already proven)
**Hybrid: deterministic core + agentic escalation.** Detection is deterministic; the LLM does *judgment*
(classify category/tier, propose fix, ask the intent question). Cheap deterministic path for the common
case; escalate only the uncertain residue.

## Detection — use abaplint's AST, not regex (review fix #2, #5)
Plain token/regex matching FAILS on the corpus's high-value cases and is the #1 risk. Concretely it must
handle, from real `src/` files: multi-line `SELECT`, `SELECT SINGLE`, `JOIN`, `FOR ALL ENTRIES`,
**`IMPORT … FROM DATABASE rfblg` (cluster read, NOT a SELECT)**, **`EXEC SQL … ENDEXEC` (native)**, and
**reads vs writes** (`INSERT/UPDATE/MODIFY/DELETE`). A regex that greps `(18)` misses `gv_matnr+9(9)`.
- **Backbone: abaplint's parser/AST** (TypeScript; runs with no SAP system; the corpus is abaplint-clean).
  Use it to enumerate DB-access *statements*, their target object, and read-vs-write — this solves
  statement boundaries, multi-line, IMPORT-FROM-DATABASE, and dedup in one move.
- **KB lookup = recall floor**: for each statement's object, look it up in the catalog.
- **LLM = only the dataflow escalations** the AST can't resolve alone (e.g. `matnr+0(9)` offset-parsing on
  a *variable* typed `mara-matnr` — connecting variable→object needs reasoning, not matching).
- **Statement grain + line (review fix #5):** emit **one finding per DB-access statement**, not one per
  textual mention. A file may reference `BSEG` on ~15 lines (`TABLES`, `TYPE bseg-…`, `TYPE TABLE OF
  bseg`); the finding's `line` is the **access statement** (the `SELECT`/`IMPORT`/`EXEC` line), never a
  `TABLES`/`TYPES` declaration.
- **Scan `*.abap` ONLY.** Ignore the paired `.prog.xml`/`.clas.xml` metadata (not code).

## The negative / suppression path — emit nothing on traps (review fix #6)
The corpus seeds precision traps *in the same files the skill reads*. The detector MUST suppress, not flag:
- **VALID tables** (e.g. MARA, MAKT, VBAK, VBAP, BKPF, T001, SKAT — not in the catalog as broken) → emit nothing.
- **`DECLUSTERED_SAME_NAME` reads** (CDPOS, CDHDR — a plain `SELECT FROM cdpos` still works) → emit nothing
  as a must-fix. (Only direct CDCLS cluster IMPORT/EXPORT would break — not present.)
- **World-B BAPIs/FMs** (released, still work) → emit nothing as must-fix.
- **`A-verify` / `B-verify`** (KNA1, LFA1, credit BAPI) → `action: verify` ONLY, never `auto_apply`.
Over-flagging any of these tanks precision — the negative path is as important as detection.

## Classification — change taxonomy (4 categories) → tier/action (the scored axes)
THREE axes per finding (they compose): **world** (must-I-fix, from catalog), **category** (what KIND of
change — the playbook key), **tier/action** (how much judgment — THE SCORED OUTPUT).

| Category | Nature | → Tier | → action | Playbook |
|---|---|---|---|---|
| **1 Syntactic** (rename, field length) | mechanical | T1 | `auto_apply` | deterministic 1:1 fix |
| **2 Structural** (type, compat view) | adjust access | T2 | `propose` | redirect read; propose |
| **3 Semantic** (data reshaped) | rebuild intent | T3 | `escalate` | ask `intent_question` → propose |
| **4 Functional** (capability gone) | redesign / triage | T3 | `escalate` | write-up, hand off, **don't auto-fix** |

Plus: A-verify/B-verify → `verify`; statement-level smell (SELECT*, DB-in-LOOP, EXEC SQL) →
`route_to_sibling` (Skill-4 handoff). Slide narrative: **SAP's ATC covers cat 1–2; we earn our keep at
3–4 — value peaks at 3, triage at 4.**

**Honest framing:** the **scored surface is two fields — `tier` and `action`.** `category` is the
classification + playbook key; emit it too (it IS in the schema now — review fix #4), but don't oversell
"three axes" to a Deloitte reviewer who'll read the contract. `world` is mostly catalog-derived.

## Escalation safety — make "0 unsafe auto-applies" STRUCTURAL, not a prompt hope (review fix #3)
Tier is a property of the *statement*, not the object: KONV *read* = T1 but **KONV *write* = T3**; MATNR =
T1 but **offset-parsed = T3**. The escalate-only ratchet (bump category UP the 1→4 spectrum, never down)
must be **enforced by a deterministic guard script**, not just instructed in prose:
- **Refuse `auto_apply`** whenever the statement is a write (`INSERT/UPDATE/MODIFY/DELETE`) OR the object's
  `baseline_tier` > T1 OR the LLM escalated it. Downgrade such findings to `escalate`.
This is what makes the headline "unsafe auto-applies = 0" true by construction.

## Structure — progressive disclosure (3 levels) + per-category playbooks
- **L1 frontmatter** (always loaded): `name` + a tight `description`. See "Description" below.
- **L2 `SKILL.md` body** (the procedure, NOT the data): run detector → classify → route per the table →
  apply guard → emit report. **Budget: ≤ ~500 lines / ~5k TOKENS** (review fix: the docs cap at 500 lines;
  our `CLAUDE.md` says "5000 words" — that's loose, follow the line limit). Push the routing detail +
  examples to `references/`.
- **L3 linked files** (load on demand): `scripts/` (detector, guard, emitter/validator, residual-check —
  **executed, not read into context**); `references/playbooks/{syntactic,structural,semantic,functional}.md`
  (ONE playbook per category, loaded JIT after classification; each = fix approach + escalation triggers +
  one before→after example + pointer to per-object override). Keep playbooks **one level from SKILL.md**
  (review fix — don't chain reference→reference). `assets/` = report skeleton.

**Efficiency principle:** KB stays in scripts; a playbook loads only after a finding is classified; only
the cat 3–4 residue reaches the LLM.

## Headless run contract (review fix #7, #8 — a demo-killer if skipped)
The scored run is `claude -p` in a sandbox with **NO human present**:
- **Output:** write `./remediation-report.json` at the sandbox root (the harness reads it there).
- **`escalate` = emit the `intent_question` string and STOP. NEVER await an answer** (no human → it would
  hang/time out). The ask-then-proceed loop is a *production-workflow* concept, not the scored run.
- **`usage` is HARNESS-filled.** The model cannot read its own token/cost counters. Emit `usage` as
  zeros/nulls; the harness overwrites them from the CLI `--output-format json` result.
- **Triggering:** the `description` must reliably fire on prompts like "remediate this ABAP for S/4HANA" /
  "what breaks in S/4HANA" / "S/4 ATC table-field remediation". Confirm the skill triggers under
  `claude -p` before relying on a scorecard.

## Output contract
Emit `remediation-report.json` per `eval/report-contract.schema.json`. Per finding: `file, line, object,
object_type, world, category, tier, action, replacement, rationale, intent_question, patch`; plus `run` +
`usage` (zeros — harness fills). `additionalProperties:false` — emit ONLY allowed keys or the report is
schema-invalid and scores zero. One finding per statement (BSEG = 1; field renames live inside the fix).

## Design rationale (v1 — simple; every choice maps to a metric)
- **Deterministic-first** (detection + cat-1 fixes are scripts) → 0 LLM tokens, perfect catalog recall. → Detection F1, cost-per-correct.
- **LLM only on cat 3–4 residue, playbook JIT** → minimal context/turns. → cost-per-correct.
- **Structural auto_apply guard** → "unsafe auto-applies = 0" by construction. → the safety headline.
- **NO subagents in v1.** Honest reason (review fix): the corpus is small (~39 files / ~3k LOC, fits one
  context) and deterministic-first already bounds what reaches the LLM — NOT "the human verifies" (there
  is no human in the scored run). Subagents (context-isolation, verifier) are a justified-LATER
  enhancement only if a metric demands them.

## How to iterate WITHOUT cheating (review fix — local fixtures)
- Build **2–3 tiny LOCAL fixtures** with hand-known expected output (write them yourself from general SAP
  knowledge — **NOT** copied from `findings.yaml`) and iterate the inner loop against those.
- Use the real harness sparingly as a coarse FINAL signal: `cd ../synthetic-sap-codebase && bash
  eval/run.sh --label <x>` (it reads `findings.yaml` internally; you never do). **Do not tune to
  individual finding IDs** — that's overfitting. You read the scorecard, never the answer key.

## Description (rewrite — the skeleton is stale)
The current `description` is SELECT-scoped and predates the tier model. Rewrite per the `CLAUDE.md` rule
(`[what] + [when] + [trigger phrases]`, <1024 chars, no `< >`). Cover: ABAP data access (SELECT *and*
IMPORT-FROM-DATABASE *and* EXEC SQL) on tables/fields that change in an S/4HANA brownfield conversion;
classifies by remediation complexity and emits a structured report; triggers on "S/4HANA conversion",
"ATC remediation", "what breaks in S/4", "table/field remediation".

## Build iteratively
Smallest working version first: deterministic detect (abaplint) + classify + emit valid contract JSON on a
couple of `src/` files (incl. one negative file, to get suppression right early). Then the guard script,
then the agentic cat 3–4 escalation + intent-question emission.

## Pointers
- `SPEC.md` (historical baseline — World-A/B only) · `CLAUDE.md` (skill-authoring rules — but note the
  "5000 words" figure is loose; the real cap is ~500 lines / 5k tokens)
- `../synthetic-sap-codebase/docs/02-eval-harness-plan.md` (contract + tiered metrics + scoring rules)
- `../synthetic-sap-codebase/docs/00-verified-research.md`, `01-build-plan.md` (SAP background)
- `../working-notes/2026-06-13-approach-rethink.md` (decision log D1–D10)
