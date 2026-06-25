# Playbook — Category 3: Semantic (T3 → escalate)

**Nature:** the data was **reshaped** — same business object, different granularity / key /
on-the-fly computation. A mechanical rewrite would compile but be **wrong**. This is where the
skill earns its keep: the LLM must understand the read's *intent* before proposing a fix.

## Fix approach
1. State the reshape (catalog `fix_pattern`): what moved, what changed key/granularity.
2. Emit a sharp `intent_question` that a functional analyst can answer — this is the deliverable
   in the scored run. **Emit it and STOP; never await an answer** (no human in the headless run).
3. Propose the most likely target (`replacement`) conditioned on the probable intent.
4. Emit `tier: T3`, `action: escalate`, `category: semantic`.

## Canonical cases
- **BSEG → ACDOCA** (Universal Journal): line items now in ACDOCA; renames BUKRS→RBUKRS,
  HKONT→RACCT, BUZEI→DOCLN (3→6 char), add RLDNR='0L'. *Intent:* full line-item detail vs
  aggregated journal? which ledger?
- **MKPF / MSEG → MATDOC**: header+item merged; stock computed on the fly. *Intent:* are append
  fields / stock-snapshot semantics relied on?
- **MATNR offset-parsing** (`gv_matnr+9(9)`): code assumes the 18-char layout; under length 40 the
  slice is wrong. *Intent:* what does the sub-range mean (a real sub-key, or a legacy convention)?

## Escalation triggers (always T3 here)
- Offset/length slice **assigned** off a MATNR-typed field → flag (high confidence).
- A read-only prefix compare (`matnr+0(8) = '00000000'`) → **judge**: often benign under length 40
  (still reads the first 8 chars). Suppress unless it drives a branch that assumes 18-char layout.

## Before → after (proposed, pending intent)
```abap
" before
SELECT bukrs hkont buzei dmbtr FROM bseg WHERE ... INTO TABLE @lt.
" proposed (T3 — confirm intent + ledger before applying)
SELECT rbukrs racct docln dmbtr FROM acdoca WHERE ... AND rldnr = '0L' INTO TABLE @lt.
```

## Per-object overrides
Catalog (`scripts/catalog.py <OBJECT>`) carries the field-rename map in `fix_pattern`. Use it.
