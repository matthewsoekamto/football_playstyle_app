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
pip install -r requirements-dev.txt            # dev deps (pytest)
```

## Architecture (5-Module Pipeline)

```
app.py  (Streamlit orchestration — no ML/cleaning logic)
  ├── charts.py      (pure Plotly figure builders)
  ├── features.py    (filtering, percentiles, display formatting)
  └── model_engine.py (KMeans clustering, archetype labeling)
        └── data_loader.py  (CSV load, column normalization, per-90 rates)
              └── data/players_data_light-2025_2026.csv
```

Dependency direction is strictly one-way. No module imports from `app.py`. `charts.py` and `features.py` are importable without Streamlit runtime.

Data flow on cold cache: `CSV → data_loader → model_engine.group_players → app.load_app_data (adds percentiles + unique labels) → features.filter_dataframe → render sections`. Three `@st.cache_data` layers (CSV read, clustering, full load) keyed on filepath — CSV replacement without restart serves stale data.

## Key Design Points

- **Two independent KMeans models** — outfield (6 features, k=5) and GK (4 features, k=2). Kept separate because GK and outfield stat distributions are incomparable. The `cluster_id` values from each model are not meaningful across groups; the human-readable `playstyle_cluster` label is what's used downstream.
- **Archetype labeling** — cluster centroids are matched to hand-authored archetype vectors (`OUTFIELD_ARCHETYPES`, `GK_ARCHETYPES`) by greedy nearest-neighbor with de-duplication (`_assign_labels_from_archetypes`). Known issue: the matching `StandardScaler` is fit on only the centroids (5 or 2 points), not the full player distribution. This is tracked as ML-01.
- **Playstyle labels** — currently 5 outfield + 2 GK archetypes. An Option C plan exists to expand to 8 outfield archetypes. The archetype-matching distance function has the scaler-fragility problem above.
- **`primary_position`** — derived as the first token of comma-separated `Pos` column (e.g., `"MF,FW"` → `"MF"`). Per `DECISIONS.md` ADR-003, this is a deliberate simplification. 620 players in the dataset have multi-position entries (most common: `MF,FW` at 217).
- **Per-90 normalization** — all count stats used in clustering are divided by the `90s` column. Percentage-type stats (`save%`) are used raw. Zero-minutes guard: `90s.replace(0, pd.NA)` → `.fillna(0)`.
- **State management** — zero `st.session_state`. Streamlit's rerun model handles all interactivity.

## Known Traps

- `get_cluster_profiles` takes `playstyle_col="playstyle_cluster"` by default, but `app.py` calls it with `playstyle_col="Playstyle"` (the renamed column). Don't "simplify" by removing the parameter.
- `primary_position` is derived in two places (`data_loader.load_and_clean_data` and defensively in `model_engine.group_players`) — both are intentional for different call paths.
- `OUTFIELD_FEATURES` / `GK_FEATURES` (clustering input) and `EXPLORER_OUTFIELD_FEATURES` / `EXPLORER_GK_FEATURES` (radar display) are separate constants that currently match. They are allowed to diverge — don't merge them.
- `fetch_possession_stats.py` is not dead code. It's a deliberately disconnected, manually-run FBref scraper. Don't delete it or wire it into the live app.
- 152 duplicate player names exist in the dataset (mid-season transfers). `add_unique_player_labels` appends squad names only for duplicates. This is correct, not a data quality bug.
- `filter_dataframe` has an unused `search_query` parameter (STYLE-01) — not a bug to fix as a drive-by, it's tracked separately.

## Dataset

`data/players_data_light-2025_2026.csv` — 2,839 rows × 53 columns, Big 5 European leagues (2025/26). After Min≥270 filter: 2,183 rows, ~155 GK, ~2,028 outfield (GK count drops from 194 to 155 because GKs tend to accrue fewer minutes than outfield players). FBref export shape with comma-flattened multi-index headers. GK-only stats (Saves, Save%, GA, CS, etc.) are empty for outfield rows.

## Project Docs Reference

`docs/` is the authoritative documentation set. Key docs in order of importance:

- **PROJECT_CONSTITUTION.md** — highest authority, rules all agents must follow
- **ARCHITECTURE.md** — how the system is put together (read before any code change)
- **DECISIONS.md** — ADR log for every deliberate tradeoff
- **ML_GUIDELINES.md** — clustering/feature engineering standards
- **STYLE_GUIDE.md** — Python coding conventions (type hints, naming, forbidden patterns)
- **STREAMLIT_GUIDELINES.md** — UI conventions (layout, chart template, empty states)
- **TESTING_GUIDE.md** — test expectations per module
- **TASK_BACKLOG.md** — tracked tech debt items (ML-01, SEC-01, STYLE-01, etc.)
- **OPTION_C_PLAN.md** — proposed refactoring to 8 archetypes (not yet implemented)

The CONVENTION: `PROJECT_CONSTITUTION.md > everything else in /docs > code > your best guess`. If a doc and code disagree, that's a bug in whichever is stale — fix the doc in the same change as the code.

## Changelog (Session Chronicle)

This section accumulates findings, corrections, and clues from each session so the next session catches up without rework. Newest entries at top. Remove entries when the issue is fully resolved and no longer relevant context.

### 2026-07-20 — Initial review of CLAUDE.md accuracy
- **Corrected:** `217 multi-position entries` → `620` (217 was only the `MF,FW` subset).
- **Corrected:** `~194 GK after Min≥270` → `~155 GK` (194 was the pre-filter count; GKs tend to log fewer minutes).
- **Confirmed:** All architecture, dependency, and design claims are accurate. One minor awareness point: the "152 duplicate names" count is `duplicated().sum()` (rows after first), covering 151 unique names — one player (Nicolás González) appears 3× across 3 clubs.
- **Next items (known but unaddressed):** ML-01 (scaler fit on centroids only), STYLE-01 (unused search_query param), Option C plan (8 archetypes).

## External Dependencies

Runtime: `streamlit>=1.28.0`, `pandas>=2.0.0`, `scikit-learn>=1.3.0`, `plotly>=5.18.0`. No lockfile. `fetch_possession_stats.py` has its own dep footprint (`requests`, `beautifulsoup4`, `lxml`) intentionally absent from `requirements.txt`.
