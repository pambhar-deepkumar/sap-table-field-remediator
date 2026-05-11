# Tests

> **Status:** scaffolding only. Harness implementation begins Phase 2.

## Intent

Pytest-based evaluation harness. Each test case loads an ABAP snippet, runs the skill, and scores the output against an expected markdown report.

## Layout (planned)

```
tests/
├── conftest.py             # pytest fixtures
├── test_cases/             # input ABAP + expected output pairs
│   ├── 001-obsolete-table-with-cds.abap
│   ├── 001-obsolete-table-with-cds.expected.md
│   └── ...
├── test_skill.py           # the harness
└── README.md               # this file
```

## Rule

Test case expected outputs are the source of truth. **Never edit `*.expected.md` to make a failing test pass — fix the skill instead.** (See `CLAUDE.md`.)
