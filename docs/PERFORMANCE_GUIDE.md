# PERFORMANCE GUIDE

Authority: subordinate to `PROJECT_CONSTITUTION.md`. Current scale context: **2,839 raw rows / 2,183 post-filter rows, 53 raw columns.** At this scale almost nothing in the pipeline is a real bottleneck today — this guide exists so performance stays good as data volume grows (multi-season, possession stats), not because there's a current fire to fight.

---

## 1. Pandas Optimization

- Avoid row-wise `.apply()` with a Python function where a vectorized operation exists. The codebase is already good about this — `_add_per90_rates` uses vectorized division (`df[stat] / ninety_s`), not `.apply(lambda row: ...)`. The one legitimate `.apply()` in the codebase (`df["player"].apply(remove_accents)` in `app.py`) is justified because `unicodedata.normalize` has no vectorized pandas equivalent — this is the right call, not a smell.
- Chain filters with boolean masks rather than repeated `.loc` calls where possible, matching `features.filter_dataframe`'s existing pattern of sequential `filtered = filtered[filtered[col].isin(values)]`.
- `df.copy()` is used deliberately at function boundaries throughout (`data_loader.load_and_clean_data`, `features.filter_dataframe`, `features.add_position_percentiles`) to avoid `SettingWithCopyWarning` and accidental mutation of a caller's DataFrame. **Keep this pattern** — removing a `.copy()` "for speed" is a false optimization at this data scale and risks silent mutation bugs; it would only become a real tradeoff worth reconsidering at 100x+ current row counts.

## 2. NumPy Optimization

- `np.linalg.norm` is already used correctly for vectorized distance computation in both `model_engine._assign_labels_from_archetypes` (archetype distances) and `model_engine.get_cluster_profiles` (distance-to-centroid for representative players) — no per-row Python loops. Preserve this pattern for any new distance-based feature.

## 3. Memory Management

- At ~2,200 rows × ~60-70 columns (raw + derived), the full in-memory footprint is trivial (low single-digit MB). No memory optimization (categorical dtypes, chunked reads, etc.) is currently warranted.
- **Forward-looking threshold**: if multi-season support (`TASK_BACKLOG.md`) multiplies row count by 5-10x (multiple seasons loaded simultaneously) or possession-stat integration roughly doubles column count, revisit whether `comp`, `squad`, `primary_position`, and `Playstyle` should become `pd.Categorical` dtype — cheap to do, meaningful memory/groupby-speed win once the DataFrame is materially larger.

## 4. Caching

- Three-layer `@st.cache_data` stack (`ARCHITECTURE.md §8`) is the single most important performance mechanism in the app — it means clustering (the only non-trivial-cost operation) runs once per process lifetime, not once per user interaction.
- **Operational caveat to know**: cache keys are derived from the function's arguments and Streamlit's hash of the function body — **not** from the CSV file's contents or modification time. Replacing `players_data_light-2025_2026.csv` on disk without restarting the Streamlit process will silently continue serving stale cached data. If/when this becomes an operational pain point (e.g. after multi-season support ships), the fix is to add the file's mtime or a content hash as an explicit cache-key argument to `load_and_clean_data`/`get_clustered_data`/`load_app_data` — track in `TASK_BACKLOG.md`, not implemented here.
- Never cache a function that reads `st.session_state` or any widget value directly — cache correctness depends on all relevant inputs being explicit function arguments.

## 5. Lazy Loading

- Not currently applicable — the entire dataset is small enough to load eagerly. Do not introduce pagination/lazy loading for the main table until row counts grow by an order of magnitude; `st.dataframe` already virtualizes rendering for reasonably large tables client-side.

## 6. Model Loading

- No persisted model exists yet (`ML_GUIDELINES.md §11`); "model loading" today *is* "recompute KMeans," which completes in well under a second at current scale and is fully covered by the `@st.cache_data` layer on `get_clustered_data`. Once model persistence is introduced, loading a pickled/joblib artifact from disk must also be wrapped in `@st.cache_resource` (the Streamlit-recommended decorator for non-serializable objects like fitted sklearn models, as distinct from `@st.cache_data` for DataFrames) — do not use `@st.cache_data` for a `KMeans`/`StandardScaler` object.

## 7. Streamlit Rerender Optimization

- Streamlit reruns the entire `app.py` script top-to-bottom on every widget interaction. The current structure is already optimized for this: the only genuinely expensive step (`load_app_data`) is cached, and everything after it (filtering, chart building) is cheap enough (sub-second on ~2,200 rows) to simply re-run every time without special-casing.
- Avoid introducing widgets inside a loop that generates a large, unbounded number of components (e.g. one `st.selectbox` per player) — none exist today; keep it that way.
- If a future section becomes genuinely expensive to recompute on every rerun (unlikely at current scale), prefer `@st.cache_data` on the computation function over manual `st.session_state` memoization — simpler and consistent with the rest of the codebase.

## 8. Data Loading

- Single `pd.read_csv` call, no chunking — appropriate at ~2,839 rows. If multi-season loading eventually means reading multiple CSVs, prefer `pd.concat` over multiple files read individually rather than a single mega-CSV, to keep `data_loader.py`'s per-file cleaning logic reusable per season before concatenation.

## 9. Algorithmic Complexity

- K-Means: O(n · k · i · d) per group (n=rows, k=clusters, i=iterations, d=features) — trivial at current n. `n_init=10` means 10 independent runs; still trivial at this scale. No complexity concerns until n grows by orders of magnitude.
- Percentile computation (`features.add_position_percentiles`) is O(n log n) per stat per position group (due to `.rank()`) — called once per stat in `get_all_compare_stats()` (currently a handful of stats), fully cached via the `load_app_data` wrapper. Not a concern at current scale; would only matter if the stat catalog grew into the hundreds.

## 10. Profiling Strategy

- No profiling infrastructure exists today, and none is warranted at current data scale — premature profiling would be YAGNI (`PROJECT_CONSTITUTION.md §11`). If/when the app is reported as slow:
  1. First check whether the slowness is a **cold cache** (expected on first load / after a code change) vs. a **genuine per-rerun cost** (the actual problem).
  2. Use Streamlit's built-in `st.write(st.session_state)` / the browser dev tools network tab to distinguish server compute time from network/render time before reaching for `cProfile`.
  3. Only introduce `cProfile`/`line_profiler` on the specific cached function suspected of being slow — never profile the whole app blindly.

## 11. Optimization Priorities (in order, for this project specifically)

1. **Correctness of caching** (never serve stale or wrong data) over raw speed — a fast, wrong playstyle label is worse than a correctly-cached correct one.
2. **Cold-start time** (first load after deploy/restart) since that's the only time users currently experience the real clustering cost.
3. **Table/chart render responsiveness** on filter interaction — already fast; protect this as new sections are added by keeping filtering logic in `features.py` cheap and vectorized.
4. **Memory footprint** — lowest priority today given current data scale; revisit only when multi-season/possession-stat integration materially changes row/column counts.
