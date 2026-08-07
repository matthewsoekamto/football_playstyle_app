# TASK BACKLOG

Authority: subordinate to `PROJECT_CONSTITUTION.md`. Every item below was identified by direct inspection of the current repository â€” none are generic placeholder tasks. IDs are stable references used elsewhere in `/docs` (e.g. `ML_GUIDELINES.md` refers to `ML-01`).

---

## CRITICAL

### SEC-01: Handle CSV load failure gracefully
- **Priority:** Critical | **Difficulty:** Low | **Impact:** High | **Effort:** ~1 hour
- **Dependencies:** None
- **Files affected:** `app.py` (`load_app_data` call site), possibly `data_loader.py`
- **Acceptance criteria:** A missing or malformed `players_data_light-2025_2026.csv` produces a clear `st.error(...)` message and `st.stop()`, never a raw traceback in the deployed app.
- **Expected outcome:** The app degrades safely instead of crashing for end users. See `STYLE_GUIDE.md Â§9`, `STREAMLIT_GUIDELINES.md Â§12`, `SECURITY_GUIDE.md Â§2`.

### TEST-01: Stand up a `pytest` suite with at least the determinism test
- **Priority:** Critical | **Difficulty:** Medium | **Impact:** High | **Effort:** ~1 day for initial suite
- **Dependencies:** None
- **Files affected:** New `tests/` directory, new `requirements-dev.txt`
- **Acceptance criteria:** At minimum, a test proving `group_players` produces identical `playstyle_cluster` labels across two runs on the same input (the single highest-value test per `TESTING_GUIDE.md Â§3`).
- **Expected outcome:** The project has a safety net against accidental reproducibility regressions (e.g. a seed removal) before it can be called anything close to production-ready.

## HIGH

### ML-01: Fix the archetype-matching `StandardScaler` fragility â€” âœ… RESOLVED (Phase 4C)
- **Status:** RESOLVED by Phase 4C (Option C). `_assign_labels_from_archetypes` now accepts the player-level `scaler_out`/`scaler_gk` from `group_players` and uses those to transform both centroids and archetype vectors. The fallback (centroid-only scaler) remains as a code path for direct unit-test calls but is no longer the production path. See `DECISIONS.md` ADR-009, `ML_GUIDELINES.md Â§3`.
- **Note:** The scaler-fix was implemented as part of the larger Option C refactor. No separate scaler-only change was needed.

### ML-02: Scope percentile computation to position-relevant stats — ✅ RESOLVED
- **Status:** RESOLVED 2026-07-21 (Phase 5). `add_position_percentiles` now initialises each percentile column as NaN and only computes values for position groups where the stat is relevant per `POSITION_COMPARE_STATS`.
- **Files affected:** `features.py` (`add_position_percentiles`), `tests/test_model_engine.py` (4 new tests for NaN-on-irrelevant-stats).

### STYLE-01: Remove or wire up the unused `search_query` parameter
- **Priority:** High | **Difficulty:** Low | **Impact:** Low-Medium (code clarity/DRY) | **Effort:** ~30 minutes
- **Dependencies:** None
- **Files affected:** `features.py` (`filter_dataframe`)
- **Acceptance criteria:** Either `filter_dataframe`'s `search_query` parameter is removed (since `app.apply_search_filter` already handles search separately) or the two search paths are consolidated into one, with a test locking in the chosen behavior.
- **Expected outcome:** No dead/misleading parameter in a public function signature. See `STYLE_GUIDE.md Â§12`.

### DEP-01: Add `.gitignore` and pin dependency upper bounds / lockfile — ✅ RESOLVED
- **Status:** RESOLVED. `.gitignore` existed (verified). Added upper bounds to `requirements.txt` (e.g., `streamlit>=1.28.0,<2.0.0`). Generated `requirements.lock` via `pip freeze`. Added `models/` to `.gitignore`.

## MEDIUM

### V2-DATA: StatsBomb event parser (P3) — ✅ RESOLVED
- **Status:** RESOLVED 2026-08-07 (commit `7ccb424`). `statsbomb_parser.py` produces 21 locked event-derived features (pressures, recoveries, touches by zone, GK metrics, etc.) from StatsBomb Open Data; `build_master_dataset.py` merges them into `data/wc2022_players_master.csv` (217 rows × 167 cols). See `PROJECT_STATE.md` v2 roadmap (P1–P5 data pipeline complete; P6–P9 ML/app still pending) and `ARCHITECTURE.md` §11.
- **Tests:** 35 parser tests in `tests/test_statsbomb_parser.py` lock the contract, zone boundaries, GK heuristics, merge gating, and real-dataset cardinality.

### DATA-01: Integrate possession/passing stats into the pipeline
- **Priority:** Medium | **Difficulty:** High | **Impact:** High (materially richer playstyle signal) | **Effort:** ~3-5 days
- **Status:** v2 scoped. The original scraper (`fetch_possession_stats.py`) has been deleted in v1.0 cleanup. A new data-collection mechanism is needed. **Note:** the v2 rebuild largely supersedes this — the P3 StatsBomb parser already delivers event-derived possession/passing-adjacent features (see V2-DATA above, `ARCHITECTURE.md` §11).
- **Dependencies:** TEST-01 (the scaler fragility ML-01 is now resolved — see ADR-009)
- **Files affected:** `data_loader.py` (new loader/merge step), `model_engine.py` (`OUTFIELD_FEATURES`, `OUTFIELD_ARCHETYPES` re-tuning), possibly new scraper or alternate data source
- **Acceptance criteria:** Possession/passing stats join the outfield feature set via the same per-90 normalization pipeline; `OUTFIELD_ARCHETYPES` centroid targets are re-validated (adding dimensions changes clustering geometry — this is not a drop-in change); resulting clusters are manually sanity-checked.
- **Expected outcome:** Materially better playstyle differentiation (e.g. distinguishing possession-retaining midfielders from pressing ones, which the current 6-feature set cannot do). See `DECISIONS.md` ADR-005, `ML_GUIDELINES.md §14`, `PROJECT_SPEC.md §5`.

### ML-03: Model persistence — ✅ RESOLVED
- **Status:** RESOLVED. Implemented `joblib` persistence for `StandardScaler` + `KMeans` objects with metadata JSON (dataset hash, row count, fit timestamp, library versions). Added `_get_or_fit_model` with `@st.cache_resource`, `_save_model_artifacts`, `_load_model_artifacts`, `_compute_dataset_hash`, `_apply_loaded_model`. CLI `--persist` flag on `model_engine.py`. Added tests for save/load roundtrip and hash-mismatch invalidation.
- **Files affected:** `model_engine.py`, `requirements.txt` (added `joblib>=1.3.0`), `tests/test_model_engine.py` (new tests), `.gitignore` (added `models/`)

### ML-04: Add clustering evaluation metrics — ✅ RESOLVED
- **Priority:** Medium | **Difficulty:** Low | **Impact:** Medium (diagnostic value, portfolio value) | **Effort:** ~2-3 hours
- **Dependencies:** None
- **Files affected:** `model_engine.py` (`__main__` block primarily, or a small `evaluate_clusters` function)
- **Acceptance criteria:** Silhouette score and Davies-Bouldin index computed per group (outfield, GK) and logged when `model_engine.py` is run standalone.
- **Expected outcome:** Objective, reviewable evidence of cluster quality â€” currently zero such metrics exist anywhere in the project. See `ML_GUIDELINES.md Â§9`.

### ARCH-01: Extract hardcoded configuration into named constants with rationale comments
- **Priority:** Medium | **Difficulty:** Low | **Impact:** Low-Medium | **Effort:** ~2 hours
- **Dependencies:** None
- **Files affected:** `data_loader.py` (`270` threshold), `model_engine.py` (`8`, `2`, `42`, `3.5`)
- **Acceptance criteria:** Each magic number becomes a named module-level constant (e.g. `MIN_MINUTES_THRESHOLD = 270  # three full 90-minute matches`) per `STYLE_GUIDE.md Â§14`.
- **Expected outcome:** Slightly better readability and a natural place to hang future config-file wiring.

### TEST-02: Full test coverage per `TESTING_GUIDE.md`
- **Priority:** Medium | **Difficulty:** Medium-High | **Impact:** High (cumulative) | **Effort:** ~3-4 days
- **Dependencies:** TEST-01
- **Files affected:** `tests/` (all files)
- **Acceptance criteria:** Every public function in `data_loader.py`, `model_engine.py`, `features.py` has at least one test; every `build_*` in `charts.py` has a smoke test â€” per `TESTING_GUIDE.md Â§10`.
- **Expected outcome:** Meets the Definition of Production Ready testing bar (`PROJECT_CONSTITUTION.md Â§16`).

### CI-01: Basic CI (lint + test on push) — ✅ RESOLVED
- **Status:** RESOLVED. Created `.github/workflows/ci.yml` running `ruff check .` and `pytest tests/ -v` on every push/PR to main.
- **Files affected:** `.github/workflows/ci.yml`, `requirements-dev.txt` (added `ruff>=0.4.0`)

## LOW

### STYLE-02: Remove dead code in `fetch_possession_stats.py`
- **Status:** RESOLVED. File was deleted in v1.0 cleanup.
- **Priority:** Low | **Difficulty:** Trivial | **Impact:** Low | **Effort:** ~10 minutes

### DOC-01: Expand `README.md` with a link to `/docs`
- **Priority:** Low | **Difficulty:** Trivial | **Impact:** Low-Medium (discoverability) | **Effort:** ~15 minutes
- **Files affected:** `README.md`
- **Acceptance criteria:** README links to `docs/00-constitution/PROJECT_CONSTITUTION.md` as the entry point for contributors.

### PERF-01: Categorical dtypes for high-cardinality-repeated columns
- **Priority:** Low | **Difficulty:** Low | **Impact:** Low at current scale, Medium after multi-season | **Effort:** ~1 hour
- **Files affected:** `data_loader.py`
- **Acceptance criteria:** `comp`, `squad`, `primary_position`, `Playstyle` become `pd.Categorical` â€” only pursue once row counts materially grow (`PERFORMANCE_GUIDE.md Â§3`).

## FUTURE

### FUT-01: Multi-season support
- **Priority:** Future | **Difficulty:** High | **Impact:** High | **Effort:** ~1-2 weeks
- **Files affected:** `data_loader.py`, `model_engine.py`, `app.py`, `ARCHITECTURE.md`
- **Acceptance criteria:** A season selector replaces the hardcoded filename; cache keys correctly incorporate season; clustering remains season-scoped per `ML_GUIDELINES.md Â§14`.

### FUT-02: Cache invalidation on data file change
- **Priority:** Future | **Difficulty:** Low | **Impact:** Low-Medium (operational) | **Effort:** ~1 hour
- **Files affected:** `data_loader.py`, `model_engine.py`, `app.py`
- **Acceptance criteria:** Cache key incorporates file mtime or content hash so replacing the CSV without a process restart correctly invalidates cached data. See `PERFORMANCE_GUIDE.md Â§4`.

### FUT-03: Multi-page navigation / dedicated Player Profile view
- **Priority:** Future | **Difficulty:** Medium | **Impact:** Medium | **Effort:** ~3-5 days
- **Files affected:** `app.py` (restructure), possibly new `pages/` directory, requires a `DECISIONS.md` entry first.

### FUT-04: CSV export of filtered views
- **Priority:** Future | **Difficulty:** Low | **Impact:** Low-Medium | **Effort:** ~2 hours
- **Files affected:** `app.py` (`st.download_button` on `filtered_df`)

