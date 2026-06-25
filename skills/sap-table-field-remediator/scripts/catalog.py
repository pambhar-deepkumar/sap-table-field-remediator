#!/usr/bin/env python3
"""catalog.py — load the S/4HANA simplification catalog (single source of truth).

The catalog is `simplification-list.yaml` (schema: key `object`; statuses VALID,
CHANGED, RENAMED, ABOLISHED, RESTRUCTURED, DECLUSTERED_SAME_NAME, REDIRECT_BP,
MODERNIZATION_ONLY; plus `world`, `baseline_tier`, `s4_replacement`, `cds_view`).

This REPLACES the old json loaders (key `ecc_table`, status "COMPATIBILITY VIEW"):
that schema KeyErrors on the YAML and silently misses BSEG/MKPF/MSEG (RESTRUCTURED).

Resolution order at runtime (skill reads whatever catalog is in its working dir):
  1. $CATALOG env var, if set
  2. ./ground-truth/simplification-list.yaml   (the eval sandbox layout)
  3. ./simplification-list.yaml
  4. the copy bundled in ../references/simplification-list.yaml (production fallback)

Usage as a CLI:  python3 catalog.py [--path P] [OBJECT]
  - no OBJECT: print a summary; OBJECT: print that entry as JSON.
"""
from __future__ import annotations

import json
import os
import sys

try:
    import yaml
except ImportError:
    sys.stderr.write("ERROR: pyyaml required (pip install pyyaml).\n")
    sys.exit(2)

HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLED = os.path.normpath(os.path.join(HERE, "..", "references", "simplification-list.yaml"))


def find_catalog(explicit: str | None = None) -> str:
    candidates = [
        explicit,
        os.environ.get("CATALOG"),
        os.path.join(os.getcwd(), "ground-truth", "simplification-list.yaml"),
        os.path.join(os.getcwd(), "simplification-list.yaml"),
        BUNDLED,
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    raise FileNotFoundError(
        "No simplification-list.yaml found (looked in $CATALOG, ./ground-truth/, ./, bundled)."
    )


def load(path: str | None = None) -> dict[str, dict]:
    p = find_catalog(path)
    with open(p, "r") as f:
        data = yaml.safe_load(f)
    catalog = data["catalog"]
    return {str(c["object"]).upper(): c for c in catalog}


def main() -> int:
    args = sys.argv[1:]
    path = None
    if "--path" in args:
        i = args.index("--path")
        path = args[i + 1]
        del args[i : i + 2]
    cat = load(path)
    if args:
        obj = args[0].upper()
        entry = cat.get(obj)
        print(json.dumps(entry, indent=2) if entry else f"(not in catalog: {obj})")
    else:
        by_status: dict[str, list[str]] = {}
        for obj, e in sorted(cat.items()):
            by_status.setdefault(e.get("status", "?"), []).append(obj)
        print(f"catalog: {find_catalog(path)}  ({len(cat)} objects)")
        for st in sorted(by_status):
            print(f"  {st:22} {', '.join(by_status[st])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
