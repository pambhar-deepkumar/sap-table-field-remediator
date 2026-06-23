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
THREE axes per finding — they compose; do not conflate them:
- **world** A | A-verify | B — *must I fix it?* (from the catalog; already exists)
- **category** 1–4 — *what KIND of change is it?* (the classification + the playbook key — see below)
- **tier** T1 | T2 | T3 — *how much human judgment does the fix need?* (the SCORED axis — emit this)

### Change taxonomy (4 categories) → tier/action (3 tiers)
Classify each finding into one category; the category maps to the scored tier/action:

| Category | Nature | → Tier | → action | Playbook does |
|---|---|---|---|---|
| **1 Syntactic** (rename, field length) | mechanical | T1 | `auto_apply` | apply the deterministic 1:1 fix, no human |
| **2 Structural** (type, compat view) | adjust access | T2 | `propose` | redirect the read; propose; human signs off |
| **3 Semantic** (data reshaped) | rebuild intent | T3 | `escalate` | ask the `intent_question` → then propose |
| **4 Functional** (capability gone) | redesign / triage | T3 | `escalate` | write up the analysis, hand to a consultant, **don't auto-fix** |

Plus two non-category actions: A-verify / B-verify → `verify` (flag "verify on target", don't hard-fix);
statement-level smell (SELECT*, DB-in-LOOP, EXEC SQL) → `route_to_sibling` (Skill-4 handoff).

Narrative (and a slide): **cat 1–2 are what SAP's own ATC/Simplification DB already cover; our tool
earns its keep at 3–4 — value peaks at 3 (still codeable after intent), triage at 4.**

**Scoring note:** `tier`/`action` are what the harness scores — emit them. `category` is the skill's
classification + the playbook selector + an informative report field. We do NOT re-tag the corpus or
change what the harness scores. (Category-accuracy could become a metric later by tagging findings.yaml.)

**Escalation safety (critical) = bump the category UP the 1→4 spectrum, never down.** A finding's
baseline category/tier comes from the catalog, but the agent may **escalate** when the specific usage is
riskier than the object implies — e.g. a MATNR *parsed by character offset* (Syntactic→Semantic) or a
*write* to an abolished/condition table (→ Functional). Escalated cases must NOT be `auto_apply`. This
escalate-only ratchet is what makes zero-human T1 defensible; the eval scores "unsafe auto-applies = 0".

## Structure — progressive disclosure (3 levels) + per-category playbooks
Lay the skill out so the heavy stuff loads only when needed (token + context efficiency):
- **L1 frontmatter** (always loaded; the trigger): `name` + a tight `description` (what + when + trigger
  phrases). Nothing else.
- **L2 `SKILL.md` body** (loads when relevant; the playbook, NOT the data): the procedure — run the
  deterministic detector → classify each finding into a category → route by the table above → emit the
  report. Lean (<5k words); point to L3 for depth.
- **L3 linked files** (load on demand; the depth):
  - `scripts/` — the deterministic detector (reads the KB, finds + baseline-classifies), report
    emitter/validator, residual-check. **Executed, not read into context.**
  - `references/playbooks/{syntactic,structural,semantic,functional}.md` — ONE playbook per category,
    loaded JIT *after* a finding is classified. Each playbook = the fix approach + when it escalates
    + a worked before→after example + pointer to the per-object override (field maps, CDS view, SAP note).
  - `references/*.json` — the KB (read by the detector script, not the LLM) + the report schema.
  - `assets/` — report skeleton / templates.

**The efficiency principle:** the KB lives in scripts (never in LLM context); a finding's playbook loads
only after it's classified; only the cat 3–4 residue reaches the LLM. A program with only BSEG issues
never loads the Syntactic/cluster playbooks.

## Design rationale (v1 — keep it simple; every choice maps to a harness metric)
- **Deterministic-first.** Detection + cat-1 Syntactic fixes are scripts → 0 LLM tokens, perfect recall
  on the catalog, reproducible. (Backed: prior eval measured the deterministic path at ~$0.) → feeds
  Detection F1 + cost-per-correct.
- **LLM only on the cat 3–4 residue, playbook loaded JIT** → minimal context, fewer turns. → cost-per-correct.
- **Escalate-only ratchet** → never auto-applies a risky fix. → "unsafe auto-applies = 0".
- **NO subagents in v1.** The human is the verifier for T2/T3 (fits "human review non-negotiable").
  Context-isolation + verifier subagents are an explicit LATER enhancement, justified only if a metric
  needs them — not core. (Rationale for the talk: subagents add tokens; deterministic-first already
  bounds what reaches the LLM, so v1 doesn't need them.)

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
