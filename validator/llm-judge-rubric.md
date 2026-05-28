# LLM-as-judge rubric — remediation quality (semantic sensor)

Used by the evaluation (and Branch B's self-correction loop) to score a remediation
the computational sensors can't fully judge. Per course w04: separate the generator
from the judge; escalate to a semantic sensor only for properties a deterministic
check can't express. Score each finding 0–2; a remediation "passes quality" at ≥ mean 1.5.

Give the judge: the original ECC code, the proposed remediation, the relevant KB
entries, and (when available) the expected-fix key. Ask it to score:

1. **Correctness of mapping (0–2)** — Right replacement table and right field renames
   (`HKONT→RACCT`, `BUZEI→DOCLN`, `BUKRS→RBUKRS`, `MONAT→POPER`)? `RLDNR='0L'` added for
   ACDOCA reads? 0 = wrong, 1 = partial, 2 = complete and correct.
2. **World-A/B precision (0–2)** — Did it treat must-fix (World A) and key-only (World B)
   correctly, and NOT over-flag a working released BAPI or a still-valid table? This is
   the headline metric. 0 = over-flags World B / valid tables, 2 = clean separation.
3. **Honesty & release-dependence (0–2)** — Are release-dependent items (MATNR length,
   VBTYP, FSCM) flagged as needing target-system verification rather than asserted? Is
   "not activation-verified" stated? 0 = overconfident, 2 = appropriately hedged.
4. **Citation (0–2)** — Does each finding cite the triggering table/field and a KB/source
   reference (no uncited claims)? 0 = none, 2 = all cited.
5. **Blocker handling (0–2)** — Are no-clean-replacement cases (S001, RFBLG, PCL*, KNKK)
   marked BLOCKER / manual-redesign rather than given a fake fix? 0 = fabricated fix, 2 = correct.

Output JSON: `{ "scores": {"mapping":n,"precision":n,"honesty":n,"citation":n,"blocker":n},
"mean": x.x, "pass": true|false, "notes": "..." }`.

Penalize "AI-slop": confident-but-wrong CDS names, invented field maps, or rewriting
World-B BAPIs as if ATC forced them.
