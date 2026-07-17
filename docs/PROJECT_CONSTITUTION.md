# PROJECT CONSTITUTION
### Football Playstyle Clustering App

**Status:** Ratified | **Authority Level:** Highest — supersedes all other documents in `/docs`
**Applies to:** Every human contributor and every AI coding agent (Claude Code, Cursor, Continue, Cline, GitHub Copilot, GPT-based agents, etc.)

> If any other document in this repository conflicts with this Constitution, this Constitution wins. If this Constitution conflicts with an explicit, informed instruction from the project owner in a given session, the owner's instruction wins for that session only — it does not amend this document.

---

## 1. What This Project Is

A Streamlit application that ingests season-long player statistics for the "Big 5" European football leagues (Premier League, La Liga, Ligue 1, Serie A, Bundesliga) and uses unsupervised learning (K-Means) to assign every player a human-readable **playstyle** — e.g. "Elite Finishers," "Ball-Winning Anchors," "Shot-Stoppers" — and then lets a user explore, filter, and compare players through that lens.

It is currently a **single-CSV, single-season, single-page** analytics tool (`app.py` orchestrating `data_loader.py` → `model_engine.py` → `features.py` → `charts.py`). It is not yet a multi-season platform, not yet a service with an API, and not yet backed by automated tests. The Constitution exists precisely because the project is small today and ambitious tomorrow — the rules below are what keep growth from turning into entropy.

## 2. Vision

Become the clearest, most trustworthy open-source tool for understanding **how a footballer plays**, not just how many goals they scored — a portfolio-grade demonstration that clean data engineering, honest unsupervised ML, and a well-designed Streamlit UI can be combined without hand-waving.

## 3. Mission (12-Month Horizon)

1. Turn the clustering pipeline into a reproducible, testable, versioned ML component — not a script that happens to work.
2. Expand the data surface (possession, passing, progressive actions — see `fetch_possession_stats.py` as the seed of this) without breaking the existing per-90 feature contract.
3. Keep the Streamlit UI fast and legible as the dataset and feature set grow.
4. Make the codebase safe for AI coding agents to operate on unsupervised, by giving them unambiguous, machine-followable rules (see `AI_DEVELOPER_RULEBOOK.md`).

## 4. Long-Term Goals

- **Multi-season support**: the current loader hardcodes a single filename (`players_data_light-2025_2026.csv`); the long-term architecture must support selecting a season without code changes.
- **Richer feature space**: integrate possession/passing metrics currently only scraped by the orphaned `fetch_possession_stats.py` into the actual clustering pipeline.
- **Model governance**: move from "recompute KMeans on every cold cache" to a versioned, persisted model artifact with a documented retraining policy.
- **Test coverage** as a first-class deliverable, not an afterthought — the project currently has zero automated tests.
- **Portfolio readiness**: the repository itself (docs, tests, CI, structure) should be as much a demonstration of engineering judgment as the app is a demonstration of ML/product judgment.

## 5. Engineering Philosophy

- **Correctness over cleverness.** The archetype-labeling logic in `model_engine._assign_labels_from_archetypes` is a good example of "clever" (distance-matching cluster centroids to hand-authored archetype vectors) that must be held to a "correct" standard — see `ML_GUIDELINES.md` for the specific concern about fitting a `StandardScaler` on only 2–5 centroid points.
- **Small, explainable modules.** The existing five-module split (`data_loader` → `model_engine` → `features` → `charts` → `app`) is the correct shape. New functionality should extend this shape, not collapse it into `app.py`.
- **No silent magic numbers.** `min >= 270`, `n_clusters=5`, `n_clusters=2`, and every value inside `OUTFIELD_ARCHETYPES` / `GK_ARCHETYPES` are currently magic numbers embedded in code. The Constitution does not require removing them immediately, but it forbids adding *new* undocumented magic numbers going forward (see `STYLE_GUIDE.md §Constants`).
- **Fail loud in development, fail soft in production UI.** A Streamlit user should never see a raw Python traceback; a developer running `python model_engine.py` should see the real exception.

## 6. AI Development Philosophy

AI coding agents are treated as **capable but context-blind junior engineers**: fast, tireless, and prone to confidently rewriting things they don't have full context on. Every rule in `AI_DEVELOPER_RULEBOOK.md` exists to compensate for that specific failure mode. The core stance:

- An AI agent's default action is to **read**, not write.
- An AI agent must be able to point to *which* document justified a given change.
- An AI agent must never treat "the code ran without an exception" as equivalent to "the code is correct" — this is a clustering/statistics project; silent numerical wrongness is the primary risk, not crashes.

## 7. Code Quality Philosophy

Readable, typed, tested, small functions that do one thing — the current codebase is already close to this ideal (e.g. `features.py` functions are short and single-purpose) and the bar should not regress as the project grows. See `STYLE_GUIDE.md`.

## 8. ML Philosophy

- Unsupervised clustering results are **descriptive, not authoritative**. A "playstyle" label is a modeling choice, not ground truth about a player. All UI copy and documentation must reflect this framing.
- Reproducibility is non-negotiable: every stochastic step (`KMeans(random_state=42, ...)`) must have a fixed seed, and any new stochastic step must too.
- Feature engineering decisions (per-90 normalization, `fillna(0)`) must be documented at the point of decision, not just in code comments. See `ML_GUIDELINES.md`.

## 9. UI Philosophy

The Streamlit UI should read like a sports analytics product, not a data-science notebook. Every chart needs a title a non-technical fan would understand (the app already does this well — e.g. "Elite Outlier Analysis," "Percentile Footprint"). New UI additions must match this bar.

## 10. Performance Philosophy

Cache expensive, deterministic computation (`@st.cache_data` on `load_and_clean_data`, `get_clustered_data`, `load_app_data` — already correct) and never cache anything that depends on user-specific filter state. See `PERFORMANCE_GUIDE.md`.

## 11. Maintainability Philosophy

Every module has exactly one reason to change. `fetch_possession_stats.py` currently violates the spirit of this by existing in the repo but not participating in the module graph at all (`data_loader.py` never imports it) — it must either be formally adopted into the pipeline or clearly marked as a standalone, optional utility (see `DECISIONS.md`).

## 12. Refactoring Philosophy

Refactor in the smallest slice that proves the point. Never refactor and add a feature in the same change. Never refactor a module you were not asked to touch, even if you notice a real problem in it — flag it in `TASK_BACKLOG.md` instead.

## 13. Security Philosophy

The current attack surface is small (local CSV, no auth, no network calls from the Streamlit app itself) but is not zero: `fetch_possession_stats.py` performs an outbound HTTP request and HTML parse against a third-party site, and any future file-upload feature would introduce untrusted input. See `SECURITY_GUIDE.md`.

---

## 14. Non-Negotiable Engineering Rules

1. Never commit secrets, API keys, or credentials. (None exist today — keep it that way.)
2. Never introduce a second source of truth for a feature list, archetype definition, or column mapping. `FRIENDLY_NAMES`, `POSITION_COMPARE_STATS`, `OUTFIELD_FEATURES`/`GK_FEATURES`, and `OUTFIELD_ARCHETYPES`/`GK_ARCHETYPES` are each defined exactly once today (in `features.py` and `model_engine.py` respectively) — this must not change.
3. Never silently change the meaning of an existing column (e.g. redefining what `_p90` means) without a corresponding entry in `DECISIONS.md`.
4. Never remove the `random_state=42` seeding, or any future seeding, without an explicit, documented reason.
5. Never let `app.py` grow ML logic (`model_engine.py`'s job) or data-cleaning logic (`data_loader.py`'s job). `app.py` is presentation only.
6. Never ship a change to the clustering pipeline without manually inspecting the resulting cluster sizes and archetype assignments — a KMeans run that silently collapses to fewer meaningful clusters must be caught by a human or a test, not shipped.
7. Every new dependency must be added to `requirements.txt` in the same change that introduces the import.

## 15. Definition of Done

A change is **Done** when:
- It runs (`streamlit run app.py` starts with no exceptions, and/or `python data_loader.py` / `python model_engine.py` print `SUCCESS`).
- It respects `STYLE_GUIDE.md`.
- It does not regress any existing UI section (table, Playstyle Explorer, scatter plot, head-to-head).
- Any new function has a docstring and, if it contains non-obvious logic, a comment explaining *why*, not *what*.
- The relevant `/docs` document (`ARCHITECTURE.md`, `DECISIONS.md`, `TASK_BACKLOG.md`, etc.) has been updated in the same change.

## 16. Definition of Production Ready

The project is **Production Ready** when, in addition to Definition of Done for every change:
- An automated test suite exists and passes (`TESTING_GUIDE.md`).
- A CSV load failure or malformed dataset produces a user-facing Streamlit error message, not a stack trace.
- `requirements.txt` pins are reviewed and either pinned exactly or accompanied by a lockfile.
- The clustering pipeline has documented, versioned outputs (even a simple "last trained on / dataset hash" note is sufficient at this stage).
- Basic CI (lint + test on push) is running.

## 17. Definition of Feature Complete (v1 scope)

v1 is **Feature Complete** when the app supports: multi-league filtering, position filtering, squad filtering, playstyle filtering, name search, a sortable player table, a Playstyle Explorer with distribution + radar + representative players, an outlier scatter plot, and a head-to-head comparison. **All of these already exist.** Any feature beyond this list (multi-season, possession stats, model persistence, authentication, etc.) is v2+ and belongs in `TASK_BACKLOG.md`, not bolted onto v1 without a decision record.

## 18. Principles Every AI Agent Must Obey

1. Read `ARCHITECTURE.md` and the file(s) you intend to touch before writing a single line.
2. State your plan and the files you will touch before making large edits.
3. Never invent a column name, API, or library function that isn't verified to exist in this codebase or its dependencies.
4. Never delete functionality to make a bug "go away."
5. Prefer the smallest correct diff.
6. When in doubt, ask or flag in `TASK_BACKLOG.md` — do not guess silently.

---
*This document is reviewed whenever project scope materially changes. Last ratified: this repository snapshot (2025–2026 season data).*
