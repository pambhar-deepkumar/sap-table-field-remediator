# Expected findings — `ZR_SD_OPEN_ORDER_MARGIN_COCKPIT` (Input Program)

**Scope:** Skill 3 (Table & Field Remediator) findings only. **Status: reconstructed key** — derived from Deloitte's generation prompt taxonomy (`Prompt Skils 1 to 4.txt`) + the knowledge base, **not** validated against Deloitte's instructor key. Validate against the real ATC finding list in the Monday session.

**World A** = ATC-forced (Simplification DB flags it; must fix). **World B** = clean-core modernization (a *working released* BAPI/FM is **not** an ATC finding; key-only). Line numbers refer to `input-program.abap`.

## A. World-A table/field findings — OUR SCOPE (must fix)

| # | Object | Where (form / line) | Category | Replacement | Release-dependent | Blocker |
|---|---|---|---|---|---|---|
| A1 | `VBUK` | `TABLES` l.21; `get_header_status` SELECT l.317–326 | Removed table (header status) | Status folded into `VBAK` / `I_SalesOrder` | no | no |
| A2 | `VBUP` | `TABLES` l.22; `get_item_status` SELECT l.339–348 | Removed table (item status) | Status folded into `VBAP` / `I_SalesOrderItem` | no | no |
| A3 | `KONV` | `TABLES` l.23; `get_conditions` SELECT l.361; `calc_margin` SELECT SINGLE l.556, l.564 | Abolished cluster | `PRCD_ELEMENTS` (same fields, release ≥1909) | no | no |
| A4 | `VAPMA` | `get_index_data` SELECT l.444 | Eliminated SD index table | Read `VBAP` / released CDS | yes (verify) | no |
| A5 | `KNKK` | `TABLES` l.24; `get_credit` SELECT l.387 | Classic credit removed | FSCM/UKM (`UKMBP`/`UKM_ITEM`) — redesign | yes (verify) | yes |
| A6 | `MATNR` length (18→40) | `matnr_legacy` CHAR18 l.118; `gv_matnr_old/18` l.157–158; `gc_matnr_dummy` l.170; offset `matnr+0(18)` l.427, l.479, l.854; `lv_matnr_disp` CHAR18 l.833 | Field-length extension | Use full 40-char `MATNR`; drop CHAR18 / offset access | **yes** (priority depends on extended-matnr active) | no |
| A7 | `VBTYP`→`VBTYPL` | `ty_order-vbtyp` l.44; `gv_vbtyp_char` CHAR1 l.159; `gc_vbtyp_order` l.171; compare l.279–280 | Field-length change CHAR1→CHAR4 | Use `VBTYPL` | yes (verify on release) | no |

Field-rename specifics the rewrite must apply when moving SD status to VBAK/VBAP and (if any FI) to ACDOCA are in `references/field-mappings.json`.

## B. Statement-level findings — DETECT & ROUTE (sibling skill; we do NOT rewrite)

Flag with owner = "statement/performance skill", do not fix in Skill 3:
- `SELECT *` — `get_items` l.297 (`FROM vbap`).
- `SELECT SINGLE` on partial key — `calc_margin` l.556/564 (`konv` on `knumv/kposn/kschl`, no full key).
- DB access inside LOOP — `build_output` `SELECT SINGLE maktx` l.490; `read_netwr_native` EXEC SQL in LOOP l.606–621.
- Native `EXEC SQL` — `read_netwr_native` l.611–615.
- `FOR ALL ENTRIES` without empty-table guard — `get_items` l.300, `get_header_status` l.325, `get_item_status` l.346, `get_conditions` l.373, `get_credit` l.395.

## C. World-B — MODERNIZATION, key-only (must NOT be reported as ATC-forced)

| Object | Form / line | ATC finding? | Modernization target |
|---|---|---|---|
| `BAPI_SALESORDER_CREATEFROMDAT2` | `create_followup_orders` l.667 | **no** | `MODIFY ENTITIES OF I_SalesOrderTP` |
| `BAPI_SALESORDER_CHANGE` | `change_open_orders` l.724 | **no** | `MODIFY ENTITIES OF I_SalesOrderTP` |
| `BAPI_MATERIAL_GET_DETAIL` | `read_material_detail` l.759 | **no** | Released product CDS / API |
| `BAPI_TRANSACTION_COMMIT/ROLLBACK` | l.679, l.681, l.735, l.739 | **no** | none (still valid) |
| `BAPI_CUSTOMER_GETCREDITACCOUNT` | `get_credit_exposure` l.810 | release-dependent | FSCM/UKM (tied to classic credit) — verify in SYCM |
| `WS_DELIVERY_UPDATE` | `post_delivery_update` l.787 | release-dependent | Released delivery API — verify in SYCM |

## D. False-positive guards — still-valid tables, must NOT be flagged obsolete

`MARA` (l.418), `MAKT` (l.490), `VBAK` (l.262), `VBAP` (l.297), `LIKP`, `VBRK` (declared l.19–27) still exist in S/4HANA. The skill may say "verify fields on target" but must **not** mark them removed/abolished. The guarded FAE in `get_material_master` (`IF gt_item IS INITIAL. RETURN.` l.410–412) is the **correct counter-example** — do not flag it.

## Scoring intent

A good Skill-3 result on this program: catches A1–A7 (World A, our scope), routes B-items without rewriting them, does **not** over-flag the C World-B BAPIs as must-fix, and does **not** flag the D still-valid tables. Precision on World-A/B separation is the headline metric.
