# PROJECT_STATE.md

> Single-source-of-truth snapshot of the Football Playstyle Clustering App. Updated 2026-08-07.

---

## Project Vision

**Version 2 replaces the original feature-light clustering system with a position-aware playstyle engine.**

Core principles:
- Position-specific clustering
- Hybrid FBref + StatsBomb features
- Explainable archetypes
- Reproducible feature engineering
- Event-derived advanced metrics

**Principle (revised at P6): When a feature exists in both FBref and StatsBomb, the source actually present in the v2 master is canonical.** The v2 download only includes the FBref standard/shooting/miscellaneous/GK tables, so passing, defending, possession and xG-family features default to StatsBomb (P6 event-derived); FBref remains canonical where its tables exist (Gls, Ast, Saves, Save%, Int, TklW, carries, dribbles, crosses, fouls).

---

## Core Design Documents

| Document | Purpose |
|---|---|
| `01-product/PLAYSTYLE_SPEC.md` | Canonical definition of all 20 archetypes |
| `01-product/FEATURE_VALIDATION.md` | Validation of every feature against StatsBomb Open Data |
| `01-product/DATA_SOURCE_MAPPING.md` | Defines the canonical source of every feature (FBref vs StatsBomb) |

---

## Design Constraints

- Every feature has exactly one canonical data source
- Every metric must be reproducible from publicly available datasets
- Position groups are clustered independently
- No commercial APIs or proprietary data
- All feature engineering must be deterministic

---

## v1 (Legacy)

- **Status:** Archived — Feature Complete + Production Ready
- **Tag:** `v1.0` (commits `473a579` / `f2cfc4c`, 2026-07-27)
- **Dataset:** 2025/26 Big 5 leagues FBref (`players_data_light-2025_2026.csv`)
- **Archetypes:** 8 outfield + 2 GK (Option C)
- **Architecture:** 5-module pipeline over single CSV

### Completed (v1)

| Item | Description |
|---|---|
| **v1.0 Release** | Feature Complete + Production Ready |
| **Option C** | 8 outfield archetypes, non-greedy labeling, shared labels allowed |
| **ML-01** | Archetype-matching scaler fragility fixed (player-level scaler) |
| **ML-02** | Position-scoped percentiles (NaN for irrelevant stats) |
| **ML-03** | Model persistence (joblib + metadata JSON, hash invalidation) |
| **ML-04** | Clustering evaluation metrics (silhouette, Davies-Bouldin) |
| **CI-01** | CI pipeline (ruff + pytest on push/PR) |
| **DEP-01** | Dependency upper bounds + lockfile + `models/` gitignore |
| **STYLE-02** | Remove dead `fetch_possession_stats.py` |
| **Post-v1 lint/CI** | Ruff fixes, import sorting, unused import removal |

---

## v2 (Current Development)

**Status:** Active — Phase 4: Evaluation (P8) scheduled

### Current Phase

**Phase 3 — Position-Scoped KMeans Engine (P7) ✅ complete.**

One KMeans per position group is fit on the P6 master, clusters labeled against the 20 σ-offset archetypes, and the fitted scalers/centroids/labels persisted to `models_v2/` (SHA256-invalidated). `v2_model_engine.py` is headless (no streamlit import).

**P1–P7 (data pipeline + feature engineering + clustering) complete.** The StatsBomb event parser (P3) landed at `7ccb424`; the V3-corrected FBref↔StatsBomb build (P1/P2/P4/P5) landed at `59ef406`; P6 position-scoped feature engineering + `position_v2` and the P7 engine + GK label rename landed on branch `statsbomb-parser` (merged to `main` at `caffe0e`). `data/wc2022_players_master.csv` is 217 rows × 192 cols (146 pre-P3 + 21 P3 + 23 P6 event-derived + 2 identity columns incl. `position_v2`). Remaining: **P8–P9** (evaluation, visualization).

### Branch / merge status

- **Phase B is merged into `main` (2026-08-12).** `statsbomb-parser` was fast-forwarded to `main` as 5 commits (`18ebbd5` · `8ec9b68` · `eecb0b3` · `6d0c564` · `caffe0e`); `main` = `origin/main` = `caffe0e`. The `statsbomb-parser` branch is kept in sync with `main`.
- **Next: P8** (v2 evaluation: bootstrap stability) → **P9** (v2 visualization + wire into `app.py`).

### Goal

Rebuild the entire playstyle engine around the FIFA World Cup 2022 dataset using a hybrid FBref + StatsBomb architecture.

### Target Archetypes (20 total)

| Position Group | Archetypes |
|---|---|
| Goalkeepers | 2 |
| Centre-backs | 3 |
| Full-backs | 3 |
| Midfielders | 5 |
| Wide players | 3 |
| Strikers | 4 |

### Architecture (Target)

```
FBref CSVs                    StatsBomb Open Data
      │                              │
      ▼                              ▼
FBref Loader                StatsBomb Parser
      │                              │
      └──────────────┬───────────────┘
                     ▼
           Feature Engineering
      (position-scoped feature sets)
                     │
                     ▼
              Merge Engine
      (FBref + StatsBomb feature join)
                     │
                     ▼
         wc2022_players_master.csv
                     │
                     ▼
              data_loader.py
                     │
                     ▼
         model_engine.py
      (position-scoped KMeans)
                     │
                     ▼
           Streamlit App
```

### Data Sources

| Source | Scope | Files |
|---|---|---|
| **FBref** | Canonical season statistics | `wc2022_standard.csv` (688), `wc2022_shooting.csv` (688), `wc2022_miscellaneous.csv` (688), `wc2022_players.csv` (476 — intermediate player-level dataset used during v2 development, not the final canonical dataset), `wc2022_gk.csv` (46) |
| **StatsBomb** | Event-level enrichment | `events/`, `lineups/`, `matches/` (Open Data) |

**Output:** `wc2022_players_master.csv` — unified feature matrix for clustering.

### Completed (v2)

| Item | Description |
|---|---|
| **01-product/PLAYSTYLE_SPEC.md** | Canonical 20-archetype definitions |
| **01-product/FEATURE_VALIDATION.md** | Feature-by-feature validation against StatsBomb Open Data |
| **01-product/DATA_SOURCE_MAPPING.md** | Canonical source assignment for every feature (FBref vs StatsBomb) |
| **Project architecture defined** | Position-scoped clustering, hybrid sourcing, deterministic pipeline |
| **P1–P2 (FBref schema + loader/merger)** | V3-corrected FBref build (`59ef406`) |
| **P3 (StatsBomb parser)** | `statsbomb_parser.py` → 21 locked event-derived features (`7ccb424`); downloader `scripts/download_statsbomb.py` |
| **P4 (player matching)** | FBref↔StatsBomb identity bridge (name+squad, `normalize_name`) in `build_master_dataset.py` |
| **P5 (merge dataset)** | `data/wc2022_players_master.csv` — 217 rows × 167 cols |
| **P6 (position-scoped features)** | 23 more event-derived features (passing, defending, duels, shots/xG/npxG, box/final-third touches, penalties) + `parse_lineups`/`position_v2` (6 groups from StatsBomb lineups) → master 217 × 192; data fixes (`conversion_pct` overflow, `dribble_success_pct`, dropped `pkwon`/`pkcon`) |
| **P7 (position-scoped KMeans)** | `v2_model_engine.py` (headless): per-group KMeans (k=2/3/3/5/3/4), σ-offset archetype labeling vs the 20 archetypes, `models_v2/` persistence (SHA256-invalidated, `_artifact_stem` sanitizes the `FB/WB` group name). Engine tests in `tests/test_v2_model_engine.py` (16 tests) |

### Success Criteria (v2 Complete)

- ✓ Unified player dataset generated (`wc2022_players_master.csv`)
- ✓ All validated features available (target: 62)
- ✓ 20 archetypes successfully clustered
- ✓ Stable clustering metrics (silhouette, Davies-Bouldin, bootstrap stability)
- ✓ Interactive visualization complete (position-aware radar, distribution, H2H)

### Next Tasks (v2 — Phase 3 onward)

#### Data — ✅ DONE (P1–P6)
P1–P5 complete: FBref schema validated, loader/merger built (`59ef406`), StatsBomb parser (`7ccb424`), player matching, and merge into `data/wc2022_players_master.csv`. P6 complete (branch `statsbomb-parser`): 23 more event-derived features + `position_v2` (most-played StatsBomb lineup position → GK/CB/FB-WB/MF/Wide/ST) → master 217 rows × 192 cols. **position_v2 distribution: GK=28, CB=59, FB/WB=36, MF=55, Wide=21, ST=18** (all 217 resolve; every group ≥ its k).

#### Next (in order)
| Priority | Task | Effort | Where |
|---|---|---|---|
| **P8** | Evaluation (silhouette, DB, **bootstrap stability**) on the v2 engine | ~1 day | `TASK_BACKLOG.md` P8 |
| **P9** | Visualization updates + wire v2 clustering into `app.py` | ~2 days | `TASK_BACKLOG.md` P9 |

---

## Known Decisions (v2)

| Decision | Summary |
|---|---|
| **Position-scoped clustering** | One KMeans per position group (GK, CB, FB, CM, Wide, ST) — not global outfield/GK split |
| **Hybrid feature sourcing** | Each feature assigned to FBref or StatsBomb as canonical source (`01-product/DATA_SOURCE_MAPPING.md`) |
| **Event-derived metrics** | Progressive carries, pressures, pass types from StatsBomb events — not just summary tables |
| **Archetype definitions first** | `01-product/PLAYSTYLE_SPEC.md` drives feature selection, not vice versa |
| **WC 2022 as dev dataset** | Single tournament, complete event data available via StatsBomb Open Data |

---

## Future (v3+)

- Club seasons (multi-season support)
- Multiple competitions
- Temporal playstyle evolution
- Transfer learning across leagues/competitions

---

*Updated 2026-08-12: P1–P7 complete and merged to `main` (`caffe0e`). Next update when P8–P9 land.*