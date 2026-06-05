# Evaluation results — Branch A (deterministic) vs Branch B (agentic)

**Date:** 2026-06-07. **Setup:** both skills built on the same knowledge base + verifier harness
(`feat/skill-3-base`), evaluated on two tiers with one objective scorer (`score.py`).

**Honesty caveats (state these in the talk):**
- The objective scorer uses subset/substring matching on 6 dimensions — generous by design; it
  measures detection & mapping, not prose quality.
- The Input-Program key is **reconstructed** from Deloitte's generation prompt, not their instructor
  key. Validate against the real ATC list on Monday.
- Rewrites are **not activation-verified** (no SAP compiler); abaplint is a generic-syntax proxy.

## Tier 1 — 12 labeled snippets (Attachment 3, with answer keys)

Dimensions: detect (obsolete tables flagged) · replacement (correct S/4 target named) ·
fields (correct renames) · blocker (no-clean-replacement marked) · precision (no World-B
over-flag) · residual (check_residual clean after rewrite, for non-blockers).

| Branch | detect | replacement | fields | blocker | precision | residual | **total** |
|---|---|---|---|---|---|---|---|
| A — deterministic | 12/12 | 12/12 | 12/12 | 12/12 | 12/12 | 12/12 | **72/72** |
| B — agentic ReAct | 12/12 | 12/12 | 12/12 | 12/12 | 12/12 | 12/12 | **72/72** |

**They tie on measurable correctness** — unsurprising, since both read the same KB. The interesting
signal is *how* they got there and what happens off the KB's beaten path.

## Tier 2 — realistic Input Program (`ZR_SD_OPEN_ORDER_MARGIN_COCKPIT`)

| | Branch A (deterministic) | Branch B (agentic) |
|---|---|---|
| World-A items recovered | all 7 (VBUK, VBUP, KONV, VAPMA, KNKK, VBTYP, MATNR-length) | all 7 |
| Output shape | 109 raw table occurrences (every line) | compacted to **8 distinct findings** (context-engineering, w03) |
| Statement-level | detected & routed: select_star, fae_no_guard, db_in_loop, native_exec_sql | same, routed not rewritten |
| Blocker | KNKK | KNKK |
| World-B BAPIs | 9 found, **none** marked must-fix | classified `atc_finding:false` / release-dependent, none rewritten |
| False-positive guard | MARA/MAKT/VBAK/VBAP not marked removed | same |

## Cost, reproducibility, robustness

| | Branch A | Branch B |
|---|---|---|
| Determinism | byte-identical every run | varies by wording/path |
| Cost / speed | ~free, instant (pure Python) | ~12 loop iterations + model tokens per program |
| Rewrite syntax | abaplint-CLEAN on the gold snippets (tc-01, tc-12 verified) | abaplint-CLEAN; **self-corrects** when a first pass leaves a residual (example-runs.md tc-12: iter1 left `FROM bseg` → iter2 clean) |
| Off-KB long tail | brittle — a table not in the KB is missed; can't reason | reasons: `SHKZG` not in KB → did **not** fabricate a rename, used `HSL` + flagged reviewer judgment; verify-only tables get an SE11 note |

## Failure modes observed (course w04 lens)

- Branch A: no infinite-loop/overflow risk (single pass), but **no recovery** — a malformed one-liner
  input produced a slightly off rewrite (the well-formed gold inputs were clean). Coverage is exactly
  the KB; silent miss on anything outside it.
- Branch B: bounded by a 3-iteration cap (no infinite loop); compaction avoids context overflow on the
  877-line program. Cost and non-determinism are the price.

## Verdict → recommendation: **hybrid (deterministic core + agentic escalation)**

For the curated 15-table scope with known patterns, the **deterministic engine is the right default**:
perfect, reproducible, free, and its rewrites parse clean. The **agentic loop earns its place on the
long tail** — tables/fields outside the KB, judgment calls (sign logic, verify-only), and structural
redesigns — where a rule table would miss or mis-map. The final skill should run deterministic
detection/rewrite first and **escalate only the uncertain residue to the agentic loop**.

Practical call for Monday: paste **Branch A's** Input-Program remediation into the Deloitte system
(reproducible baseline), keep Branch B for the judgment cases, and validate both against the real ATC
finding list.

## Known gaps / to fix

- Branch B `SKILL.md` validator path is `../../validator/` but the dir resolves one level higher — doc
  drift, harmless (check_residual is the authoritative signal). Fix before final.
- Scorer is generous (subset/substring). For the final eval, tighten replacement matching to the exact
  target table and add an abaplint-clean dimension.
