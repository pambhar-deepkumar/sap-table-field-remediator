#!/usr/bin/env python3
"""abaplint wrapper — the syntax sensor (course w04, computational).

abaplint checks *generic* ABAP syntax ("is this parseable ABAP"), our offline
proxy for "would it activate". It does NOT know the SAP DDIC, so it cannot judge
S/4 migration correctness — that is check_residual.py's job. Here we only want the
parse/obsolete-statement signal.

Wraps a snippet into a minimal report object (`zdummy.prog.abap`) in a temp dir
with abaplint.json, runs `npx @abaplint/cli`, and reports issues.

Graceful degradation: if abaplint/npx is unavailable (offline), exits 2 with a
clear message so the harness falls back to check_residual only.

Usage:
  python3 lint_snippet.py <file.abap>
  python3 lint_snippet.py -            # stdin
  python3 lint_snippet.py <file> --json
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "abaplint.json")

_HEADERS = ("REPORT", "PROGRAM", "CLASS", "FUNCTION", "INTERFACE", "MODULE")


def wrap(snippet: str) -> str:
    head = snippet.lstrip().upper()
    if head.startswith(_HEADERS):
        return snippet
    return "REPORT zdummy.\n\n" + snippet + "\n"


def run(snippet: str) -> dict:
    if shutil.which("npx") is None:
        return {"available": False, "reason": "npx not found", "issues": []}
    workdir = tempfile.mkdtemp(prefix="abaplint_")
    try:
        src = os.path.join(workdir, "src")
        os.makedirs(src)
        with open(os.path.join(src, "zdummy.prog.abap"), "w") as fh:
            fh.write(wrap(snippet))
        shutil.copy(CONFIG, os.path.join(workdir, "abaplint.json"))
        try:
            proc = subprocess.run(
                ["npx", "--yes", "@abaplint/cli", "--format", "json"],
                cwd=workdir, capture_output=True, text=True, timeout=180,
            )
        except subprocess.TimeoutExpired:
            return {"available": False, "reason": "abaplint timed out (offline?)", "issues": []}
        except Exception as e:  # noqa: BLE001
            return {"available": False, "reason": f"abaplint failed: {e}", "issues": []}
        out = (proc.stdout or "").strip()
        try:
            issues = json.loads(out) if out.startswith("[") else []
        except json.JSONDecodeError:
            issues = []
        if not out and proc.returncode != 0 and "npm" in (proc.stderr or "").lower():
            return {"available": False, "reason": "could not fetch @abaplint/cli (offline?)", "issues": []}
        return {"available": True, "issue_count": len(issues), "issues": issues,
                "returncode": proc.returncode}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    as_json = "--json" in sys.argv
    if not args:
        print("usage: lint_snippet.py <file.abap|-> [--json]", file=sys.stderr)
        return 2
    text = sys.stdin.read() if args[0] == "-" else open(args[0]).read()
    res = run(text)
    if as_json:
        print(json.dumps(res, indent=2))
        return 0 if res.get("available") and not res.get("issue_count") else (2 if not res.get("available") else 1)
    if not res.get("available"):
        print(f"ABAPLINT UNAVAILABLE: {res['reason']} (harness falls back to check_residual)")
        return 2
    if res.get("issue_count"):
        print(f"ABAPLINT: {res['issue_count']} issue(s)")
        for i in res["issues"][:20]:
            print(f"  {i.get('key','?')}: {i.get('message','')}")
        return 1
    print("ABAPLINT CLEAN: parses as valid ABAP.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
