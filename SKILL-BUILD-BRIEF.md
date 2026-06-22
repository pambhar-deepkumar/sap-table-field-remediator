# Skill Build Brief — Tier-Aware Table & Field Remediator

**For:** a fresh Claude session that will build the skill. **Date:** 2026-06-22.
**Read this first. It is self-contained — you do NOT need the long design conversation that preceded it.**

---

## ⛔ THE ONE HARD RULE (blind build — eval integrity depends on it)

**NEVER open `../synthetic-sap-codebase/ground-truth/findings.yaml`.** That is the SECRET answer key.
If this session reads it, every precision/recall number the eval produces becomes meaningless (the
skill would be tuned to the answers). Build the skill from the public catalog + general SAP knowledge
ONLY.

You MAY read:
- `../synthetic-sap-codebase/src/**` — the ABAP code under test.
- `../synthetic-sap-codebase/ground-truth/simplification-list.yaml` — the PUBLIC catalog (the skill would
  legitimately have this in production).
- `../synthetic-sap-codebase/eval/report-contract.schema.json` and `docs/02-eval-harness-plan.md` — the
  output contract + metrics.
- This repo's existing work (below).

You MUST NOT read: `findings.yaml`. Do not infer its contents. Do not grep for it.

## Mission
Build the **tier-aware** Table & Field Remediator as a Claude Code skill that, given custom ECC ABAP,
detects references to tables/fields that change in an S/4HANA brownfield conversion and emits a
**machine-readable remediation report** (the contract below) that routes each finding by *how much
human judgment its fix needs*.

## What already exists here — REUSE, don't rebuild
- `skills/sap-table-field-remediator/` — the skill folder (currently a skeleton `SKILL.md` on
  `feat/skill-3-base`; richer implementations on branches `feat/skill-A-deterministic` and
  `feat/skill-B-agentic`).
- `skills/.../references/*.json` — the **knowledge base** (real Deloitte table/field mappings + World A/B
  + CDS views). This is the catalog spine. Reuse + extend; add the tier field.
- `SPEC.md` — the original EARS spec. **Note: it predates the tier model** (it only has World A/B). Treat
  it as the historical baseline; this brief carries the new design that supersedes the World-only view.

## The verdict to build on (already proven)
The A-vs-B head-to-head concluded **hybrid: deterministic core + agentic escalation**. Detection is
deterministic (KB lookup / abaplint — never let the LLM *find*, it hallucinates); the LLM does
*judgment* (classify tier, propose fix, ask the intent question). Run the cheap deterministic path for
the common case; escalate only the uncertain residue to the paid agentic loop.

## The NEW design (the delta vs the old World-A/B-only skill)
Two ORTHOGONAL axes per finding:
- **world** A | A-verify | B — *must I fix it?* (from the catalog; already exists)
- **tier** T1 | T2 | T3 — *how much human judgment does the fix need?* (NEW — the scored axis)

Tier → action mapping the report uses:
- **T1 mechanical** → `auto_apply` (deterministic 1:1 fix, no human)
- **T2 bounded-semantic** → `propose` (agent proposes → verifier → human signs off)
- **T3 needs-human-intent** → `escalate` (agent asks a targeted `intent_question`, then proceeds)
- A-verify / B-verify → `verify` (flag "verify on target", don't hard-fix)
- statement-level smell (SELECT*, DB-in-LOOP, EXEC SQL) → `route_to_sibling` (Skill-4 handoff)

**Escalation safety (critical):** a finding's baseline tier comes from the catalog, but the agent may
**escalate it (never downgrade)** when the specific usage is riskier than the object implies — e.g. a
MATNR that is *parsed by character offset*, or a *write* to an abolished/condition table. Such cases must
NOT be `auto_apply`. This "escalate-only" ratchet is what makes zero-human T1 defensible, and the eval
scores "unsafe auto-applies must = 0".

## Output contract (what the skill must emit)
Emit `remediation-report.json` conforming to `../synthetic-sap-codebase/eval/report-contract.schema.json`
(one entry per finding: file, line, object, object_type, world, tier, action, replacement, rationale,
intent_question, patch; plus run + usage metadata). Statement grain: one finding per problematic SQL
statement (BSEG = 1 finding; field renames live inside the fix, not as separate findings).

## How to get feedback WITHOUT cheating
You may run the harness to get a scorecard: `cd ../synthetic-sap-codebase && bash eval/run.sh --label <x>`
(it scores against `findings.yaml` internally — the *harness* reads it, you never do). Treat the scorecard
as a coarse final signal, **not** a tuning oracle — do not iterate against individual finding IDs
(that's overfitting). The integrity rule is absolute: you read the scorecard, never the answer key.

## Build iteratively
Smallest working version first: deterministic detect + classify + report on a couple of `src/` files,
emitting valid contract JSON. Then add the agentic escalation path, the intent-question loop, and the
verifier. Match effort to the demo + the metrics.

## Pointers (design rationale, all readable)
- `SPEC.md` (historical baseline) · `CLAUDE.md` (Anthropic skill-authoring rules — follow them)
- `../synthetic-sap-codebase/docs/02-eval-harness-plan.md` (contract + tiered metrics + scoring rules)
- `../synthetic-sap-codebase/docs/01-build-plan.md`, `00-verified-research.md` (SAP background)
- `../working-notes/2026-06-13-approach-rethink.md` (full decision log D1–D10)
