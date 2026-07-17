# TESTING GUIDE

Authority: subordinate to `PROJECT_CONSTITUTION.md`. **Current state: zero automated tests exist anywhere in the repository.** This guide defines what "tested" means for this project going forward and is the primary blocker on reaching `PROJECT_CONSTITUTION.md`'s Definition of Production Ready.

---

## 1. Testing Philosophy

Because this is a data/ML pipeline, **the biggest risk is silent numerical wrongness, not crashes.** A test suite that only checks "the function runs without raising" is insufficient — tests must assert on actual values (row counts, specific computed rates, cluster label stability) wherever feasible. Prioritize tests that would have caught a real, plausible mistake in *this* codebase over generic boilerplate coverage.

## 2. Test Framework & Structure (Recommended)

- `pytest`, added to a new `requirements-dev.txt` (do not add test dependencies to the runtime `requirements.txt`).
- Proposed structure:
```
tests/
├── conftest.py              # shared fixtures (e.g. a small synthetic DataFrame)
├── test_data_loader.py
├── test_model_engine.py
├── test_features.py
└── test_charts.py
```
- Use a small **synthetic fixture DataFrame** (10-20 hand-crafted rows covering GK + outfield + a duplicate name + a zero-minutes edge case) in `conftest.py` rather than reading the real 2,839-row CSV in every test — faster, and failures are traceable to a known, human-readable input.

## 3. Unit Tests — by module

### `data_loader.py`
- `load_and_clean_data` correctly lowercases/normalizes column names (e.g. a fixture CSV with a `"Gls"` column becomes `gls`).
- The `Min >= 270` filter excludes rows below the threshold and includes rows at/above it (boundary test at exactly 270).
- `primary_position` correctly takes the first token of a comma-separated `Pos` value (`"MF,FW"` → `"MF"`).
- `_add_per90_rates`: a player with `gls=9, 90s=27.2` produces `gls_p90` ≈ `0.331`; a player with `90s=0` produces `gls_p90 == 0` (not `NaN`, not a `ZeroDivisionError`) — this is the concrete regression test for the `.replace(0, pd.NA)` / `.fillna(0)` logic.
- A missing optional rate-stat source column (e.g. no `crs` column in a fixture) does not raise — `_add_per90_rates` silently skips stats not present in `df.columns`.

### `model_engine.py`
- `group_players` on the synthetic fixture produces exactly the expected number of `GK` and outfield rows after the split, and every row has a non-null `playstyle_cluster`.
- **Determinism test**: running `group_players` twice on the same fixture produces identical `playstyle_cluster` assignments both times — this directly enforces the `random_state=42` reproducibility requirement from `PROJECT_CONSTITUTION.md §14` and `ML_GUIDELINES.md §10`. This is the single highest-value test in the whole suite: it would catch an accidental seed removal immediately.
- `_assign_labels_from_archetypes` never assigns the same archetype name to two different cluster IDs within one call (tests the `used_names` de-duplication logic) — construct a fixture where two synthetic centroids are deliberately close to the same archetype to exercise the de-dup branch.
- `get_cluster_profiles` returns a `top_players` list of length ≤5, and the players returned are genuinely those closest to the centroid on the fixture (verifiable by hand on a small synthetic set).
- `group_players` on a fixture with **zero goalkeepers** (all outfield) does not raise — `df_gk` being empty must be handled gracefully (this exercises the `if gk_features and not df_gk.empty:` guard already present in the code — a good example of an existing guard clause that should be locked in by a test).

### `features.py`
- `add_position_percentiles`: a stat where all players in a position group are tied produces well-defined (not `NaN`) percentile values.
- `filter_dataframe`: each filter dimension (league/position/squad/playstyle) in isolation and in combination with another produces the expected row subset on the fixture; passing no filters returns the full DataFrame unchanged.
- `get_compare_stats_for_position`: an unrecognized position string falls back to the `"MF"` stat set (tests the existing fallback branch).
- `format_display_table`: output columns are renamed per `DISPLAY_COLUMN_LABELS`, and a `#` column of consecutive integers starting at 1 is present regardless of the input DataFrame's original index.

### `charts.py`
- Each `build_*` function returns a `plotly.graph_objects.Figure` instance (a cheap but real smoke test — catches, e.g., a typo in a Plotly kwarg that would raise at call time).
- `build_scatter_chart` on a fixture with fewer than 100 rows returns a figure containing exactly that many points, not a crash from `nlargest(100, ...)` on a smaller-than-100 DataFrame (verifies `nlargest` gracefully caps at available rows — a real edge case given filtered views in the app can easily be smaller than 100 rows).
- `build_h2h_radar`/`build_playstyle_radar_chart`: the returned figure's `theta`/`r` arrays are "closed" (first category repeated at the end), matching the existing `... + [values[0]]` pattern — a regression test that would catch someone accidentally removing the radar-closing logic.

## 4. Integration Tests

- **End-to-end pipeline test**: `load_and_clean_data(fixture_csv) → group_players → get_cluster_profiles` on a small fixture, asserting the final output has the expected shape and that every input row survives (no rows silently dropped outside the intended `Min >= 270` filter).
- **App-data-loading test**: exercise `app.load_app_data`'s composition (rename `playstyle_cluster`→`Playstyle`, add percentiles, add unique labels) against a fixture containing at least one duplicated player name, asserting the duplicate gets a squad-suffixed `player_label` while a unique name does not.

## 5. Regression Tests

- Any bug fix must ship with a test that fails on the pre-fix code and passes after — this is the mechanism that prevents the same class of bug from recurring, and is mandatory per `AI_DEVELOPER_RULEBOOK.md`.
- Specific known-risk regressions to guard once fixed (see `TASK_BACKLOG.md`):
  - `features.filter_dataframe`'s unused `search_query` parameter (STYLE-01) — once removed or wired up, add a test locking in the chosen behavior.
  - `add_position_percentiles` computing percentiles for position-irrelevant stats (ML-02) — once scoped, a test asserting `saves_percentile` is *not* present (or is explicitly null/excluded) for forward rows.

## 6. Edge Cases Worth Explicit Tests

- Empty DataFrame after filtering (all filters combine to zero rows) — every `render_*` function in `app.py` must be checked to confirm it shows an `st.info` message rather than raising (already true by inspection for the explorer, scatter, and H2H sections; worth locking in with tests once the rendering functions are made testable independently of a live Streamlit session, e.g. by extracting the "what to show when empty" branch logic).
- A player with `90s == 0` surviving the `Min >= 270` filter — should be structurally impossible (270 minutes ÷ 90 = 3.0, so `90s` is always ≥ 3 at the filter boundary) but worth a defensive test given `_add_per90_rates` explicitly guards against division by zero regardless.
- Exactly two players with the same name in the same squad (not currently possible in the real dataset, but not structurally prevented) — document as a known, accepted limitation (`DECISIONS.md` ADR-008) rather than silently "fixing" via a test that would require new disambiguation logic.

## 7. ML Validation

- Beyond the determinism test in §3, validate that cluster **sizes are non-degenerate** on the real dataset periodically (not necessarily in CI, but as part of any change to `model_engine.py`): no outfield playstyle cluster should end up with, e.g., 1 player out of ~2,000 — that would indicate a scaling or feature bug, not a genuine tiny archetype. This is a manual sanity check today (`PROJECT_CONSTITUTION.md §14, rule 6`); consider automating a "minimum cluster size" assertion against the real CSV as a slow, non-CI-blocking test once the suite exists.

## 8. UI Validation

- Full browser-level UI testing (e.g. Playwright against a running `streamlit run app.py`) is **not** a near-term priority given the project's current size — the ROI is low relative to the effort of standing up browser automation. Prioritize unit/integration tests on the underlying data and chart-building functions (§3-4) first, since those functions are already structured to be testable without a live Streamlit session.

## 9. Acceptance Criteria (for merging any change)

- All existing tests pass.
- New/changed logic has new/updated tests.
- No test relies on the real, full `players_data_light-2025_2026.csv` unless specifically testing something about that file's actual shape (e.g. "the real CSV has exactly 5 unique `Comp` values") — prefer the small fixture for everything else, for speed and clarity of failure.

## 10. Coverage Targets

- No hard percentage target is mandated (coverage percentage is a weak proxy for test quality on a project this size). Instead: **every public function in `data_loader.py`, `model_engine.py`, and `features.py` must have at least one test**, and **every `build_*` function in `charts.py` must have at least a smoke test.** `app.py`'s `render_*` functions are lower priority for direct unit testing (they're thin Streamlit-coupled orchestration) but the pure logic they call (already factored into `features.py`/`model_engine.py`) must be fully covered.

## 11. Testing Philosophy, Restated

A test suite for a clustering app is not there to prove the clusters are "correct" (there is no ground truth) — it's there to prove the **pipeline is deterministic, the data cleaning is exact, and the presentation layer doesn't silently mangle numbers.** Keep that framing in mind when reviewing any new test for value versus busywork.
