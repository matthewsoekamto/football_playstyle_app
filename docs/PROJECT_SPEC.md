# PROJECT SPEC
### Football Playstyle Clustering App

Authority: subordinate to `PROJECT_CONSTITUTION.md`. Describes *what the product is*, not *how the code must be written*.

---

## 1. Purpose

Answer a question standard stat sites don't answer well: **"what kind of player is this, stylistically?"** Goals and assists tell you outcomes; this app clusters players on rate-based behavioral stats (shots, crosses, tackles, interceptions, saves — all per 90 minutes) to answer the style question, and gives fans, analysts, and recruiters a way to browse, filter, and compare players through that lens.

## 2. Goals

- Provide an instant, no-signup, single-page way to explore ~2,183 qualifying players (2,839 raw rows, filtered to `Min >= 270`) across the five biggest European leagues.
- Make unsupervised ML output *legible* — a cluster ID like `3` is worthless to a fan; "Creative Playmakers" is not.
- Support direct player-vs-player comparison with position-aware stats.
- Surface statistical outliers (the scatter plot's "elite outlier" framing) as a discovery mechanism, not just a filter mechanism.

## 3. Target Users

| User | What they want from the app |
|---|---|
| Football fan / hobbyist analyst | Browse and discover: "who plays like Player X?" |
| Data/ML portfolio reviewer | Evidence of clean pipeline design, honest clustering, and a working deployed app |
| Scout / recruitment analyst (aspirational, not yet served) | Position-scoped, statistically grounded shortlists |
| Future contributor (human or AI agent) | A codebase and doc set clear enough to extend safely |

## 4. Current Capabilities (as of this snapshot)

Confirmed by direct inspection of `app.py`, `data_loader.py`, `model_engine.py`, `features.py`, `charts.py`:

- **Data ingestion & cleaning** (`data_loader.load_and_clean_data`): loads `players_data_light-2025_2026.csv` (2,839 rows × 53 raw FBref-style columns), normalizes column names, filters to players with ≥270 minutes played (2,183 remain), derives `primary_position` from the first token of the (possibly multi-valued, e.g. `"MF,FW"`) `Pos` column, and computes per-90 rate stats for six outfield stats and three goalkeeper stats.
- **Clustering** (`model_engine.group_players`): two independent K-Means models — 5 clusters for outfield players on 6 features, 2 clusters for goalkeepers on 4 features — each with `StandardScaler` and `random_state=42` for reproducibility. Cluster centroids are matched to one of 7 hand-authored archetype definitions (5 outfield, 2 GK) to produce human-readable playstyle labels.
- **Feature/percentile layer** (`features.py`): position-scoped percentiles for comparison stats, position-aware stat sets for head-to-head comparison, filtering by league/position/squad/playstyle, and display-table formatting with friendly column names.
- **Visualization** (`charts.py`): a distribution bar chart of playstyle counts, a radar chart per playstyle centroid, a z-score-based "elite outlier" scatter plot (top 100 by combined outlier score, top 15 labeled), and a head-to-head percentile radar.
- **UI** (`app.py`): sidebar filters (league, position, squad, playstyle), accent-insensitive name search, a sortable results table, the Playstyle Explorer, the scatter plot, and the head-to-head comparison tool — all on one page, cached with `st.cache_data`.
- **Standalone data-collection script** (`fetch_possession_stats.py`): scrapes FBref's Big-5-leagues possession table into a CSV. **Not currently wired into the app** — its output is not consumed by `data_loader.py` or any other module.

## 5. Future Capabilities (Roadmap-Level — see `TASK_BACKLOG.md` for execution detail)

- Multi-season support (season selector instead of a hardcoded filename).
- Integrating possession/passing/progression stats (the natural next step for `fetch_possession_stats.py`) into the clustering feature set.
- Persisted, versioned model artifacts instead of recompute-on-cold-cache.
- Automated testing and CI.
- Optional: saved/shareable comparisons, CSV export of filtered views.

## 6. Out of Scope (Explicitly, For Now)

- **User accounts / authentication.** No user data is stored; nothing requires login.
- **Live/in-match data.** The dataset is season-aggregate stats, not live feeds.
- **Predictive modeling** (e.g. predicting future performance, transfer value, injury risk). This is a descriptive clustering tool, not a forecasting tool — conflating the two would misrepresent what K-Means output means.
- **Automated scraping in production.** `fetch_possession_stats.py` is explicitly a *local, manual* script (its own docstring says "Run this script locally"); the deployed Streamlit app must never perform live scraping of a third-party site at request time.
- **Mobile-native app.** Streamlit's responsive layout is the only supported surface.

## 7. Constraints

- **Data constraint**: the app is only as good as one CSV snapshot; there is no update mechanism today beyond manually replacing the file.
- **Deployment constraint**: designed for Streamlit Community Cloud (per `README.md`) — single-process, no background workers, no persistent database.
- **Minutes-played constraint**: the `Min >= 270` cutoff (three full matches) is a deliberate small-sample-size guard baked into `data_loader.py`; any change to this threshold is a product decision, not a bugfix, and must go through `DECISIONS.md`.
- **License/ToS constraint**: FBref data usage via scraping (`fetch_possession_stats.py`) must remain manual, low-frequency, and rate-limited (the existing `time.sleep(3)` is the minimum courtesy, not a ceiling).

## 8. Assumptions

- The uploaded CSV will continue to follow FBref's Big-5-leagues export shape (comma-flattened multi-index columns, `Player`/`Pos`/`Squad`/`Comp`/`Min`/`90s` present).
- "Playstyle" is understood by users as a descriptive/statistical label, not a scouting-grade tactical assessment.
- A player's `primary_position` (first listed position) is an acceptable simplification for clustering and percentile scoping, even though many players are genuinely multi-positional (e.g. 217 players are listed as `"MF,FW"`).
- Streamlit's single-page rerun model is acceptable UX for this feature set; no page-based navigation is required yet.

## 9. Success Criteria

- A new visitor can go from landing on the page to understanding a specific player's playstyle and comparing them to another player in under two minutes, with no explanation needed.
- Cluster labels remain stable and sensible run-to-run (guaranteed today by `random_state=42`).
- The app has zero unhandled exceptions surfaced to the end user under normal filter/search interactions.
- The documentation set in `/docs` remains accurate enough that a new AI agent or engineer can make a correct first contribution without needing to ask clarifying questions about *why* the code is shaped the way it is.
