# CODE REVIEW CHECKLIST

Authority: subordinate to `PROJECT_CONSTITUTION.md`. Run through this checklist before proposing any change, and again before considering it finished. Every item should be answerable with a specific reference to this codebase, not a generic "looks fine."

---

## Architecture Review
- [ ] Does the change stay inside the owning module per `ARCHITECTURE.md §1`'s responsibility table? (Data cleaning → `data_loader.py`; clustering → `model_engine.py`; filtering/percentiles/display formatting → `features.py`; charts → `charts.py`; orchestration/rendering → `app.py`.)
- [ ] If the change adds a new module or restructures the folder layout, is there a corresponding `DECISIONS.md` entry?
- [ ] Does the change preserve the existing caching boundaries (`@st.cache_data` on `load_and_clean_data`, `get_clustered_data`, `load_app_data`)?
- [ ] Is the fetch_possession_stats.py disconnection respected (not silently wired in)?

## Naming Review
- [ ] `snake_case` for functions/variables, `UPPER_SNAKE_CASE` for module-level constants, `_`-prefix for internal helpers — per `STYLE_GUIDE.md §2`.
- [ ] Any new DataFrame column follows the existing lowercase-underscore convention.
- [ ] Any new stat has an entry in `FRIENDLY_NAMES`/`DISPLAY_COLUMN_LABELS` if it will ever be user-facing.
- [ ] No new constant duplicates an existing one in `FRIENDLY_NAMES`, `POSITION_COMPARE_STATS`, `OUTFIELD_FEATURES`/`GK_FEATURES`, or `OUTFIELD_ARCHETYPES`/`GK_ARCHETYPES`.

## Performance Review
- [ ] Any new expensive, deterministic, cacheable computation is wrapped in `@st.cache_data` (or `@st.cache_resource` for non-serializable objects like a future persisted model — `PERFORMANCE_GUIDE.md §6`).
- [ ] No new row-wise `.apply()` where a vectorized pandas/numpy operation would work (`PERFORMANCE_GUIDE.md §1`).
- [ ] No function that reads live widget state (filters, search) is accidentally cached.

## Bug Review
- [ ] Division operations that could hit zero (e.g. per-90 rates) are guarded (matching `.replace(0, pd.NA)` / `.fillna(0)` pattern in `_add_per90_rates`).
- [ ] Empty-DataFrame edge cases are handled (e.g. filters that combine to zero rows) with an `st.info`/`st.warning`, not a crash — check against the existing pattern in `render_playstyle_explorer`, `render_h2h_section`.
- [ ] `NaN`/missing-value handling is deliberate and matches the documented policy in `DECISIONS.md` ADR-007, not an accidental new imputation strategy introduced ad hoc.
- [ ] If touching `_assign_labels_from_archetypes` or any archetype-matching logic, confirm de-duplication (`used_names`) still prevents two clusters from receiving the same label.

## Security Review
- [ ] No new `eval`/`exec`/`os.system`/untrusted `pickle` (`SECURITY_GUIDE.md §3`).
- [ ] Any new dependency is added to `requirements.txt` in the same change.
- [ ] Any new file I/O validates the source is trusted/expected (no path built from unsanitized user input).
- [ ] No secrets introduced in source; if a secret is genuinely needed, it's sourced from environment/`st.secrets`, never hardcoded.

## Testing Review
- [ ] New/changed logic has a corresponding new/updated test per `TESTING_GUIDE.md`'s module-by-module plan.
- [ ] A bug fix includes a regression test that fails on the pre-fix code.
- [ ] If touching `model_engine.py`'s clustering, the determinism expectation (`random_state=42` produces identical labels run-to-run) is preserved and, ideally, exercised by a test.

## Documentation Review
- [ ] `ARCHITECTURE.md` updated if module responsibilities, data flow, or the dependency graph changed.
- [ ] `DECISIONS.md` has a new entry if a previously-documented tradeoff was deliberately changed.
- [ ] `TASK_BACKLOG.md` updated (item marked done, or a newly-discovered issue added) as appropriate.
- [ ] Docstrings updated for any function whose behavior, inputs, or outputs changed.

## ML Review (only if `model_engine.py`, `data_loader.py`'s feature derivation, or archetype definitions are touched)
- [ ] `random_state=42` (or an equally explicit, documented seed) is still present on every stochastic operation.
- [ ] Feature scaling (`StandardScaler`) still happens before distance-based operations (KMeans fitting, archetype matching).
- [ ] Any new feature is per-90 normalized if it's a count-like rate stat, per `ML_GUIDELINES.md §2`.
- [ ] The outfield/GK feature and archetype split is preserved — no merging of the two pipelines.
- [ ] Cluster sizes on the real dataset were sanity-checked (no degenerate near-empty cluster) if `n_clusters`, feature lists, or archetype definitions changed.

## UI Review (only if `app.py` or `charts.py` are touched)
- [ ] New sections use `st.divider()` before them and a `st.subheader()`/`st.markdown("#### ...")` heading, matching existing hierarchy (`STREAMLIT_GUIDELINES.md §2`).
- [ ] New charts are built as pure functions in `charts.py`, never inline in `app.py`.
- [ ] `template="plotly_dark"` and `width="stretch"` conventions preserved.
- [ ] Empty/insufficient-data states use `st.info`/`st.warning` with a specific, actionable message.
- [ ] Any new displayed statistic uses its `FRIENDLY_NAMES` label, never a raw column name.

## Regression Review
- [ ] All four main UI sections (table, Playstyle Explorer, scatter plot, head-to-head) still function against the current dataset after the change — mentally trace each, or note explicitly if this could not be verified and why.
- [ ] `python data_loader.py` and `python model_engine.py` (the `__main__` smoke-test blocks) would still print `SUCCESS`.
- [ ] No previously-passing test now fails.

## Final Gate
- [ ] The diff is the smallest correct change that accomplishes the requested task — no unrelated refactors, no unrelated fixes bundled in.
- [ ] The change was explained clearly enough that a reviewer with no other context could approve it in under a minute, per `AI_DEVELOPER_RULEBOOK.md §6`.
