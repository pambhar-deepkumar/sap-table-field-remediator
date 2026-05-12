# Artifacts

Per-epic work outputs. This folder mirrors the [GitHub Project board](https://github.com/users/pambhar-deepkumar/projects/4) so every ticket has a home for its files. Not the same as graded submissions — those bundle artifacts from one or more epics when a phase ends.

## Layout

```
artifacts/
├── README.md                         (this file)
├── epic-1-foundation/                ← currently expanded
│   ├── 1.1-scope/
│   ├── 1.2-domain-research/
│   ├── 1.3-tooling-landscape/
│   ├── 1.4-test-taxonomy/
│   └── 1.5-input-acquisition/
├── epic-2-knowledge-base/            ← empty until expanded
├── epic-3-detection/
├── epic-4-recommendation/
├── epic-5-testing-eval/
└── epic-6-demos-docs/
```

Only Epic 1's child folders exist today. Epics 2–6 stay empty placeholders until we expand them — see _Filling in the rest_ below.

## How tickets, folders and PRs fit together

```
┌─────────────────────────────────────────────────────────┐
│                  GitHub Project #4                      │
│                                                         │
│   #2 Umbrella ──sub-issues──▶ #8 #9 #10 #11 #12         │
│   (Epic 1 — Foundation)       (1.1 … 1.5)               │
└────────────────────────────────────┬────────────────────┘
                                     │  pick a child issue
                                     ▼
                       artifacts/epic-1-foundation/
                              1.4-test-taxonomy/
                                     │
                                     │  open PR  ·  "Closes #11"
                                     ▼
                              child issue closes
                                     │
                                     │  when all children closed
                                     ▼
                               umbrella closes
```

## How to use it

1. Open the [board](https://github.com/users/pambhar-deepkumar/projects/4) and find your assigned issue.
2. Branch off `main`, work inside the matching `artifacts/epic-N-…/N.M-…/` folder.
3. Open a PR and write `Closes #<issue-number>` in the description. The issue closes when the PR merges.
4. Drop anything that supports the deliverable in the same folder — markdown, code, data, screenshots.

## What kinds of files belong here

- **Markdown** — write-ups, designs, notes.
- **Code** (`.py`, etc.) — scripts, parsers, harnesses.
- **Data** (`.csv`, `.json`, `.yaml`, `.abap`) — catalog extracts, fixtures, samples.
- **Images** (`.png`, `.svg`) — diagrams, charts.
- **Large binaries** (video, big PDFs) — link externally; don't commit.

No fixed filenames — name things sensibly. Folder = the contract, files inside = your call.

## Filling in the rest

Epics 2–6 are intentionally empty for now. Per the project plan's _Meta-phase C_ ritual: when an epic starts, we break it into child issues on the board **and** scaffold its `N.M-…/` sub-folders here. We don't pre-detail epics we haven't reached.
