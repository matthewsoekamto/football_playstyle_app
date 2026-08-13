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
python statsbomb_parser.py                    # parse raw events -> 44 event-derived features (P3+P6) + parse_lineups -> position_v2
python build_master_dataset.py                # FBref + StatsBomb -> data/wc2022_players_master.csv
python v2_model_engine.py --persist           # v2 headless engine: fit + save to models_v2/ + log eval metrics
python v2_model_engine.py --evaluate          # v2 headless engine: fit + eval (no save)

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

v2 data pipeline + engine + visualization (WC 2022 rebuild — wired into app.py via a sidebar dataset selector, P9)
statsbomb_parser.py   (pure parser: StatsBomb events -> 44 event-derived features [21 P3 + 23 P6]; parse_lineups -> position_v2)
scripts/download_statsbomb.py  (fetch raw StatsBomb Open Data into data/statsbomb/, gitignored)
build_master_dataset.py  (FBref CSVs + StatsBomb events -> data/wc2022_players_master.csv; merge_position_v2)
v2_model_engine.py    (headless engine: per-position_v2 KMeans, 20 σ-offset archetype labels, models_v2/ persistence)
v2_features.py        (app-facing layer: cached load, filter, position-scoped percentiles, σ-radar data)
tests/test_statsbomb_parser.py  (52 parser tests, incl. locked P3+P6 contracts + position_v2)
tests/test_v2_model_engine.py   (26 engine tests: determinism, provenance, persistence roundtrip, no-streamlit import, bootstrap, ST k-fix)
tests/test_v2_features.py       (13 app-facing tests: filter, percentiles, unrepresented archetypes, radar data, chart smoke)
models_v2/            (gitignored: v2 per-group scalers/KMeans, cluster_labels_v2.json, metadata_v2.json)
data/statsbomb/       (gitignored raw JSON: events/, lineups/, matches/)
```

`v2_model_engine.py` is **headless** — no streamlit in its import graph. It copies the v1 pure helpers verbatim (`_assign_labels_from_archetypes`, `evaluate_clustering`, `_compute_dataset_hash`) rather than importing `model_engine`/`data_loader`.

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

**v2 rebuild** — `data/wc2022_players_master.csv`: 217 rows × 192 columns (146 pre-P3 + 21 P3 + 23 P6 event-derived + 2 identity columns incl. `position_v2`), FIFA World Cup 2022 (StatsBomb competition 43 / season 106). Built by `build_master_dataset.py` from FBref CSVs + StatsBomb events; 217 eligible players after Min≥270 filter. **P3+P6 complete** — 44 locked event-derived features: P3 (pressures, recoveries, touches by zone, GK metrics) at `7ccb424`, P6 (passing, defending/duels, shots/xG/npxG, box/final-third touches, penalties) + `position_v2` (6 groups from most-played StatsBomb lineup position: GK=28, CB=59, FB/WB=36, MF=55, Wide=21, ST=18) on branch `statsbomb-parser`. Raw StatsBomb Open Data lives in `data/statsbomb/` (gitignored; reproducible via `scripts/download_statsbomb.py`).

**v2 engine (P7)** — `v2_model_engine.py` clusters the master by `position_v2` group (k=2/3/3/5/3/4) and labels each cluster against the **20 σ-offset archetypes** (traits as σ-above-group-mean, converted to raw units via the player-level scaler). Persists to `models_v2/` (gitignored), invalidated by SHA256 of the CSV. `python v2_model_engine.py --persist` fits+saves; `--evaluate` fits+logs per-group silhouette/DB + label distribution.

Source FBref CSVs (`wc2022_standard.csv`, `wc2022_shooting.csv`, `wc2022_miscellaneous.csv`, `wc2022_gk.csv`) remain in `data/` as inputs to the v2 build.

## Current Status (v2) — 2026-08-12

**Phase B is merged into `main`** (2026-08-12). P6 position-scoped features + `position_v2`, the P7 position-scoped KMeans engine, and the GK fallback-label rename were fast-forwarded to `main` as 5 commits (`18ebbd5` spec 19–20 · `8ec9b68` P6 · `eecb0b3` P7 · `6d0c564` GK label rename · `caffe0e` docs handoff); `main` = `origin/main` = `caffe0e`. The `statsbomb-parser` branch is kept in sync with `main` for reference.

- **Engine output (217 players):** GK = Shot Stopper 10 · Traditional Goalkeeper 18 · CB = Ball-Playing 23 / Traditional 21 / Stopper 15 · FB/WB = Attacking 25 / Defensive 11 · MF = Deep-Lying 32 / Defensive Mid 21 / Shadow Striker 1 / Mixed 1 · Wide = Inverted 9 / Traditional 9 / Wide Playmaker 3 · ST = Complete Forward 10 / False 9 4 / Target Man 4. Reproduce with `python v2_model_engine.py --evaluate`.
- **Next actions:** v2 rebuild complete (P1–P9). No open tasks — optional follow-ups (multi-tournament dataset to populate the 5 unrepresented archetypes) are v3. Tracked in `TASK_BACKLOG.md` (V2-MERGE / P8 / P8.1 / P9 all RESOLVED); full state in `docs/PROJECT_STATE.md`.
- **Persistence caveat:** v2 model artifacts invalidate on dataset-hash change only — a code change (labels/archetypes) silently serves stale labels on `--persist`; clear `models_v2/` and re-run `--persist` when the code changes.

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
│   ├── PROJECT_SPEC.md                         Product purpose, users, capabilities
│   ├── PLAYSTYLE_SPEC.md                       v2: 20-archetype feature design specs
│   ├── DATA_SOURCE_MAPPING.md                  v2: canonical FBref/StatsBomb source per feature
│   └── FEATURE_VALIDATION.md                   v2: feature feasibility vs StatsBomb Open Data
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

### 2026-08-13 — P9 complete: v2 visualization wired into `app.py` (branch `worktree-p8-bootstrap-stability`)
- **P9 RESOLVED:** new app-facing module **`v2_features.py`** (cached `load_v2_clustered_data` → fresh-fit `group_and_cluster`; `filter_v2_dataframe`; position-scoped `add_v2_percentiles`; `build_distribution_dataframe`; σ-space `build_player_radar_data`) + two new `charts.py` builders (`build_v2_distribution_chart`, `build_v2_archetype_radar_chart`). `app.py` gains a **sidebar dataset selector** (`st.sidebar.radio`, v2 default) that branches to the v2 `render_*` sections (table, archetype distribution, σ-radar playstyle explorer, position-scoped H2H) or falls through to the **byte-identical v1 body** (guarded by `st.stop()`). Recorded as **ADR-012**.
- **The "solve it in the UI" directive (from P8.1's findings):** the 5 unrepresented archetypes (Sweeper Keeper, Wingback, Box-to-Box Midfielder, Advanced Playmaker, Poacher) are surfaced via `st.info` in the distribution — never silently dropped; duplicate labels (Attacking Fullback ×2, Deep-Lying Playmaker ×2) are summed by label and the explorer keys on `(position_v2, cluster_id_v2)`; the radar is **σ-space** (standardized vs the archetype prototype), which also resolves the mixed-units problem.
- **Tests:** 13 new tests in `tests/test_v2_features.py` (filter, position-scoped percentiles, unrepresented archetypes, radar data, chart smoke). Full suite 126 passed + 1 pre-existing skip, ruff clean.
- **Docs updated:** `DECISIONS.md` ADR-012, `ARCHITECTURE.md` (tree + purpose table + §11), `STREAMLIT_GUIDELINES.md` §3, `TASK_BACKLOG.md` P9, `PROJECT_STATE.md`, this entry.

### 2026-08-13 — ST k-reduction (4→3) + Poacher retained-unpopulated (branch `worktree-p8-bootstrap-stability`)
- **ADR-011 RESOLVED:** P8's bootstrap exposed ST's over-split — k=4 on n=18 produced a 2-player Messi/Memphis micro-cluster and two clusters both labelled "False 9" (degen 0.39), while the 4th archetype (Poacher) never won a label (~6.3σ from Complete Forward, no WC 2022 striker fits it). Reduced `GROUP_K["ST"]` 4→3 → **ST = Complete Forward 10 / False 9 4 / Target Man 4**; ARI 0.454→0.526, degen 0.39→0.14. Poacher is **retained in the taxonomy but unpopulated** (owner decision: keep, don't drop) so the 20-archetype spec survives richer future data.
- **Tests:** `test_group_order_and_k` updated (ST 3); new `test_master_st_no_duplicate_label_no_micro_cluster` locks the fix. 26 engine tests; full suite 113 passed + 1 pre-existing skip (parser test needing gitignored `data/statsbomb/`), ruff clean.
- **Docs updated:** `PLAYSTYLE_SPEC.md` (Poacher note), `DECISIONS.md` ADR-011, `ARCHITECTURE.md` §11, `ML_GUIDELINES.md` §9, `PROJECT_STATE.md`, `TASK_BACKLOG.md` (P8.1), this entry.

### 2026-08-12 — P8 complete: bootstrap stability / refit-variance on the v2 engine (branch `worktree-p8-bootstrap-stability`)
- **P8 RESOLVED:** `v2_model_engine.py --evaluate` now runs `evaluate_bootstrap_stability` per `position_v2` group (after silhouette/DB). B=100 same-n bootstrap resamples per group; each refits the exact production preprocessing (`fillna(0) → StandardScaler → KMeans(k, random_state=42+B+b, n_init=10)`, resample via `np.random.default_rng(42+b)`) and predicts labels for **all original players**, scored by `adjusted_rand_score` vs the deployed partition. Reports mean ± std ARI (bootstrap stability), mean ± std refit silhouette/DB (refit-variance), and the degenerate fraction (full-n prediction collapsed to a ≤1-player cluster). Full-n predict chosen over co-membership / pairwise-ARI because with ST n=18, k=4 a cluster is absent from a bootstrap sample with ~e⁻¹ probability per player — sample-restricted ARI would be an apples-to-oranges k−1-vs-k comparison. Recorded as **ADR-010**.
- **Real-data snapshot (`--evaluate`, 217 players):** GK ARI 0.633±0.287 · degen 0.01 · CB 0.344±0.183 · 0.06 · FB/WB 0.203±0.129 · 0.17 · MF 0.354±0.142 · 0.12 · Wide 0.304±0.152 · 0.26 · ST 0.454±0.191 · 0.39. Confirms the expected story: low-silhouette groups (ST/Wide) are also the least stable — ST's 4-way split collapses a cluster in 39% of refits, so **ST/Wide archetype assignments are provisional** (reported as a limitation; candidate for k-reduction in a future phase, not a blocker — diagnostic, not gating, per ML_GUIDELINES §9).
- **Purely additive:** the deployed clustering / labels / k / feature set are unchanged (bootstrap runs only under `evaluate=True`; `--persist` refit uses `evaluate=False`). Locked by `test_bootstrap_integration_does_not_change_clustering`.
- **Tests:** 8 new engine tests (determinism, keys/ARI bounds, high stability on separable blobs, refit-variance finite, uniform-noise NOT falsely stable, integration no-op, small-group NaN, real-master runs). 25 v2 engine tests; full suite **112 passed + 1 pre-existing skip** (parser test needing gitignored `data/statsbomb/`), ruff clean.
- **Docs updated:** `TASK_BACKLOG.md` (P8 RESOLVED), `ARCHITECTURE.md` §11, `ML_GUIDELINES.md` §9+§10, `DECISIONS.md` ADR-010, `PROJECT_STATE.md`, this entry.

### 2026-08-12 — Phase B merged to main (owner approval)
- **Merge complete:** `statsbomb-parser` → `main` fast-forwarded (5 commits: `18ebbd5` · `8ec9b68` · `eecb0b3` · `6d0c564` · `caffe0e`); `main` = `origin/main` = `caffe0e`. Done from the isolated worktree via a temp-branch local ff-merge + push (`git push origin ff-merge-main:main`); the shared checkout's local `main` needs one `git pull` to catch up. `statsbomb-parser` kept in sync with `main`.
- **Next:** P8 (v2 evaluation: bootstrap stability) → P9 (v2 visualization + wire into `app.py`).

### 2026-08-12 — Review gate resolved: GK fallback label renamed "Traditional Goalkeeper" (branch `statsbomb-parser`)
- **Decision (owner):** "Mixed Profile" is not acceptable as a dominant user-facing output. The WC 2022 GK pool is genuinely homogeneous — 18/28 GKs exceed the archetype threshold — so the fallback is now per-group via `GROUP_FALLBACK_LABEL`: **GK → "Traditional Goalkeeper"**, other groups keep the honest "Mixed Profile" (their outliers number ≤2). Verified the quiet GK cluster really is the stay-at-home keeper: below-mean on saves (−0.49σ) and on *every* sweeping/distribution trait (passes −0.45σ, long passes −0.47σ, prog passes −0.49σ, sweeper clearances −0.45σ, def-actions-outside-box −0.28σ, deeper line +0.23σ). Output now **GK = Shot Stopper 10 · Traditional Goalkeeper 18**; MF keeps Mixed Profile 1 (its genuine outlier). A global rename would have mislabelled that MF outlier "Traditional Goalkeeper" — hence the per-group map, threaded through `_assign_labels_from_archetypes(fallback_label=...)`.
- **Persistence caveat:** model artifacts are invalidated only by dataset hash, so a label-constant change silently serves stale labels on `--persist` (hash unchanged). Fixed by clearing `models_v2/` and re-running `--persist`. A code-version in `metadata_v2.json` would prevent this — candidate improvement, not required now.
- **Tests:** 17 engine tests (new `test_gk_fallback_label_is_traditional_goalkeeper`; label provenance is now group-aware). 105/105 suite, ruff clean.

### 2026-08-12 — P7 complete: position-scoped KMeans engine + σ-offset archetype labeling (branch `statsbomb-parser`)
- **P7 RESOLVED:** `v2_model_engine.py` fits one KMeans per `position_v2` group (k=2/3/3/5/3/4, seed 42) and labels clusters against the 20 archetypes. Persistence to `models_v2/` (gitignored; per-group scaler/kmeans joblib, `cluster_labels_v2.json`, `metadata_v2.json` with SHA256). CLI `--persist`/`--evaluate` verified end-to-end — cache reload reproduces fresh-fit labels exactly.
- **Plan deviation (documented at the review gate):** the first fit labelled **all 217 players "Mixed Profile"**. Root cause: hand-authored raw-unit archetype vectors were 2–40σ off real centroids (e.g. `avg_def_position_y` −41σ on a near-constant column; the `absent→0.0` default on low-variance `pass_completion_pct` at −9.6σ). Fixed by rewriting `GROUP_ARCHETYPES` as **σ-offset profiles** (Important traits +2.0–2.5σ, else 0.0σ = group mean) + `_archetype_vectors_raw` + `_label_threshold(n)=3.5·√(n/6)`. This is the fix the plan's review gate deferred to the owner; it preserves the plan's architecture.
- **Bug caught by the new tests:** artifact filenames for `FB/WB` contained a `/`, so `Path / "FB/WB_scaler.joblib"` resolved to a non-existent `models_v2/FB/` dir → `--persist` would crash. Fixed with `_artifact_stem` (`FB_WB`).
- **Review-gate results (`--evaluate`, 217 players):** GK Shot Stopper 10 / **Mixed 18** (sil 0.195, DB 1.71); CB Ball-Playing 23 / Traditional 21 / Stopper 15 (0.091, 2.34); FB/WB Attacking 25 / Defensive 11 (0.063, 2.32); MF Deep-Lying 32 / Defensive Midfielder 21 / Mixed 1 / Shadow Striker 1 (0.091, 1.51); Wide Inverted 9 / Traditional 9 / Wide Playmaker 3 (0.122, 1.75); ST Complete Forward 9 / False 9 5 / Target Man 4 (0.146, 1.39). The GK 18/28 Mixed is **data-correct**, not a calibration failure — it matches v1's Phase 4C finding (this WC 2022 GK pool has no sweeper split; the quiet-GK cluster is genuinely 5.44σ from both prototypes vs threshold 5.15). MF singletons: Neymar → Shadow Striker (huge xG/SCA/shots — semantically right), c3 → honest Mixed outlier. Low silhouette is expected for high-dim small-n groups (ST 18×34, k=4) — flagged in the plan's Risks.
- **Tests:** 16 engine tests in `tests/test_v2_model_engine.py` (determinism, provenance, small-group guard, persistence roundtrip + hash-mismatch, no-streamlit import graph, real-master feature availability / data-fix bounds / non-degenerate labels). 104/104 full suite, ruff clean.
- **Docs updated:** `PROJECT_STATE.md` (P7 done, Phase 4 next), `ARCHITECTURE.md` §11 (P7 paragraph + design points), `TASK_BACKLOG.md` (V2-ML RESOLVED + review gate note), CLAUDE.md (this entry, commands, tree, dataset).

### 2026-08-12 — P6 complete: position-scoped features + position_v2 (branch `statsbomb-parser`)
- **P6 RESOLVED:** 23 locked event-derived features (passing, defending/duels, shots/xG/npxG, box/final-third touches, penalty GK) + `parse_lineups()`/`position_v2` (6 groups) → master **217 rows × 192 cols**. Data fixes: `conversion_pct` overflow (sh==0 → 0.0), `save_pct`/`shots_on_target_pct` guarded, `dribble_success_pct` added, fully-null `pkwon`/`pkcon` dropped.
- **Correctness fix in `parse_lineups`:** the final-whistle clock is read from the match's events file (`max(minute*60 + second)` — official match clock, exact through stoppage; event `timestamp` resets at halftime and must NOT be used), falling back to max explicit lineup endpoint only if events missing. The old lineups-only approach undercounted the match end by a ~9 min median, which CAN flip duration-weighted position assignments (MF 56→55, ST 17→18). Regression test: `test_parse_lineups_final_whistle_from_events`.
- **position_v2 real distribution (authoritative):** GK=28, CB=59, FB/WB=36, MF=55, Wide=21, ST=18 (sums to 217; supersedes the plan's 28/59/35/54/22/19 and pre-fix 28/59/36/56/21/17). Rodri = CB is data-correct (played RCB in all 4 Spain matches).
- **New modules/columns:** `P6_COUNT_FEATURES`/`P6_RAW_KEYS`/`P6_MASTER_COLUMNS` (23), `_P6_COUNT_MAP` (17), `_P6_GK_COLUMNS=("penalty_save_pct",)`, `parse_lineups` (829 rows), `merge_position_v2`. P3 contract untouched (18/7/21).
- **Docs updated:** `PROJECT_STATE.md` (P6 row, 217×192, next = P7–P9), `ARCHITECTURE.md` §11, `TASK_BACKLOG.md` (V2-DATA extended to P3+P6; DATA-01 SUBSMED), `DATA_SOURCE_MAPPING.md` (22 rows → StatsBomb canonical), `FEATURE_VALIDATION.md` (status flips + P6 Implementation Notes). Spec's 2 missing striker archetypes (Complete Forward, False 9) landed at commit `18ebbd5` (20/20).
- **Tests:** 52 parser tests, 88/88 full suite, ruff clean.

### 2026-08-12 — Phase A: v2 design docs committed, main test suite complete
- **Committed:** `PLAYSTYLE_SPEC.md`, `DATA_SOURCE_MAPPING.md`, `FEATURE_VALIDATION.md` moved from untracked repo-root files into `docs/01-product/` (docs taxonomy). `PROJECT_STATE.md` references retargeted to `01-product/...`.
- **Main checkout now self-sufficient:** `data/statsbomb/` downloaded there too → `pytest` runs 71/71 (no skip) in both checkouts.
- **Left untouched:** pre-existing uncommitted working-tree deletions of `V1_READINESS_ASSESSMENT.md` and `docs/README.md` in the shared checkout — not part of this change.

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