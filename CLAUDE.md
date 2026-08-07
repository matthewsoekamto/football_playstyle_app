# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the app
streamlit run app.py

# Run clustering or data-loading standalone (validates pipeline)
python model_engine.py
python data_loader.py

# Model persistence: fit + save + evaluate
python model_engine.py --persist              # fit + save + log eval metrics
python model_engine.py --evaluate             # fit + eval (no save)

# Run tests
python -m pytest tests/ -v                    # all tests
python -m pytest tests/test_model_engine.py -v # single file
python -m pytest tests/ -k "determinism" -v   # specific test

# v2 data pipeline (WC 2022 rebuild)
python scripts/download_statsbomb.py          # fetch StatsBomb Open Data into data/statsbomb/
python statsbomb_parser.py                    # parse raw events -> 21 event-derived features (P3)
python build_master_dataset.py                # FBref + StatsBomb -> data/wc2022_players_master.csv

# Lint
ruff check .

# Install
pip install -r requirements.txt               # runtime deps
pip install -r requirements-dev.txt            # dev deps (pytest, ruff)
```

## Architecture (5-Module Pipeline + Tests + Artifacts)

```
app.py  (Streamlit orchestration — no ML/cleaning logic)
  ├─ charts.py      (pure Plotly figure builders)
  ├─ features.py    (filtering, percentiles, display formatting)
  └─ model_engine.py (KMeans clustering, archetype labeling, persistence)
        └─ data_loader.py  (CSV load, column normalization, per-90 rates)
              └─ data/players_data_light-2025_2026.csv (v1 legacy, provisional)
tests/              (pytest + conftest.py fixture, one file per module)
.github/workflows/  (CI: ruff check + pytest on push/PR to main)
models/             (gitignored: persisted scalers, KMeans, metadata.json)

v2 data pipeline (WC 2022 rebuild, in parallel — not yet wired into app.py)
statsbomb_parser.py   (pure parser: StatsBomb events -> 21 event-derived features, P3)
scripts/download_statsbomb.py  (fetch raw StatsBomb Open Data into data/statsbomb/, gitignored)
build_master_dataset.py  (FBref CSVs + StatsBomb events -> data/wc2022_players_master.csv)
tests/test_statsbomb_parser.py  (35 parser tests, incl. locked P3 contract)
data/statsbomb/       (gitignored raw JSON: events/, lineups/, matches/)
```

Dependency direction is strictly one-way. No module imports from `app.py`. `charts.py` and `features.py` are importable without Streamlit runtime.

Data flow on cold cache: `CSV → data_loader → model_engine.group_players → app.load_app_data (adds percentiles + unique labels) → features.filter_dataframe → render sections`. Three caching layers:
- `data_loader.load_and_clean_data` — `@st.cache_data` keyed on filepath
- `model_engine.get_clustered_data` — `@st.cache_data` keyed on filepath
- `model_engine._get_or_fit_model` — `@st.cache_resource` (loads persisted joblib artifacts)

CSV replacement without restart serves stale data (filepath key doesn't change). Model persistence artifacts are validated by SHA256 hash of the CSV — changing the CSV triggers automatic refit.

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
- `int_p90` is computed twice (once via `OUTFIELD_RATE_STATS`, once via `GK_RATE_STATS`, both include `"int"`) inside `data_loader._add_per90_rates`. Each rate-stat list needs to be independently complete for its consumer.
- `evaluate_clustering` expects pre-scaled numpy arrays, not raw DataFrames — it's called after `StandardScaler` in `group_players`.
- `app.py` does not use `if __name__ == "__main__":` — this is idiomatic for Streamlit (it re-executes the script directly). Don't "fix" this.
- The GK-vs-outfield comparison warning in `render_h2h_section` has two `elif` branches (GK→outfield and outfield→GK). Both must be preserved.

## Dataset

Two datasets coexist, one per app version:

**v1 legacy** — `data/players_data_light-2025_2026.csv`: 2,839 rows × 53 columns, Big 5 European leagues (2025/26). After Min≥270 filter: 2,183 rows, ~155 GK, ~2,028 outfield (GK count drops from 194 to 155 because GKs tend to accrue fewer minutes than outfield players). FBref export shape with comma-flattened multi-index headers. GK-only stats (Saves, Save%, GA, CS, etc.) are empty for outfield rows.

**v2 rebuild** — `data/wc2022_players_master.csv`: 217 rows × 167 columns (146 pre-P3 + 21 P3 event-derived), FIFA World Cup 2022 (StatsBomb competition 43 / season 106). Built by `build_master_dataset.py` from FBref CSVs + StatsBomb events; 217 eligible players after Min≥270 filter. **P3 complete** — 21 locked event-derived features (pressures, recoveries, touches by zone, GK metrics, etc.) merged in at commit `7ccb424`. Raw StatsBomb Open Data lives in `data/statsbomb/` (gitignored; reproducible via `scripts/download_statsbomb.py`).

Source FBref CSVs (`wc2022_standard.csv`, `wc2022_shooting.csv`, `wc2022_miscellaneous.csv`, `wc2022_gk.csv`) remain in `data/` as inputs to the v2 build.

## Mandatory Pre-Read (per DEVELOPMENT_WORKFLOW.md)

Before ANY code change, read in order:
1. **PROJECT_CONSTITUTION.md** — highest authority
2. **AI_DEVELOPER_RULEBOOK.md** — operating rules for AI agents
3. **ARCHITECTURE.md** — how the system is put together
4. **DEVELOPMENT_WORKFLOW.md** — mandatory SOP (reading, planning, review, completion)

Then check **DECISIONS.md** (ADRs) and **TASK_BACKLOG.md** (tracked items) before assuming something is a bug.

## Docs Directory

All docs live in `docs/` organized by authority and domain:

```
docs/
├── README.md                                  ← entry point
├── 00-constitution/
│   └── PROJECT_CONSTITUTION.md                 Highest authority: vision, rules, DoD
├── 01-product/
│   └── PROJECT_SPEC.md                         Product purpose, users, capabilities
├── 02-architecture/
│   ├── ARCHITECTURE.md                         System structure, data flow, ML pipeline
│   └── DECISIONS.md                            ADR log of real design decisions
├── 03-engineering-standards/
│   ├── STYLE_GUIDE.md                          Python coding standards for this repo
│   ├── ML_GUIDELINES.md                        Feature engineering, clustering, evaluation
│   ├── STREAMLIT_GUIDELINES.md                 UI/UX handbook for app.py
│   ├── PERFORMANCE_GUIDE.md                    Caching, pandas/numpy, rerun optimization
│   └── SECURITY_GUIDE.md                       Input validation, secrets, deps
├── 04-process/
│   ├── AI_DEVELOPER_RULEBOOK.md                Operating rules for AI coding agents
│   ├── CODE_REVIEW_CHECKLIST.md                Checklist before/after every change
│   ├── DEVELOPMENT_WORKFLOW.md                 Mandatory SOP (read before any task)
│   └── TESTING_GUIDE.md                        Concrete test plan per module
└── 05-roadmap/
    ├── TASK_BACKLOG.md                          Prioritized, estimated backlog
    └── PROJECT_IMPROVEMENT_REPORT.md            Scored review + ROI recommendations
```

Key docs in reading order:
1. **00-constitution/PROJECT_CONSTITUTION.md** — highest authority
2. **04-process/DEVELOPMENT_WORKFLOW.md** — mandatory SOP
3. **02-architecture/ARCHITECTURE.md** — system structure
4. **02-architecture/DECISIONS.md** — ADRs
5. **03-engineering-standards/ML_GUIDELINES.md** — ML standards
6. **03-engineering-standards/STYLE_GUIDE.md** — Python conventions
7. **03-engineering-standards/STREAMLIT_GUIDELINES.md** — UI conventions
8. **04-process/AI_DEVELOPER_RULEBOOK.md** — AI agent rules
9. **04-process/CODE_REVIEW_CHECKLIST.md** — review checklist
10. **04-process/TESTING_GUIDE.md** — test expectations
11. **05-roadmap/TASK_BACKLOG.md** — tracked items

The CONVENTION: `00-constitution/PROJECT_CONSTITUTION.md > everything else in /docs > code > your best guess`. If a doc and code disagree, that's a bug in whichever is stale — fix the doc in the same change as the code.

## Changelog (Session Chronicle)

This section accumulates findings, corrections, and clues from each session so the next session catches up without rework. Newest entries at top. Remove entries when the issue is fully resolved and no longer relevant context.

### 2026-08-07 — P3 complete: StatsBomb event parser (commit 7ccb424)
- **P3 RESOLVED:** 21 locked event-derived features from StatsBomb Open Data, merged into `data/wc2022_players_master.csv` (217 rows × 167 cols). Contract locked in `tests/test_statsbomb_parser.py::TestContract`. See `PROJECT_STATE.md` v2 roadmap.
- **New modules:** `statsbomb_parser.py` (pure parser, no FBref import), `scripts/download_statsbomb.py` (raw fetch → `data/statsbomb/`, gitignored), `build_master_dataset.py` (FBref+StatsBomb merge; `merge_statsbomb_event_features` now starts with `reset_index(drop=True)` — positional-safety fix for a latent IndexError).
- **Only 3 authorized heuristics:** `goals_prevented_p90` (sums linked-shot `statsbomb_xg`), `reflex_saves_p90` (GK "Shot Saved" from ≤5.5 yd), `cross_accuracy_pct` (completed/attempted cross ratio). Everything else counted directly from event schema.
- **GK gating:** 7 GK-scoped features zero-filled for non-GKs in the merge (`pos_n == "GK"`).
- **Docs updated:** CLAUDE.md (this entry), `ARCHITECTURE.md` (repo tree, purpose table, new §11), `TASK_BACKLOG.md`, `PROJECT_STATE.md` (P1–P5 roadmap status).

### 2026-07-28 — CLAUDE.md audit: commands, architecture, traps, dataset status
- **Commands:** Added `ruff check .`, `model_engine.py --persist`/`--evaluate`
- **Architecture:** Added tests/, CI, models/ to tree. Documented all 3 cache layers + SHA256 invalidation
- **Known traps:** Added `int_p90` double-compute, `evaluate_clustering` numpy req, Streamlit no-`__main__`, both GK warning branches
- **Dataset:** Marked as **provisional** (not yet final), noted `wc2022_*.csv` scratch files

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