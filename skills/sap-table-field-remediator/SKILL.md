---
name: sap-table-field-remediator
description: Analyzes SAP ABAP code to find SELECT statements on tables or fields that become obsolete or restricted in S/4HANA Brownfield conversions, and recommends modern replacements (released CDS views where available).
---

# SAP Table & Field Remediator

> **Status:** Skeleton. Implementation begins Phase 2 of the project.

## When to use this skill

Use this skill when you have legacy SAP ABAP code (custom code from an ECC system) and need to know which `SELECT` statements will break after a Brownfield S/4HANA conversion, and what to use instead.

## What this skill does

1. Reads the ABAP code snippet provided.
2. Identifies every `SELECT` statement.
3. Checks each table/field against the SAP Simplification Item Catalog.
4. Classifies each finding:
   - `1:1 transferable` — no change needed.
   - `obsolete-with-replacement` — recommend the released CDS view.
   - `obsolete-no-replacement` — route to manual review.
   - `restricted-field` — flag the specific field on a still-valid table.
5. Produces a structured markdown remediation report.

## Inputs

- A snippet of ABAP code (text).

## Outputs

- A markdown report: per-statement classification + reasoning + recommended replacement (when known).

## Implementation notes

To be filled during Phase 2. See `docs/` for design decisions as they accumulate.
