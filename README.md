# SAP Table & Field Remediator

A Claude Code skill that flags SAP ABAP code referencing tables/fields that break after an S/4HANA Brownfield conversion, and recommends modern replacements (released CDS views where available).

> **Status:** Scaffolding only. Skill implementation begins Phase 2.

## What this skill does

Given a snippet of legacy ABAP code, the skill:
1. Detects `SELECT` statements on obsolete or restricted tables/fields.
2. Classifies each finding (obsolete-with-replacement, obsolete-no-replacement, restricted-field).
3. Recommends a modern replacement or routes to manual review.
4. Returns a structured markdown remediation report.

## Try it in 5 minutes

> Requires [Claude Code](https://docs.claude.com/en/docs/claude-code) installed locally.

```bash
# 1. Clone (private repo — requires GitHub access; ask Deep for collaborator invite)
git clone https://github.com/pambhar-deepkumar/sap-table-field-remediator.git
cd sap-table-field-remediator

# 2. Install the skill (TODO — fill in once SKILL.md is implemented;
#    likely a symlink or copy into ~/.claude/skills/)

# 3. Try an example (TODO — fill in once skill exists)
```

Paste-and-go examples will live in `examples/`.

## For Deloitte engineers giving feedback

- Read `docs/feedback-asks.md` first — it narrows what we'd love your eyes on this round.
- Open a GitHub issue or comment on the PR Deep links you to.

## Project context

This skill is part of a TUM × Deloitte research project (Summer 2026): *AI-Powered SAP Custom Code Analyzer — Leveraging Anthropic Claude for Automated S/4HANA Conversion Assessment*. We're the Table & Field Remediator sub-team (Skill 3 of 6). Strategic / operational context lives outside this repo intentionally.

## Contributing

Read `CLAUDE.md` before using AI assistance in this repo. See `CONTRIBUTING.md` for PR flow.
