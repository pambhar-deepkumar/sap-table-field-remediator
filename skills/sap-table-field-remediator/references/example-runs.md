# Worked ReAct runs — few-shot guidance for the loop

These are real traces of the per-finding ReAct loop (the one in `SKILL.md`), executed against
the gold snippets and the input program. They double as few-shot examples: copy the shape, not
the literal text. Every recommendation traces to a `kb_lookup.py` row (citation) and every
rewrite is confirmed by `check_residual.py` (residual-clean) plus `lint_snippet.py` (parses).

Conventions in each trace: **REASON / ACT / OBSERVE / CLASSIFY / DECIDE / PROPOSE / VERIFY**, then
**STOP** (clean or cap). Commands are relative to the skill folder
`skills/sap-table-field-remediator/`.

---

## Run 1 — BSEG field-rename rewrite to ACDOCA (tc-01) — CLEAN @ iter 1

The headline World-A case: a removed/compatibility table with renamed fields.

**Input (ECC):**
```abap
SELECT * FROM bseg
  INTO TABLE lt_bseg
  WHERE bukrs = '1000' AND gjahr = '2023' AND belnr = '0100000123'.
LOOP AT lt_bseg INTO ls_bseg.
  WRITE: / ls_bseg-hkont, ls_bseg-dmbtr, ls_bseg-buzei.
ENDLOOP.
```

- **REASON** `bseg` is a table token in a `SELECT ... FROM`. Look it up.
- **ACT** `python3 scripts/kb_lookup.py --table BSEG --fields`
- **OBSERVE** `status=COMPATIBILITY VIEW, world=A, cds_view=I_JournalEntryItem, src=deloitte-attachment-1`.
  Field rows: `HKONT->RACCT`, `BUZEI->DOCLN`, `BUKRS->RBUKRS`; `DMBTR/GJAHR/BELNR` same name.
- **CLASSIFY** World A, must-fix. Not a blocker (clean replacement exists). release_dependent=false.
- **DECIDE** rewrite (table + field map + `RLDNR='0L'`); recommend CDS `I_JournalEntryItem` (REQ-002).
- **PROPOSE:**
```abap
SELECT * FROM acdoca
  INTO TABLE lt_acdoca
  WHERE rldnr = '0L'
    AND rbukrs = '1000' AND gjahr = '2023' AND belnr = '0100000123'.
LOOP AT lt_acdoca INTO ls_acdoca.
  WRITE: / ls_acdoca-racct, ls_acdoca-dmbtr, ls_acdoca-docln.
ENDLOOP.
```
- **VERIFY** `check_residual.py - < fix` -> `CLEAN` (exit 0). `lint_snippet.py` -> `ABAPLINT CLEAN`.
- **STOP** clean @ iteration 1.

Citation: BSEG row + field rows (deloitte-attachment-1/2). Caveat: not activation-verified; ACDOCA
field semantics (e.g. amount sign) should be confirmed on the target system.

---

## Run 2 — BSEG SELECT SINGLE, explicit field list (tc-09) — CLEAN @ iter 1

Shows the field map driving an explicit column list, and honest handling of a field with no 1:1
map (`SHKZG`).

**Input:** `SELECT SINGLE hkont buzei dmbtr shkzg FROM bseg INTO (...) WHERE bukrs=.. belnr=.. gjahr=.. buzei=..`

- **ACT** `kb_lookup --field BSEG.HKONT`, `--field BSEG.BUZEI`, `--field BSEG.BUKRS`.
- **OBSERVE** `HKONT->RACCT`, `BUZEI->DOCLN`, `BUKRS->RBUKRS` (all MOVED, world A). `SHKZG` has **no** KB row.
- **DECIDE** rewrite. For `SHKZG`: do not invent a map; ACDOCA carries signed amounts (`HSL`) — note this as a
  judgment call for the reviewer rather than asserting a column rename.
- **PROPOSE:**
```abap
" SHKZG not carried in ACDOCA; use signed amount HSL (debit/credit sign already applied).
SELECT SINGLE racct docln hsl
  FROM acdoca
  INTO (ls_acdoca-racct, ls_acdoca-docln, ls_acdoca-hsl)
  WHERE rldnr = '0L' AND rbukrs = lv_bukrs AND belnr = lv_belnr
    AND gjahr = lv_gjahr AND docln = lv_buzei.
```
- **VERIFY** `CLEAN` (exit 0), `ABAPLINT CLEAN`. **STOP** @ iter 1.

Lesson: when a referenced field is not in the KB, flag it for reviewer judgment; never fabricate a rename.

---

## Run 3 — RFBLG: ABOLISHED, no 1:1 access -> BLOCKER (tc-04) — no rewrite

The required ABOLISHED-no-replacement blocker case.

**Input:** `SELECT * FROM rfblg INTO TABLE lt_rfblg WHERE mandt = sy-mandt AND bukrs = '1000'.`

- **ACT** `kb_lookup --table RFBLG`
- **OBSERVE** `status=ABOLISHED, replacement="ACDOCA ... Direct cluster access not possible", cds_view=I_JournalEntryItem`.
- **CLASSIFY** World A. Although a CDS exists for the *data*, RFBLG is a physical FI **cluster** — there is no
  1:1 read swap; the access pattern itself is gone. Per REQ-005 -> **BLOCKER**.
- **DECIDE** route to manual redesign. **No rewrite, no fabricated fix.**
- **VERIFY** n/a (no rewrite to verify — expected for a blocker).
- **STOP** @ iter 1 with `status: BLOCKER`.

Report text: "RFBLG cluster cannot be accessed in S/4HANA. Data now lives in ACDOCA (Universal
Journal); the read logic must be redesigned, not text-swapped. Flag as BLOCKER. Source: RFBLG row,
deloitte-attachment-1. Not activation-verified."

Sibling blocker (tc-08, `S001`): `status=ABOLISHED, cds_view=null` -> BLOCKER, route to Embedded
Analytics / CDS (SAP Note 2267463). Same shape: no fake fix.

---

## Run 4 — KONV table swap (tc-02) — CLEAN @ iter 1, release-gated

A pure table-name swap where fields are identical.

- **ACT** `kb_lookup --table KONV` -> `ABOLISHED, replacement=PRCD_ELEMENTS (1909+), cds_view=null`.
- **DECIDE** swap token `konv -> prcd_elements`; keep field list and loop logic; gate on release >= 1909.
- **PROPOSE:** change `FROM konv` to `FROM prcd_elements` (and the `TYPE TABLE OF` decl); prepend a
  `" Verify target release >= 1909` comment.
- **VERIFY** `CLEAN`, `ABAPLINT CLEAN`. **STOP** @ iter 1.

Note: this is release-dependent in practice (release >= 1909). The KB marks the table
release_dependent=false but the replacement note carries the gate — surface it in the report.

---

## Run 5 — SELF-CORRECTION over two iterations (tc-12, BSEG GROUP BY) — CLEAN @ iter 2

Demonstrates the feedback loop catching an incomplete first attempt (the w04 guard in action).

**Input:** `SELECT hkont kostl SUM( dmbtr ) AS total_amount FROM bseg ... WHERE bukrs=.. gjahr=.. monat IN (..) GROUP BY hkont kostl.`

- **ITER 1 PROPOSE** mapped fields (`hkont->racct`, `bukrs->rbukrs`, `monat->poper`) but **left `FROM bseg`**.
- **ITER 1 VERIFY** `check_residual` -> `RESIDUAL: L2 obsolete_table BSEG` (exit 1). Not clean.
- **SELF-CORRECT** the reported residual is the table token -> swap `bseg -> acdoca`, add `RLDNR='0L'`.
- **ITER 2 PROPOSE / VERIFY** `CLEAN` (exit 0), `ABAPLINT CLEAN`.
- **STOP** clean @ iteration 2.

Lesson: the verifier names the exact residual (line + token). Fix that specific thing; do not
rewrite from scratch. If still dirty at iteration 3, emit `NEEDS-MANUAL` — do not loop forever.

---

## Run 6 — Input program: detect pass + World-A/B precision

Full program `ZR_SD_OPEN_ORDER_MARGIN_COCKPIT`. Context-compaction: one detect pass, then dedupe.

**EXPLORE** `python3 scripts/check_residual.py input-program.abap --json`
-> `residual_count: 66`, compacted to **8 distinct findings**:

| finding | type | lines (sample) | maps to expected |
|---|---|---|---|
| `KONV` | obsolete_table | 23, 371, 545, 557, 565 | A3 -> PRCD_ELEMENTS |
| `KNKK` | obsolete_table | 24, 393, 581, 804 | A5 -> FSCM/UKM (BLOCKER, verify) |
| `VAPMA` | obsolete_table | 106-110, 449 | A4 -> read VBAP / CDS (verify) |
| `VBUK` | obsolete_table | 21, 323 | A1 -> VBAK / I_SalesOrder |
| `VBUP` | obsolete_table | 22, 344 | A2 -> VBAP / I_SalesOrderItem |
| `VBTYP` | field_length_vbtyp | 44, 261, 279 | A7 -> VBTYPL (CHAR1->CHAR4, verify) |
| `matnr+0(18)` | matnr_offset_18 | 427, 479, 854 | A6 -> full 40-char MATNR (release-dep) |
| `LENGTH 18` | char18_decl | 118, 157, 158, 170, 833 | A6 -> drop CHAR18 |

That recovers **all 7 World-A findings** (A1-A7) from the expected key.

**PRECISION — must NOT over-flag:**
- **D-list still-valid tables** (REQ-008): `kb_lookup --table MARA|MAKT|LIKP|VBRK` all exit 3
  ("NOT-IN-KB -> still-valid, do not flag removed"). `VBAK`/`VBAP` ARE in the KB but as
  `status=RESTRUCTURED` (still exists; verify fields) — `check_residual` does **not** list them as
  residuals, so keeping them in a rewrite stays clean. None of the six appear as `obsolete_table`.
- **C-list World-B BAPIs** (REQ-007): `kb_lookup --bapi` classifies
  `BAPI_SALESORDER_CREATEFROMDAT2 / _CHANGE / BAPI_MATERIAL_GET_DETAIL / BAPI_TRANSACTION_COMMIT /
  _ROLLBACK` as `world=B, atc_finding=False` (key-only, NOT must-fix), and
  `BAPI_CUSTOMER_GETCREDITACCOUNT / WS_DELIVERY_UPDATE` as `world=B-verify, atc_finding=release-dependent`.
  None are table refs, so none appear in the residual detect output — they're noted, never rewritten.

**ROUTE (REQ-010), do not rewrite:** `SELECT *` (l.297), partial-key `SELECT SINGLE` in `calc_margin`
(l.556/564), DB-in-LOOP (`SELECT SINGLE maktx` l.490; EXEC SQL in LOOP l.611-621), native `EXEC SQL`
(l.611-615), unguarded `FOR ALL ENTRIES` (l.300/325/346/373/395). Owner = statement/performance skill.
The guarded FAE in `get_material_master` (`IF gt_item IS INITIAL. RETURN.` l.410-412) is correct — not flagged.

---

## Run 7 — Input program World-A rewrite: VBUK header status -> VBAK (A1) — CLEAN @ iter 1

`get_header_status` (l.317-326) reads from the abolished `VBUK`.

- **ACT** `kb_lookup --table VBUK` -> `ABOLISHED, replacement="folded into VBAK", cds_view=I_SalesOrder`.
  `kb_lookup --field VBUK.GBSTK` -> `GBSTK` now on VBAK.
- **DECIDE** rewrite: read the same status fields from `VBAK` (or released `I_SalesOrder`). Only `GBSTK`
  has an explicit KB field row; `LFSTK/FKSTK/UVALL/UVPRS` -> note "verify remaining status fields on
  target" rather than asserting maps (honesty: don't invent).
- **PROPOSE:** swap `FROM vbuk` to `FROM vbak`; add a comment that the FAE empty-table guard is a
  separate **routed** item (not fixed here).
- **VERIFY** `CLEAN` (exit 0), `ABAPLINT CLEAN`. **STOP** @ iter 1.

This is the pattern for VBUP->VBAP (A2) as well: status table removed, fields fold into the surviving
header/item table; cite the row; recommend the released CDS; keep release-dependent honesty for the
fields that have no explicit KB map.
