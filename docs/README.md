# /docs — Engineering Documentation & Governance

This is the permanent source of truth for the Football Playstyle Clustering App. It was written by reading every Python file, the dataset, and the existing `README.md` in full before any document was drafted — nothing here is generic boilerplate; every claim is traceable to a specific file, function, or data fact in this repository.

**Read `00-constitution/PROJECT_CONSTITUTION.md` first.** It is the highest-authority document; every other document is subordinate to it, and if any two documents ever conflict, the Constitution wins.

**Then read `04-process/DEVELOPMENT_WORKFLOW.md` before starting any task.** It is the mandatory, ordered procedure — reading, planning, implementation, review, testing, documentation, regression prevention, self-review, and completion — that every AI coding agent (and human contributor) must follow for every change, no matter how small.

## Folder Structure

```
docs/
├── README.md                                  ← you are here
├── 00-constitution/
│   └── PROJECT_CONSTITUTION.md                 Highest authority: vision, philosophy, non-negotiable rules,
│                                                Definitions of Done / Production Ready / Feature Complete
├── 01-product/
│   └── PROJECT_SPEC.md                         What the product is: purpose, users, current/future
│                                                capabilities, constraints, success criteria
├── 02-architecture/
│   ├── ARCHITECTURE.md                         Folder/file map, module dependency graph, data flow,
│   │                                            ML pipeline, user flow, caching (with Mermaid diagrams)
│   └── DECISIONS.md                            ADR-style log of real design decisions found in the code
├── 03-engineering-standards/
│   ├── STYLE_GUIDE.md                          Python coding standards for this repo specifically
│   ├── ML_GUIDELINES.md                        Feature engineering, clustering, evaluation, reproducibility
│   ├── STREAMLIT_GUIDELINES.md                 UI/UX handbook for app.py
│   ├── PERFORMANCE_GUIDE.md                    Caching, pandas/numpy, rerun optimization
│   ├── SECURITY_GUIDE.md                       Input validation, secrets, dependency & file-handling rules
│   └── TESTING_GUIDE.md                        Concrete test plan (repo currently has zero tests)
├── 04-process/
│   ├── AI_DEVELOPER_RULEBOOK.md                Explicit operating rules for AI coding agents
│   ├── CODE_REVIEW_CHECKLIST.md                Checklist to run before/after every change
│   └── DEVELOPMENT_WORKFLOW.md                 Mandatory SOP: how every task begins, is planned,
│                                                implemented, reviewed, tested, documented, and closed out
└── 05-roadmap/
    ├── TASK_BACKLOG.md                          Prioritized, effort-estimated backlog (Critical → Future)
    └── PROJECT_IMPROVEMENT_REPORT.md            Scored engineering review + ROI-ranked recommendations
```

## Why this order

The numbering reflects authority and reading order, not alphabetical convenience: **constitution → product intent → architecture → standards → process → roadmap.** An AI coding agent (or new human contributor) making its first change should read in roughly this order, though `AI_DEVELOPER_RULEBOOK.md` in `04-process/` is the fastest path to "what do I do right now" once the constitution has been read once.

## Keeping this set alive

Per `PROJECT_CONSTITUTION.md`'s Definition of Done, **any change to the code that changes architecture, a documented decision, or a standard must update the corresponding document in the same change.** A `/docs` set that drifts from the code it describes is worse than no `/docs` set at all — treat documentation debt with the same seriousness as code debt.
