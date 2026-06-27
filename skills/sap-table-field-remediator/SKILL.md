---
name: sap-table-field-remediator
description: Scans custom ECC ABAP for data access (SELECT, SELECT SINGLE, JOIN, FOR ALL ENTRIES, IMPORT FROM DATABASE cluster reads, and EXEC SQL native SQL) on tables or fields that change in an S/4HANA brownfield conversion, classifies each finding by remediation complexity (syntactic, structural, semantic, functional tiers T1/T2/T3), routes it (auto_apply, propose, escalate, verify, route_to_sibling) with a deterministic safety guard, and emits a machine-readable remediation-report.json. Use for "S/4HANA conversion", "ATC remediation", "what breaks in S/4HANA", "table/field remediation", "S/4 SELECT/table check", "remediate this ABAP for S/4HANA", or analyzing legacy ABAP against the SAP simplification list.
---

# SAP Table & Field Remediator

Detect custom ABAP that references tables/fields that change in an **S/4HANA brownfield
conversion**, classify each by **how much human judgment its fix needs**, and emit a
machine-readable `remediation-report.json`. Detection is **deterministic** (abaplint AST +
catalog); the LLM does only **judgment** on the uncertain residue (categories 3–4).

## When to use
Legacy/custom ECC ABAP + a question like "what breaks in S/4HANA?", "remediate this for the
conversion", "run the ATC table/field check". Inputs: a directory of `*.abap` and the public
catalog `simplification-list.yaml`.

## Mental model (do not skip)
- **The Remediation Catalog is truth.** `simplification-list.yaml` (key `object`; statuses VALID, CHANGED,
  RENAMED, ABOLISHED, RESTRUCTURED, DECLUSTERED_SAME_NAME, REDIRECT_BP, MODERNIZATION_ONLY).
  `scripts/catalog.py` loads it; never hand-maintain a second table.
- **Detection is AST, not regex.** `scripts/detect.js` uses abaplint to enumerate DB-access
  *statements* and their target object + read-vs-write. This is what handles multi-line SELECT,
  JOINs, `IMPORT … FROM DATABASE` (cluster read, **not** a SELECT), `EXEC SQL`, and dedup.
- **One finding per statement** keyed on the cataloged object. Field renames live inside the fix.
- **Safety is structural.** `scripts/guard.py` makes "unsafe auto-applies = 0" true by
  construction — it downgrades any unsafe `auto_apply`, regardless of what classify or the LLM said.
- See `references/taxonomy.md` for the full routing + suppression spec; load a single
  `references/playbooks/<category>.md` only AFTER a finding is classified.

## Procedure

### 0. Setup (once)
The detector needs `@abaplint/core`. Run the idempotent installer:
```
bash scripts/setup.sh
```
If `node` is missing, install Node.js first. abaplint runs with no SAP system.

### 1. Run the deterministic pipeline
From the working dir that contains `src/` and the catalog (the eval sandbox has the catalog at
`./ground-truth/simplification-list.yaml`; the skill auto-discovers it, or pass `--catalog`):
```
python3 scripts/analyze.py --src ./src --out ./remediation-report.json --mode analysis
```
This runs **detect → classify → guard → emit**. It writes a **schema-valid**
`remediation-report.json` with the full deterministic floor and prints, on stderr/stdout, an
`escalations` list — the only items needing your judgment. **The report is already valid and
scoreable even if you stop here.**

What `analyze.py` does for you (no LLM tokens):
- flags every cataloged must-fix DB statement; **suppresses** VALID tables,
  `DECLUSTERED_SAME_NAME` reads (CDPOS/CDHDR), and World-B BAPIs (emits nothing);
- emits `verify` (never `auto_apply`) for A-verify/B-verify (KNA1, LFA1);
- assigns tier+action+category per `references/taxonomy.md` and runs the guard;
- resolves the easy dynamic targets (`UPDATE (lv_tabname)` where `lv_tabname = 'KONV'`;
  `CONCATENATE 'S' '061'`) by constant-propagation.

### 2. Refine ONLY the escalations (the LLM's job)
For each item in `escalations`, open the **one** matching playbook
(`references/playbooks/{syntactic|structural|semantic|functional}.md`) and the source line, then:

**Ground the fix in the SAP Simplification List (via the Simplification KB, if connected).** Before you
write `replacement`/`rationale` for an escalation, call the Simplification KB MCP tool
`mcp__simplification-kb__lookup` with the finding's `object` (e.g. `lookup(object="BSEG")`). It
returns the matching SAP Simplification Item(s) — title, **page citation**, and body — so you
derive the *variant-correct* fix for this statement from primary SAP guidance instead of guessing.
Use `mcp__simplification-kb__search` for the multi-hop case (e.g. `search("pricing data model")`
when the object alone isn't enough). The KB is **evidence, not an oracle**: read it, then decide.
**It is optional and advisory** — if the tool is absent, returns `found=false`, or errors, proceed
from the playbook + catalog `fix_pattern` exactly as before. Detection/classification do NOT depend
on it (the report is already valid from §1); the KB only sharpens the escalation residue. Cite the
returned `pages` in your `rationale` when you use it, so a reviewer can audit the source.

- **`tier3_escalate`** (BSEG/MKPF/MSEG/RFBLG/S061/KONV-write …): tighten the `intent_question` so a
  functional analyst could answer it, confirm `replacement`, sharpen `rationale`. Use
  `semantic.md` (RESTRUCTURED) or `functional.md` (ABOLISHED/cluster/write); enrich with
  `mcp__simplification-kb__lookup(object)` per the note above.
- **`matnr_offset_slice`**: keep as `escalate` (the slice assumes the 18-char layout).
- **`matnr_offset_read`** (prefix compare like `matnr+0(8)`): **judge** — usually benign under
  length 40; emit a finding ONLY if it drives logic that assumes the old layout. Default: suppress.
- **`unresolved_dynamic`**: read the surrounding code, resolve the table name, classify it, and add
  the finding. If you genuinely cannot resolve it, leave it out rather than guess.

Edit `remediation-report.json` in place. Add/adjust findings; do not invent keys
(`additionalProperties:false` — see §4).

### 3. Re-run the guard (mandatory after any edit)
Any time you change actions/tiers, re-assert the safety guarantee:
```
python3 scripts/guard.py --in <intermediate-with-_meta>.json --report   # summary
```
In practice: re-run `analyze.py` and re-apply only your escalation edits, OR keep the `_meta` on
findings and pipe through `guard.py`. The headline "unsafe auto-applies = 0" must hold.

### 4. Output contract (hard rules — a violation scores zero)
- Write `./remediation-report.json` at the working-dir root (the harness reads it there).
- Conform to `eval/report-contract.schema.json`. Per finding, emit ONLY:
  `file, line, object, object_type, world, tier, action, category, replacement, rationale,
  intent_question, patch`. No extra keys.
- `object` = the **cataloged name** (e.g. `BSEG`), uppercase. `line` = the access statement line.
- `escalate`/`T3` findings MUST carry an `intent_question`.
- `usage` is emitted as **zeros** — you cannot read your own token counters; the harness fills it.
- `analyze.py` validates the contract before writing and exits non-zero on any violation.

## Headless run contract (`claude -p`, no human present)
- **`escalate` = emit the `intent_question` and STOP.** Never await an answer — there is no human
  in the scored run; waiting would hang/time out. The ask-then-proceed loop is a *production*
  workflow, not the scored path. The classification still happens; only the human turn is skipped.
- Scan `*.abap` ONLY. Ignore paired `*.prog.xml` / `*.clas.xml` (metadata, not code).
- Two modes: `analysis` (report only — the scored path) and `apply` (also writes T1 patches; then
  `python3 scripts/residual_check.py --src ./src` gates that no must-fix reference survives).
- **Simplification KB (optional enrichment).** To give the escalation step §2 the KB tools,
  pass the server config and allow its tools:
  ```
  claude -p "remediate ./src for S/4HANA" \
    --mcp-config /path/to/project/.mcp.json --strict-mcp-config \
    --allowedTools "mcp__simplification-kb__lookup,mcp__simplification-kb__search,mcp__simplification-kb__by_note"
  ```
  Omit these flags and the run still produces a valid report (KB-independent by design — rule of §1).

## Scripts (L3 — executed, not read into context)
| Script | Role |
|---|---|
| `scripts/detect.js` | abaplint-AST detector → DB-access statements (read/write, dynamic, offsets) |
| `scripts/catalog.py` | loads the Remediation Catalog `simplification-list.yaml` (auto-discovers it at runtime) |
| `scripts/classify.py` | catalog lookup → world/category/tier/action + `escalations` list |
| `scripts/guard.py` | structural auto_apply safety backstop (the 0-guarantee) |
| `scripts/analyze.py` | one-command pipeline: detect→classify→guard→validate→emit report |
| `scripts/residual_check.py` | apply-mode verification (non-zero if a must-fix reference remains) |

## Common failures
- **`@abaplint/core not installed`** → run `bash scripts/setup.sh`.
- **`No simplification-list.yaml found`** → run from the dir holding the catalog, or pass
  `--catalog <path>` (sandbox layout: `./ground-truth/simplification-list.yaml`).
- **Schema validation errors** → `analyze.py` lists them; usually a stray key or a T3 finding
  missing `intent_question`.
- **Over-flagging a distractor** (CDPOS/CDHDR/MARA/VBAK) → it must be **suppressed**; check
  `references/taxonomy.md`. Over-claiming tanks precision as hard as a miss.
