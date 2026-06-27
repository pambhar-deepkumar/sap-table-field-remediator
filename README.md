# SAP Table & Field Remediator

A Claude Code **plugin** that scans custom ECC ABAP for table/field accesses that break in an
**S/4HANA brownfield conversion**, tiers each fix by how much human judgment it needs (T1/T2/T3),
and emits a machine-readable `remediation-report.json`. Detection is deterministic (abaplint AST +
the **Remediation Catalog**); the LLM does judgment only on the hard cases; a human signs off. Ships
a **page-cited Simplification KB** served over MCP.

> **Three names, kept distinct:** the **SAP Simplification List** is SAP's official ECC→S/4 change
> document (the upstream source). The **Remediation Catalog** (`simplification-list.yaml`) is *our*
> curated, per-engagement lookup keyed by table/field object — status, tier, target. The
> **Simplification KB** is SAP's document chunked + page-cited over MCP, queried by the LLM for
> evidence on hard cases.

## Install

```
claude plugin marketplace add pambhar-deepkumar/sap-table-field-remediator
claude plugin install sap-table-field-remediator@sap-remediator
```

One command set installs the skill **and** the `simplification-kb` MCP server — no path editing,
no venv. Prerequisites:

| Need | Why | Install |
|---|---|---|
| **Claude Code** | runs the plugin | — |
| **Node.js** ≥ 18 | the abaplint AST detector | https://nodejs.org |
| **uv** *(optional)* | runs the bundled KB server with no venv/pip | https://docs.astral.sh/uv |

`uv` is optional — the skill detects and tiers findings without the KB; the KB only enriches the
harder (T3) fixes with page-cited SAP evidence.

## Try it

In Claude Code, with no code of your own:

> *"Run the SAP Table & Field Remediator on the bundled example."*

It scans `examples/zdemo_s4_check.abap` and produces a tiered report. Then point it at your code:

> *"Remediate the ABAP in `./src` for an S/4HANA brownfield conversion."*

Full walkthrough: **[QUICKSTART.md](QUICKSTART.md)**.

## What it does

1. **Detect** every DB-access statement (SELECT/JOIN/FOR ALL ENTRIES, `IMPORT … FROM DATABASE`,
   `EXEC SQL`) via abaplint's AST — not regex.
2. **Classify & tier** each finding: T1 mechanical (`auto_apply`), T2 bounded (`propose`), T3
   intent-needed (`escalate`). A structural guard guarantees **0 unsafe auto-applies, by construction**.
3. **Derive** the variant-correct fix for T3 cases from the bundled Simplification KB
   (page-cited), reached over MCP — evidence, not an oracle.
4. **Emit** a schema-valid `remediation-report.json`. A human reviews and signs off.

## Evaluation

Blind-run against a synthetic ground-truth corpus (18 abapGit objects, 30 labeled findings across
SD/MM/FI). The skill saw only the code + the public Remediation Catalog; the scorer ran outside the sandbox
against a secret answer key it never exposed to the skill. Single run, `claude-opus-4-8`, analysis
mode, 2026-06-27.

| Metric | Result |
|---|---|
| Detection F1 | **90.9%** (precision 93.8% · recall 88.2%) |
| Tier accuracy | **100%** (15/15) |
| Unsafe auto-applies | **0** (guaranteed by construction) |
| Distractor over-claims | **0 / 7** (0 / 5 on clean negatives) |
| Correct-replacement rate | 80% (12/15) |
| Cost / run | **$2.75** (~$0.18 per correct finding · ~5 min · 30 turns) |

Full scorecard: [`eval/scorecard-opus48-v1.md`](eval/scorecard-opus48-v1.md).

**Caveats (read before quoting):** tier accuracy is perfect but rests on a thin base for the easy
tiers (2 T1, 3 T2 cases; T3 is well-covered) — corpus rebalancing is in progress. The two misses
(F-MM-03, F-SD-05) and one spurious flag are listed in the scorecard. Single run, so cost is a point
estimate.

## How it's packaged

One repo = the skill + the KB MCP server + the plugin/marketplace manifest:

```
.claude-plugin/         marketplace.json + plugin.json
.mcp.json               launches the KB server via `uv run`
skills/sap-table-field-remediator/   the skill (SKILL.md + scripts/references)
mcp/                    the KB server (server.py + 429 page-cited chunks)
examples/               a demo ABAP program for zero-setup trials
```

## Project context

Part of a TUM × Deloitte research project (Summer 2026): *AI-Powered SAP Custom Code Analyzer*.
Skill 3 of 6 (Table & Field Remediator). Built entirely from **public** SAP material + **synthetic**
sample data.

## Contributing

See `CONTRIBUTING.md` for the PR flow. `CLAUDE.md` documents the skill-authoring spec followed in
`skills/sap-table-field-remediator/`.
