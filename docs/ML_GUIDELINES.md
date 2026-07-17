# ML GUIDELINES
### Clustering & feature engineering standards

Authority: subordinate to `PROJECT_CONSTITUTION.md`. Governs `model_engine.py`, `data_loader.py`'s feature-derivation code, and any future ML code.

---

## 1. Scope of "ML" in this project

This is **unsupervised, descriptive** clustering — there is no train/test split, no accuracy metric, no ground truth labels. Every guideline below is written for that reality; do not import supervised-learning conventions (e.g. "test accuracy") that don't apply here.

## 2. Feature Engineering

- **Per-90 normalization is mandatory for any new rate-like feature** used in clustering, matching the existing pattern (`data_loader._add_per90_rates`). A new feature like `xg` must become `xg_p90` before it's added to `OUTFIELD_FEATURES`, using the same `df[stat] / df["90s"].replace(0, pd.NA)` pattern (with `.fillna(0)` at the end, as already done) to avoid division-by-zero for the (already-filtered-out, but defensively handled) zero-minutes case.
- **Percentage-type stats stay raw**, not per-90'd — `save%` is correctly left untouched in `GK_FEATURES`/`GK_ARCHETYPES` since a percentage is already rate-normalized. Any new percentage-based feature must follow this same non-transformation.
- Keep the **outfield/GK feature split** (`OUTFIELD_FEATURES` vs `GK_FEATURES`) — never merge these into one shared feature list; goalkeeper and outfield stat distributions are not comparable (see `DECISIONS.md` ADR-001).

## 3. Scaling & Normalization

- `StandardScaler` (mean 0, std 1) is the correct choice for K-Means, which is distance-based — this is already used correctly for both the outfield and GK feature matrices in `model_engine.group_players`.
- **Known fragility (ADR-002):** the *second* `StandardScaler` inside `_assign_labels_from_archetypes` is fit on only the cluster centroids (n=5 or n=2 points), not on the underlying player-level data. Recommended fix direction (not yet implemented): reuse the *same, already-fitted* `scaler_out`/`scaler_gk` from `group_players` to transform both the centroids and the archetype vectors, rather than fitting a brand-new scaler on the tiny centroid sample. This keeps the archetype-matching distance metric anchored to the real data distribution instead of to this run's specific cluster geometry. Track as `TASK_BACKLOG.md` ML-01 before implementing — this is a documentation deliverable, not a code change, per the operating instructions for this doc set.

## 4. Data Cleaning

- Column normalization (`strip/lower/replace spaces and dashes with underscores`) must remain the **first** step of any new loader, exactly as in `data_loader.load_and_clean_data`, so that all downstream code can rely on a single naming convention.
- `primary_position = pos.split(",")[0]` is a deliberate simplification of multi-position players (e.g. 217 players listed as `"MF,FW"` in the raw data use `MF` as primary). Any change to this rule (e.g. weighting by all listed positions) is a modeling decision and must be logged in `DECISIONS.md`, since it changes which population a player's percentiles are computed against.

## 5. Outliers

- The project currently does **not** remove statistical outliers before clustering — this is correct for K-Means used descriptively (an "Elite Finisher" cluster is expected to contain outliers on `gls_p90`; removing them would defeat the purpose).
- Outliers are instead *surfaced*, not removed, via `charts.build_scatter_chart`'s z-score-based `outlier_score`. Keep this separation: outlier handling for clustering purposes (none, by design) is a different concern from outlier *visualization* (the scatter plot's explicit feature).

## 6. Missing Values

- Current policy: `fillna(0)` before scaling/clustering (`model_engine.group_players`) and before percentile ranking (`features.add_position_percentiles`). This is a defensible default for count/rate stats (see `DECISIONS.md` ADR-007) but has a known side effect: percentile columns get computed for position-irrelevant stats (e.g. `saves_percentile` for forwards, all tied at 0). **Do not "fix" this by imputing means** — a mean-imputed goalkeeper stat for a forward is more misleading than a zero, not less. The correct fix (tracked in `TASK_BACKLOG.md` ML-02, not implemented here) is to scope `add_position_percentiles` to only compute percentile columns for stats relevant to each position group, using `POSITION_COMPARE_STATS` as the source of relevance.

## 7. Feature Weighting

- No explicit feature weighting exists today — `StandardScaler` gives every feature equal weight after scaling. If a future iteration wants to weight, e.g., `gls_p90` more heavily than `crs_p90` for the "Elite Finishers" archetype match, that must be an explicit, documented multiplier applied post-scaling (not by changing the raw archetype values, which represent literal expected per-90 rates, not weights) — log the change in `DECISIONS.md` with the reasoning.

## 8. K-Means Specifics

- **k is fixed, not tuned**: `n_clusters=5` for outfield, `n_clusters=2` for goalkeepers, chosen to match the number of hand-authored archetypes (`OUTFIELD_ARCHETYPES`/`GK_ARCHETYPES`), not derived from an elbow/silhouette search. This is intentional — the product requirement is "5 named outfield styles and 2 named GK styles," not "however many clusters the data naturally forms." Do not "improve" this by auto-selecting k without a product conversation first (this would break the fixed archetype-matching design in ADR-002).
- `n_init=10`: explicit and reproducible. Do not change to `n_init="auto"` without verifying the sklearn version behavior matches (see `requirements.txt`'s `scikit-learn>=1.3.0` floor) and confirming labels remain stable.
- `random_state=42` is set on both `KMeans` calls. **This must never be removed or randomized** — reproducibility of playstyle labels across runs is a product requirement (`PROJECT_CONSTITUTION.md §8`), not just good practice.

## 9. Evaluation Metrics

**Currently: none are computed.** The project has no silhouette score, Davies-Bouldin index, or Calinski-Harabasz index logged anywhere. This is a real gap for a "portfolio-quality" clustering project. Recommended (not yet implemented — see `TASK_BACKLOG.md` ML-04):

- **Silhouette score** per group (outfield, GK), computed on the scaled feature matrix right after `kmeans_out.fit_predict(...)` / `kmeans_gk.fit_predict(...)`, logged (via `logging`, not `print`, per `STYLE_GUIDE.md`) whenever `group_players` runs outside a cached Streamlit context (e.g. in the `__main__` block of `model_engine.py`).
- **Davies-Bouldin index** as a secondary check — lower is better, useful for catching a degenerate run where two clusters have effectively merged.
- These are **diagnostic**, not gating — because k is fixed by product requirements (§8 above), a low silhouette score doesn't mean "change k," it means "the 5-archetype framing may not fit this season's data well," which is a product/ML discussion, not an automatic code branch.

## 10. Random Seed & Reproducibility

- Every stochastic operation must be seeded. Today that's exactly the two `KMeans(random_state=42, ...)` calls. Any new stochastic component (e.g. a future `train_test_split`, a bootstrap resampling for confidence intervals, a different clustering algorithm) must also take an explicit, documented seed — no bare `random_state=None` in project code, ever.
- Reproducibility also depends on **library versions** (`scikit-learn`'s KMeans implementation has changed defaults across versions — e.g. `n_init` default). `requirements.txt` currently only sets lower bounds (`scikit-learn>=1.3.0`). See `PERFORMANCE_GUIDE.md`/`SECURITY_GUIDE.md` for the broader pinning discussion; from an ML-correctness standpoint, an unpinned upper bound is a reproducibility risk worth resolving before calling the project "Production Ready."

## 11. Model Persistence

**Currently: no persistence at all.** `group_players()` is recomputed from scratch on every cold cache (see `ARCHITECTURE.md §8`). This is acceptable at current data scale (2,183 rows clusters in well under a second) but is flagged as a gap for a "production-quality" bar:

- Recommended direction: persist the fitted `StandardScaler` + `KMeans` objects (e.g. via `joblib`) alongside a small metadata file (dataset filename, row count, fit timestamp, `scikit-learn` version) so that (a) the deployed app can optionally load a pinned model instead of refitting on every cold start, and (b) there's an auditable record of "which model produced these labels." Track as `TASK_BACKLOG.md` ML-03.
- Until persistence exists, **the model IS the code + the CSV** — any change to `model_engine.py`'s feature lists, archetype dictionaries, or `data_loader.py`'s cleaning logic silently changes every player's playstyle label on next cold start. This is a real operational risk worth knowing, not necessarily one that needs fixing immediately.

## 12. Pipeline Design

- Keep the strict separation: `data_loader.py` (cleaning) → `model_engine.py` (modeling) → `features.py` (presentation-layer derived stats, e.g. percentiles) → `charts.py` (visualization). A new ML feature (e.g. a second clustering pass, an anomaly score) belongs in `model_engine.py`, not scattered into `features.py` or `app.py`.

## 13. Data Leakage Prevention

- Not currently a risk in the strict supervised-learning sense (no train/test split exists), but the *conceptual* analog matters here: **percentiles must remain position-scoped** (`features.add_position_percentiles` already groups by `primary_position` before ranking) so that, e.g., a goalkeeper's `int_p90` percentile is computed against other goalkeepers, not against outfield players where interceptions are a completely different statistical regime. Any new percentile or scoring feature must preserve this scoping — an un-scoped percentile across all positions would be a leakage-equivalent bug (it would silently encode "is this player a goalkeeper" into a stat meant to describe relative skill).

## 14. Future Extensibility

- **Possession/passing features** (the natural consumer of `fetch_possession_stats.py`'s output, once adopted — see `DECISIONS.md` ADR-005): when integrated, they must go through the same per-90 normalization pipeline and get added to `OUTFIELD_FEATURES` (and likely require re-tuning `OUTFIELD_ARCHETYPES` centroid targets, since adding dimensions changes the clustering geometry — this is not a drop-in addition).
- **Multi-season support**: when the hardcoded filename is replaced with a season parameter (`TASK_BACKLOG.md`), clustering must remain **season-scoped** — never cluster across multiple seasons' rows for the same player as if they were independent observations without an explicit, documented decision about how to handle within-player, cross-season comparison.
