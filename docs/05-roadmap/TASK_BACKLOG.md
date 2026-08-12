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

### V2-DATA: StatsBomb event parser + position-scoped features (P3 + P6) — ✅ RESOLVED
- **Status:** RESOLVED. **P3** (2026-08-07, commit `7ccb424`): `statsbomb_parser.py` produces 21 locked event-derived features (pressures, recoveries, touches by zone, GK metrics, etc.). **P6** (2026-08-12, branch `statsbomb-parser`): 23 more event-derived features (passing, defending/duels, shots/xG/npxG, box/final-third touches, penalties) + `parse_lineups()`/`position_v2` (6 groups from most-played StatsBomb lineup position) + data fixes (`conversion_pct` overflow, `dribble_success_pct`, dropped fully-null `pkwon`/`pkcon`). `build_master_dataset.py` merges everything into `data/wc2022_players_master.csv` (**217 rows × 192 cols**; position_v2 distribution GK=28, CB=59, FB/WB=36, MF=55, Wide=21, ST=18). See `PROJECT_STATE.md` v2 roadmap (P1–P6 data pipeline complete; P7 clustering complete; P8–P9 ML/app still pending) and `ARCHITECTURE.md` §11.
- **Tests:** 52 parser tests in `tests/test_statsbomb_parser.py` lock both contracts, zone boundaries, GK heuristics, merge gating, `position_v2` derivation, and real-dataset cardinality/distribution.

### V2-ML: Position-scoped KMeans engine (P7) — ✅ RESOLVED
- **Status:** RESOLVED (2026-08-12, branch `statsbomb-parser`). `v2_model_engine.py` is a headless engine that fits one KMeans per `position_v2` group (k = 2/3/3/5/3/4, seed 42) on the P6 master and labels each cluster against the **20 archetypes** encoded as **σ-offset profiles** (traits stored as σ-above-group-mean, converted to raw units via the player-level scaler — fixes the raw-unit vectors that were 2–40σ off real centroids and produced 100% "Mixed Profile" on the first fit). Dimension-aware label threshold `3.5·√(n/6)` preserves v1 semantics. Persistence to `models_v2/` (per-group scaler/kmeans joblib, `cluster_labels_v2.json`, `metadata_v2.json` with dataset SHA256); `_artifact_stem` sanitizes the `FB/WB` slash so `--persist` writes into real files. CLI `--persist` / `--evaluate`; both verified end-to-end (cache reload reproduces fresh-fit labels exactly). See `ARCHITECTURE.md` §11.
- **Tests:** 17 engine tests in `tests/test_v2_model_engine.py` (constant structure, determinism, all-rows-labeled, label provenance, small-group guard, unknown-position exclusion, persistence roundtrip, hash-mismatch invalidation, no-streamlit import graph, real-master feature availability/data fixes/non-degenerate labels, GK-fallback label).
- **Review gate (owner decision — RESOLVED):** first `--evaluate` flagged GK (18/28 "Mixed Profile") — root-caused as a genuinely quiet GK cluster, not a calibration failure. Owner decided "Mixed Profile" is not acceptable as a dominant user-facing output and renamed the **GK fallback to "Traditional Goalkeeper"** (verified: the quiet cluster is the stay-at-home keeper — below-mean on saves and every sweeping/distribution trait). Now GK = Shot Stopper 10 · Traditional Goalkeeper 18; other groups keep "Mixed Profile" for their rare outliers (MF 1).

### V2-MERGE: Merge `statsbomb-parser` → `main` — ✅ RESOLVED (2026-08-12)
- **Status:** RESOLVED. Phase B (spec 19–20, P6, P7, GK label rename, docs handoff) was fast-forwarded to `main` as 5 commits; `main` = `origin/main` = `caffe0e`. Merged via a local ff-merge + push (no force). The `statsbomb-parser` branch is kept in sync with `main`.
- **Post-merge validation on main:** `python -m pytest tests/ -q` (105 expected), `ruff check .`, `python v2_model_engine.py --evaluate` reproduces the label distribution (GK = Shot Stopper 10 · Traditional Goalkeeper 18). CI runs these on every push to `main`.

### P8: v2 clustering evaluation (silhouette, DB, stability/bootstrap)
- **Priority:** Medium | **Effort:** ~1 day
- **Status:** Pending (next engineering task after merge). Add per-group bootstrap stability / refit-variance to `v2_model_engine.py --evaluate` (silhouette/DB already logged per group). Low silhouette on ST/Wide (18–21 players × 23–34 dims) is expected per `ARCHITECTURE.md` §11 risks — the goal is stability evidence, not higher scores.
- **Files affected:** `v2_model_engine.py` (+ tests).

### P9: v2 visualization + wire into `app.py`
- **Priority:** Medium | **Effort:** ~2 days
- **Status:** Pending. Bring the v2 clustered output into the Streamlit app: position-aware radar/playstyle explorer against the 20 archetypes, H2H, distribution. This is the first v2 module to enter the v1 app's import graph (headless constraint applies to the engine only). See `ARCHITECTURE.md` §11 and `STREAMLIT_GUIDELINES.md`.

### DATA-01: Integrate possession/passing stats into the pipeline
- **Priority:** Medium | **Difficulty:** High | **Impact:** High (materially richer playstyle signal) | **Effort:** ~3-5 days
- **Status:** ✅ **SUBSMED by V2-DATA.** The P6 StatsBomb parser now delivers the full possession/passing/defending feature families event-derived (passes, progressive passes, completion, key/through-ball/switches, into-box/final-third, duels, pressures, carries, touches-by-zone) — see V2-DATA above and `ARCHITECTURE.md` §11. No new scraper or FBref download is needed.
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

