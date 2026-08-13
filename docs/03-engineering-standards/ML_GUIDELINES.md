# ML GUIDELINES
### Clustering & feature engineering standards

Authority: subordinate to `PROJECT_CONSTITUTION.md`. Governs `model_engine.py`, `data_loader.py`'s feature-derivation code, and any future ML code.

---

## 1. Scope of "ML" in this project

This is **unsupervised, descriptive** clustering â€” there is no train/test split, no accuracy metric, no ground truth labels. Every guideline below is written for that reality; do not import supervised-learning conventions (e.g. "test accuracy") that don't apply here.

## 2. Feature Engineering

- **Per-90 normalization is mandatory for any new rate-like feature** used in clustering, matching the existing pattern (`data_loader._add_per90_rates`). A new feature like `xg` must become `xg_p90` before it's added to `OUTFIELD_FEATURES`, using the same `df[stat] / df["90s"].replace(0, pd.NA)` pattern (with `.fillna(0)` at the end, as already done) to avoid division-by-zero for the (already-filtered-out, but defensively handled) zero-minutes case.
- **Percentage-type stats stay raw**, not per-90'd â€” `save%` is correctly left untouched in `GK_FEATURES`/`GK_ARCHETYPES` since a percentage is already rate-normalized. Any new percentage-based feature must follow this same non-transformation.
- Keep the **outfield/GK feature split** (`OUTFIELD_FEATURES` vs `GK_FEATURES`) â€” never merge these into one shared feature list; goalkeeper and outfield stat distributions are not comparable (see `DECISIONS.md` ADR-001).

## 3. Scaling & Normalization

- `StandardScaler` (mean 0, std 1) is the correct choice for K-Means, which is distance-based â€” this is already used correctly for both the outfield and GK feature matrices in `model_engine.group_players`.
- **ML-01 (fixed in Phase 4C / ADR-009):** the *second* `StandardScaler` inside `_assign_labels_from_archetypes` is now replaced. The function accepts the player-level `scaler_out`/`scaler_gk` from `group_players` and uses those to transform both centroids and archetype vectors, anchoring the archetype-matching distance metric to the real data distribution. When no scaler is provided (e.g. direct unit-test call), it falls back to fitting on the centroids â€” sufficient for larger k (8) but unreliable for small k (2). Track remaining scaler-adjacent concerns in `TASK_BACKLOG.md` ML-04 (evaluation metrics).

## 4. Data Cleaning

- Column normalization (`strip/lower/replace spaces and dashes with underscores`) must remain the **first** step of any new loader, exactly as in `data_loader.load_and_clean_data`, so that all downstream code can rely on a single naming convention.
- `primary_position = pos.split(",")[0]` is a deliberate simplification of multi-position players (e.g. 217 players listed as `"MF,FW"` in the raw data use `MF` as primary). Any change to this rule (e.g. weighting by all listed positions) is a modeling decision and must be logged in `DECISIONS.md`, since it changes which population a player's percentiles are computed against.

## 5. Outliers

- The project currently does **not** remove statistical outliers before clustering â€” this is correct for K-Means used descriptively (an "Elite Finisher" cluster is expected to contain outliers on `gls_p90`; removing them would defeat the purpose).
- Outliers are instead *surfaced*, not removed, via `charts.build_scatter_chart`'s z-score-based `outlier_score`. Keep this separation: outlier handling for clustering purposes (none, by design) is a different concern from outlier *visualization* (the scatter plot's explicit feature).

## 6. Missing Values

- Current policy: `fillna(0)` before scaling/clustering (`model_engine.group_players`) and before percentile ranking (`features.add_position_percentiles`). This is a defensible default for count/rate stats (see `DECISIONS.md` ADR-007).
- **ML-02 (RESOLVED):** `add_position_percentiles` now initialises each percentile column as NaN and only computes values for position groups where the stat is relevant per `POSITION_COMPARE_STATS`. Irrelevant stat-position pairs (e.g. `saves_percentile` for forwards) stay NaN instead of a misleading tied-at-zero 50th-percentile rank. See `DECISIONS.md` ADR-007 and `features.py::add_position_percentiles`.

## 7. Feature Weighting

- No explicit feature weighting exists today â€” `StandardScaler` gives every feature equal weight after scaling. If a future iteration wants to weight, e.g., `gls_p90` more heavily than `crs_p90` for the "Elite Finishers" archetype match, that must be an explicit, documented multiplier applied post-scaling (not by changing the raw archetype values, which represent literal expected per-90 rates, not weights) â€” log the change in `DECISIONS.md` with the reasoning.

## 8. K-Means Specifics

- **k is fixed, not tuned**: `n_clusters=8` for outfield, `n_clusters=2` for goalkeepers, chosen to match the number of hand-authored archetypes (`OUTFIELD_ARCHETYPES`/`GK_ARCHETYPES`) and informed by an elbow analysis on the actual 2025/26 data (K=8 revealed natural groupings including Wide Creators, Advanced Attackers, and Direct Attackers that K=5 collapsed into forced mislabels). This is intentional â€” the product requirement is "8 named outfield styles and 2 named GK styles," not "however many clusters the data naturally forms." Do not "improve" this by auto-selecting k without a product conversation first (this would break the fixed archetype-matching design).
- `n_init=10`: explicit and reproducible. Do not change to `n_init="auto"` without verifying the sklearn version behavior matches (see `requirements.txt`'s `scikit-learn>=1.3.0` floor) and confirming labels remain stable.
- `random_state=42` is set on both `KMeans` calls. **This must never be removed or randomized** â€” reproducibility of playstyle labels across runs is a product requirement (`PROJECT_CONSTITUTION.md Â§8`), not just good practice.

## 9. Evaluation Metrics

Both engines compute per-group silhouette + Davies-Bouldin via `logging` (not `print`, per `STYLE_GUIDE.md`): v1 in `model_engine.evaluate_clustering` (ML-04), v2 in `v2_model_engine.evaluate_clustering` (P7). The v2 `--evaluate` additionally computes **bootstrap stability / refit-variance** (P8, `v2_model_engine.evaluate_bootstrap_stability`): per `position_v2` group, B=100 same-n bootstrap resamples, each refits the group's exact production preprocessing (`fillna(0) -> StandardScaler -> KMeans(k, seeded, n_init=10)`) and predicts labels for all original players, scored by `adjusted_rand_score` vs the deployed partition. Aggregated as mean +/- std ARI, mean +/- std refit silhouette/DB, and a degenerate fraction (see `DECISIONS.md` ADR-010).

- These are **diagnostic**, not gating -- because k is fixed by product requirements (Section 8 above), a low silhouette score doesn't mean “change k,” it means the archetype framing may not fit this season's data well, which is a product/ML discussion, not an automatic code branch.
- Bootstrap stability is the evidence for *how much to trust the fixed partition*: low silhouette on high-dim small-n groups (ST/Wide) is expected, and the bootstrap quantifies the resulting refit instability. It is the lever that *justified* the ST k-reduction (ADR-011): ST k=4 showed ARI 0.45 with a cluster collapsing in 39% of refits, and dropping to k=3 removed the micro-cluster and cut degeneracy to 0.14. Wide remains the provisional small-n case -- reported as a limitation, not a blocker.

## 10. Random Seed & Reproducibility

- Every stochastic operation must be seeded. Today that's exactly the two `KMeans(random_state=42, ...)` calls. Any new stochastic component (e.g. a future `train_test_split`, a bootstrap resampling for confidence intervals, a different clustering algorithm) must also take an explicit, documented seed â€” no bare `random_state=None` in project code, ever.
- The v2 bootstrap stability evaluation (P8) follows the same rule: every resample uses `np.random.default_rng(RANDOM_STATE + b)` and every KMeans refit uses `random_state = RANDOM_STATE + BOOTSTRAP_ITERATIONS + b` -- the refit stream is offset by B so the two seed ranges never collide, and the whole evaluation is deterministic run-to-run (locked by `test_bootstrap_deterministic`).
- Reproducibility also depends on **library versions** (`scikit-learn`'s KMeans implementation has changed defaults across versions â€” e.g. `n_init` default). `requirements.txt` currently only sets lower bounds (`scikit-learn>=1.3.0`). See `PERFORMANCE_GUIDE.md`/`SECURITY_GUIDE.md` for the broader pinning discussion; from an ML-correctness standpoint, an unpinned upper bound is a reproducibility risk worth resolving before calling the project "Production Ready."

## 11. Model Persistence

**Implemented (ML-03 RESOLVED).** Fitted `StandardScaler` + `KMeans` objects are now persisted via `joblib` alongside a metadata JSON file containing dataset fingerprint (SHA256 hash, row count), fit timestamp, and library versions. This enables:

- **Fast cold starts**: `@st.cache_resource` loads persisted artifacts instead of refitting when the dataset hasn't changed
- **Auditability**: Metadata records exactly which model produced the current labels
- **Automatic invalidation**: Changing the CSV file (detected via SHA256 hash mismatch) triggers a refit and new artifact generation

**Key functions in `model_engine.py`:**
- `_get_or_fit_model(filepath)` — `@st.cache_resource` entry point; tries load -> falls back to fit+save
- `_save_model_artifacts(...)` — persists scalers, KMeans models, label mappings, and metadata
- `_load_model_artifacts(filepath)` — loads artifacts and validates dataset hash
- `_compute_dataset_hash(filepath)` — SHA256 of CSV for change detection
- `_apply_loaded_model(...)` — applies loaded scalers + KMeans to fresh cleaned data

**CLI:** `python model_engine.py --persist` explicitly fits and saves artifacts with evaluation metrics logged.

**Artifacts layout (`models/` directory, gitignored):**
```
models/
├── outfield_scaler.joblib
├── outfield_kmeans.joblib
├── gk_scaler.joblib
├── gk_kmeans.joblib
├── cluster_labels.json      # {outfield: {0: "Elite Finishers", ...}, gk: {0: "Shot-Stoppers", ...}}
└── metadata.json            # dataset_hash, row_count, fit_timestamp, sklearn_version, params
```

**Metadata schema (`metadata.json`):**
```json
{
  "dataset_file": "players_data_light-2025_2026.csv",
  "dataset_hash": "sha256:...",
  "row_count": 2183,
  "fit_timestamp": "2026-07-26T...",
  "sklearn_version": "1.5.0",
  "numpy_version": "1.26.0",
  "joblib_version": "1.3.0",
  "kmeans_params": {"n_clusters": 8, "random_state": 42, "n_init": 10},
  "gk_kmeans_params": {"n_clusters": 2, "random_state": 42, "n_init": 10}
}
```

**Determinism guarantee:** Loaded model produces byte-identical `playstyle_cluster` labels to a fresh fit on the same data (tested in `test_model_engine.py::TestModelPersistence::test_save_and_load_roundtrip`).

Until persistence exists, **the model IS the code + the CSV** — any change to `model_engine.py`'s feature lists, archetype dictionaries, or `data_loader.py`'s cleaning logic silently changes every player's playstyle label on next cold start. This is a real operational risk worth knowing, not necessarily one that needs fixing immediately.

## 12. Pipeline Design

- Keep the strict separation: `data_loader.py` (cleaning) â†’ `model_engine.py` (modeling) â†’ `features.py` (presentation-layer derived stats, e.g. percentiles) â†’ `charts.py` (visualization). A new ML feature (e.g. a second clustering pass, an anomaly score) belongs in `model_engine.py`, not scattered into `features.py` or `app.py`.

## 13. Data Leakage Prevention

- Not currently a risk in the strict supervised-learning sense (no train/test split exists), but the *conceptual* analog matters here: **percentiles must remain position-scoped** (`features.add_position_percentiles` already groups by `primary_position` before ranking) so that, e.g., a goalkeeper's `int_p90` percentile is computed against other goalkeepers, not against outfield players where interceptions are a completely different statistical regime. Any new percentile or scoring feature must preserve this scoping â€” an un-scoped percentile across all positions would be a leakage-equivalent bug (it would silently encode "is this player a goalkeeper" into a stat meant to describe relative skill).

## 14. Future Extensibility

- **Possession/passing features** (if integrated in v2 — see the v1.0 ADR-005 update in `DECISIONS.md`): when integrated, they must go through the same per-90 normalization pipeline and get added to `OUTFIELD_FEATURES` (and likely require re-tuning `OUTFIELD_ARCHETYPES` centroid targets, since adding dimensions changes the clustering geometry â€” this is not a drop-in addition).
- **Multi-season support**: when the hardcoded filename is replaced with a season parameter (`TASK_BACKLOG.md`), clustering must remain **season-scoped** â€” never cluster across multiple seasons' rows for the same player as if they were independent observations without an explicit, documented decision about how to handle within-player, cross-season comparison.

