# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the app
streamlit run app.py

# Run clustering or data-loading standalone (validates pipeline)
python model_engine.py
python data_loader.py

# Run tests
python -m pytest tests/ -v                    # all tests
python -m pytest tests/test_model_engine.py -v # single file
python -m pytest tests/ -k "determinism" -v   # specific test

# Install
pip install -r requirements.txt               # runtime deps
pip install -r requirements-dev.txt            # dev deps (pytest, ruff)
```

## Architecture (5-Module Pipeline)

```
app.py  (Streamlit orchestration — no ML/cleaning logic)
  ├─ charts.py      (pure Plotly figure builders)
  ├─ features.py    (filtering, percentiles, display formatting)
  └─ model_engine.py (KMeans clustering, archetype labeling)
        └─ data_loader.py  (CSV load, column normalization, per-90 rates)
              └─ data/players_data_light-2025_2026.csv
```

Dependency direction is strictly one-way. No module imports from `app.py`. `charts.py` and `features.py` are importable without Streamlit runtime.

Data flow on cold cache: `CSV → data_loader → model_engine.group_players → app.load_app_data (adds percentiles + unique labels) → features.filter_dataframe → render sections`. Three `@st.cache_data` layers (CSV read, clustering, full load) keyed on filepath — CSV replacement without restart serves stale data.

## Key Design Points

- **Two independent KMeans models** — outfield (6 features, k=8) and GK (4 features, k=2). Kept separate because GK and outfield stat distributions are incomparable. The `cluster_id` values from each model are not meaningful across groups; the human-readable `playstyle_cluster` label is what's used downstream.
- **Archetype labeling** — cluster centroids are matched to hand-authored archetype vectors (`OUTFIELD_ARCHETYPES`, `GK_ARCHETYPES`) by non-greedy nearest-neighbor with a distance threshold fallback (`_assign_labels_from_archetypes`). The matching `StandardScaler` reuses the player-level scalers from `group_players` (fixed ML-01). Multiple clusters can share a label if they're all closest to the same archetype. A cluster whose best match exceeds the 3.5-unit threshold gets "Mixed Profile".
- **Playstyle labels** — currently 8 outfield + 2 GK archetypes (Option C implemented). The 8 outfield archetypes are: Elite Finishers, Advanced Attackers, Wide Creators, Deep Creators, Direct Attackers, Ball-Winning Anchors, Defensive Anchors, Utility / Depth Players.
- **`primary_position`** — derived as the first token of comma-separated `Pos` column (e.g., `"MF,FW"` → `"MF"`). Per `DECISIONS.md` ADR-003, this is a deliberate simplification. 620 players in the dataset have multi-position entries (most common: `MF,FW` at 217).
- **Per-90 normalization** — all count stats used in clustering are divided by the `90s` column. Percentage-type stats (`save%`) are used raw. Zero-minutes guard: `90s.replace(0, pd.NA)` → `.fillna(0)`.
- **State management** — zero `st.session_state`. Streamlit's rerun model handles all interactivity.

## Known Traps

- `get_cluster_profiles` takes `playstyle_col="playstyle_cluster"` by default, but `app.py` calls it with `playstyle_col="Playstyle"` (the renamed column). Don't "simplify" by removing the parameter.
- `primary_position` is derived in two places (`data_loader.load_and_clean_data` and defensively in `model_engine.group_players`) — both are intentional for different call paths.
- `OUTFIELD_FEATURES` / `GK_FEATURES` (clustering input) and `EXPLORER_OUTFIELD_FEATURES` / `EXPLORER_GK_FEATURES` (radar display) are separate constants that currently match. They are allowed to diverge — don't merge them.
- 152 duplicate player names exist in the dataset (mid-season transfers). `add_unique_player_labels` appends squad names only for duplicates. This is correct, not a data quality bug.
- `filter_dataframe` has an unused `search_query` parameter (STYLE-01) — not a bug to fix as a drive-by, it's tracked separately.

## Dataset

`data/players_data_light-2025_2026.csv` — 2,839 rows × 53 columns, Big 5 European leagues (2025/26). After Min≥270 filter: 2,183 rows, ~155 GK, ~2,028 outfield (GK count drops from 194 to 155 because GKs tend to accrue fewer minutes than outfield players). FBref export shape with comma-flattened multi-index headers. GK-only stats (Saves, Save%, GA, CS, etc.) are empty for outfield rows.

## Mandatory Pre-Read (per DEVELOPMENT_WORKFLOW.md)

Before ANY code change, read in order:
1. **PROJECT_CONSTITUTION.md** — highest authority
2. **AI_DEVELOPER_RULEBOOK.md** — operating rules for AI agents
3. **ARCHITECTURE.md** — how the system is put together
4. **DEVELOPMENT_WORKFLOW.md** — mandatory SOP (reading, planning, review, completion)

Then check **DECISIONS.md** (ADRs) and **TASK_BACKLOG.md** (tracked items) before assuming something is a bug.

## Docs Directory

All docs live flat in `docs/` (16 .md files). The docs/README.md describes an aspirational subdirectory layout that hasn't been applied yet — don't rely on those subdirectory paths.

Key docs in order of importance:
- **PROJECT_CONSTITUTION.md** — highest authority, rules all agents must follow
- **ARCHITECTURE.md** — how the system is put together (read before any code change)
- **DECISIONS.md** — ADR log for every deliberate tradeoff
- **ML_GUIDELINES.md** — clustering/feature engineering standards
- **STYLE_GUIDE.md** — Python coding conventions (type hints, naming, forbidden patterns)
- **STREAMLIT_GUIDELINES.md** — UI conventions (layout, chart template, empty states)
- **DEVELOPMENT_WORKFLOW.md** — mandatory SOP (reading, planning, testing, completion)
- **AI_DEVELOPER_RULEBOOK.md** — operating rules for AI agents
- **CODE_REVIEW_CHECKLIST.md** — checklist to run before/after every change
- **TESTING_GUIDE.md** — test expectations per module
- **TASK_BACKLOG.md** — tracked tech debt items (ML-01, SEC-01, STYLE-01, etc.)

The CONVENTION: `PROJECT_CONSTITUTION.md > everything else in /docs > code > your best guess`. If a doc and code disagree, that's a bug in whichever is stale — fix the doc in the same change as the code.

## Changelog (Session Chronicle)

This section accumulates findings, corrections, and clues from each session so the next session catches up without rework. Newest entries at top. Remove entries when the issue is fully resolved and no longer relevant context.

### 2026-07-26 — CI-01, ML-03, DEP-01 implemented
- **CI-01:** Created `.github/workflows/ci.yml` running `ruff check .` and `pytest tests/ -v` on every push/PR to main. Added `ruff>=0.4.0` to `requirements-dev.txt`.
- **ML-03:** Implemented `joblib` model persistence for `StandardScaler` + `KMeans` with metadata JSON (dataset SHA256, row count, fit timestamp, library versions). Added `_get_or_fit_model` with `@st.cache_resource`, `_save_model_artifacts`, `_load_model_artifacts`, `_compute_dataset_hash`, `_apply_loaded_model`. CLI `python model_engine.py --persist` for explicit fit+save. Added persistence tests in `test_model_engine.py::TestModelPersistence`.
- **DEP-01:** Added upper bounds to `requirements.txt` (e.g., `streamlit>=1.28.0,<2.0.0`). Generated `requirements.lock` via `pip freeze`. Added `models/` to `.gitignore`.
- **Docs updated:** `TASK_BACKLOG.md` (CI-01, ML-03, DEP-01 marked RESOLVED), `ML_GUIDELINES.md §11` (persistence docs), `ARCHITECTURE.md` (models/ structure, caching section), `README.md` (CI badge, model persistence section, updated commands).

### 2026-07-24 — ML-04 ported from worktree to main branch
- **ML-04:** evaluate_clustering() function, silhouette_score/davies_bouldin_score imports, evaluate parameter on group_players, and logging-based __main__ block. Originally implemented inside the Phase 4C worktree by mistake; re-applied to main.

### 2026-07-21 — Phase 5: ML-02 resolved — position-scoped percentiles
- **Implemented:** ML-02 — `add_position_percentiles` now initialises each percentile column as NaN and only computes values for position groups where the stat is relevant per `POSITION_COMPARE_STATS`. Irrelevant stat-position pairs (e.g. `saves_percentile` for forwards) stay NaN instead of a misleading tied-at-zero 50th-percentile rank.
- **Changed:** `features.py` — `add_position_percentiles` loops over positions and checks `get_compare_stats_for_position` before computing, instead of blindly ranking all stats for all positions.
- **Tests added:** 4 new tests in `TestAddPositionPercentiles`: `test_irrelevant_stat_is_nan`, `test_relevant_stat_has_rank`, `test_saves_only_for_gk`, `test_unknown_stat_skipped`. 38/38 tests passing.
- **Impact:** Same-position percentile radars (H2H, Playstyle Explorer) are unaffected. Cross-position comparisons (already warned-about in the UI) now correctly show NaN for irrelevant stat-position pairs. No behavioral change for clustering.
- **Docs updated:** `ML_GUIDELINES.md §6` (marks ML-02 resolved), `TASK_BACKLOG.md` (status → RESOLVED), `TESTING_GUIDE.md` (tracks tests), CLAUDE.md changelog.

### 2026-07-21 — Phase 4C: Option C implemented (8 outfield archetypes)
- **Implemented:** Option C refactoring per `OPTION_C_PLAN.md` and `TASK_BACKLOG.md`.
- **Changed:** `OUTFIELD_ARCHETYPES` expanded from 5 to 8 entries (Elite Finishers, Advanced Attackers, Wide Creators, Deep Creators, Direct Attackers, Ball-Winning Anchors, Defensive Anchors, Utility / Depth Players).
- **Changed:** `KMeans(n_clusters=5)` → `KMeans(n_clusters=8)` for outfield players.
- **Changed:** `_assign_labels_from_archetypes` replaced greedy "no repeats" constraint with non-greedy nearest-neighbour + distance threshold (3.5) → "Mixed Profile" fallback.
- **Fixed (ML-01):** `_assign_labels_from_archetypes` now accepts the player-level `scaler_out`/`scaler_gk` from `group_players`, anchoring archetype-matching distances to the real data distribution instead of fitting a scaler on just the centroid points.
- **Fixed (ML-01 nuance):** The threshold fallback prevented GK clusters from being forced into "Sweeper-Keepers" — both GK centroids are genuinely closer to "Shot-Stoppers" in this season's data. The old greedy code forced the second label.
- **Added:** UI info note in `render_playstyle_explorer` about missing dribbling data.
- **Tests updated:** 2 new tests (`test_labels_use_raw_archetype_names`, `test_shared_labels_under_non_greedy`) replace the old `test_each_cluster_has_unique_label`. Fixture expanded to 12 rows (2 new outfield players) to support K=8. Expected row count in data loader test updated to 11. 32/32 tests passing.
- **Next items (still unaddressed):** STYLE-01 (unused search_query param), ML-04 (evaluation metrics), DEP-01 (gitignore), CI-01 (CI pipeline), ML-02 (scope percentiles). Option C plan is now complete — remove from "next items".

### 2026-07-20 — Initial review of CLAUDE.md accuracy
- **Corrected:** `217 multi-position entries` → `620` (217 was only the `MF,FW` subset).
- **Corrected:** `~194 GK after Min≥270` → `~155 GK` (194 was the pre-filter count; GKs tend to log fewer minutes).
- **Confirmed:** All architecture, dependency, and design claims are accurate. One minor awareness point: the "152 duplicate names" count is `duplicated().sum()` (rows after first), covering 151 unique names — one player (Nicolás González) appears 3× across 3 clubs.