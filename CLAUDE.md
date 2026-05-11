# CLAUDE.md — AI assistance rules for this repo

Read this before writing or generating code here.

## What this skill is

A Claude Code skill that detects SAP ABAP code referencing tables/fields broken under S/4HANA Brownfield conversion, and recommends remediation. Input: ABAP text. Output: structured markdown report.

Audience: SAP migration engineers (Deloitte) and graders (TUM). Not end-users.

## What we are NOT building

- We do NOT rewrite ABAP code. We *recommend*.
- We do NOT need a database, auth, or microservices.
- We do NOT need a CLI framework — a 30-line script is enough if needed.
- We do NOT need multi-environment CI/CD.

If you're about to add any of the above, stop and raise it in the PR description first.

## AI usage rules (anti-rubber-stamp)

- **Every AI-generated PR must list what the human verified.** No exceptions.
- **Never edit a test case's expected output to make a failing test pass.** Fix the skill instead.
- **Don't fabricate SAP details.** Every claim about an obsolete table/field/CDS view must cite the SAP Simplification Item Catalog or a public source, or be explicitly marked TBD.
- **Plan before implementing.** For any change >50 LOC, write a 3-line plan in the PR description before opening it for review.
- **One peer review required.** PRs cannot self-merge.

## Code & file conventions

- Skill format follows Anthropic's official spec: `SKILL.md` with YAML frontmatter (`name`, `description`) + markdown body. Reference: github.com/anthropics/skills.
- Examples in `examples/<NN-short-name>/` with an `input.abap`, `expected.md`, and a brief `README.md`.
- Tests in `tests/` use `pytest`. Each test case has a clear expected output to score against.
- Python style: standard `ruff` defaults if/when Python enters.

## Test discipline

- Every PR that changes skill behavior must add or update a test case.
- Test case expected outputs are the source of truth, not the skill output.

## Out of scope (do not propose)

- ABAP code rewriting / auto-fixing.
- Live SAP system integration — skill operates on text only.
- Authentication, user accounts, persistence.
