# PROJECT_STATE.md

> Single-source-of-truth snapshot of the Football Playstyle Clustering App. Updated 2026-07-28.

---

## Project Vision

**Version 2 replaces the original feature-light clustering system with a position-aware playstyle engine.**

Core principles:
- Position-specific clustering
- Hybrid FBref + StatsBomb features
- Explainable archetypes
- Reproducible feature engineering
- Event-derived advanced metrics

**Principle: When a feature exists in both FBref and StatsBomb, FBref is the canonical source. StatsBomb is only used to supply metrics unavailable in FBref.**

---

## Core Design Documents

| Document | Purpose |
|---|---|
| `PLAYSTYLE_SPEC.md` | Canonical definition of all 20 archetypes |
| `FEATURE_VALIDATION.md` | Validation of every feature against StatsBomb Open Data |
| `DATA_SOURCE_MAPPING.md` | Defines the canonical source of every feature (FBref vs StatsBomb) |

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

**Status:** Active — Phase 2: Data Pipeline Implementation

### Current Phase

**Phase 2 — Data Pipeline Implementation**

Current objective: Build the hybrid FBref + StatsBomb dataset that powers the new clustering engine.

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
| **PLAYSTYLE_SPEC.md** | Canonical 20-archetype definitions |
| **FEATURE_VALIDATION.md** | Feature-by-feature validation against StatsBomb Open Data |
| **DATA_SOURCE_MAPPING.md** | Canonical source assignment for every feature (FBref vs StatsBomb) |
| **Project architecture defined** | Position-scoped clustering, hybrid sourcing, deterministic pipeline |

### Success Criteria (v2 Complete)

- ✓ Unified player dataset generated (`wc2022_players_master.csv`)
- ✓ All validated features available (target: 62)
- ✓ 20 archetypes successfully clustered
- ✓ Stable clustering metrics (silhouette, Davies-Bouldin, bootstrap stability)
- ✓ Interactive visualization complete (position-aware radar, distribution, H2H)

### Next Tasks (v2 — Phase 2)

#### Data
| Priority | Task | Effort |
|---|---|---|
| **P1** | Validate FBref schema | ~1 day |
| **P2** | Build FBref loader/merger | ~2 days |
| **P3** | Build StatsBomb parser | ~3 days |
| **P4** | Player matching (FBref ↔ StatsBomb) | ~2 days |

#### ML
| Priority | Task | Effort |
|---|---|---|
| **P5** | Merge dataset → `wc2022_players_master.csv` | ~1 day |
| **P6** | Feature engineering (position-scoped) | ~2 days |
| **P7** | Cluster redesign (position-scoped KMeans) | ~3 days |

#### Application
| Priority | Task | Effort |
|---|---|---|
| **P8** | Evaluation (silhouette, DB, stability) | ~1 day |
| **P9** | Visualization updates | ~2 days |

---

## Known Decisions (v2)

| Decision | Summary |
|---|---|
| **Position-scoped clustering** | One KMeans per position group (GK, CB, FB, CM, Wide, ST) — not global outfield/GK split |
| **Hybrid feature sourcing** | Each feature assigned to FBref or StatsBomb as canonical source (`DATA_SOURCE_MAPPING.md`) |
| **Event-derived metrics** | Progressive carries, pressures, pass types from StatsBomb events — not just summary tables |
| **Archetype definitions first** | `PLAYSTYLE_SPEC.md` drives feature selection, not vice versa |
| **WC 2022 as dev dataset** | Single tournament, complete event data available via StatsBomb Open Data |

---

## Future (v3+)

- Club seasons (multi-season support)
- Multiple competitions
- Temporal playstyle evolution
- Transfer learning across leagues/competitions

---

*Next update: when P1–P3 complete and `wc2022_players_master.csv` lands.*