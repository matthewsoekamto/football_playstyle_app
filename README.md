# Football Playstyle Explorer

A portfolio-grade Streamlit dashboard that clusters footballers into human-readable **playstyle archetypes** from real event data, then lets you explore them through percentile radars, player dossiers, and head-to-head comparisons.

Built on the **2022 World Cup** (StatsBomb Open Data + FBref), with a legacy Big-5-leagues view.

## What it does

From per-90 performance and event-derived stats, the app fits a **position-scoped K-Means** model and labels every cluster against a hand-authored taxonomy of **20 archetypes** — "Deep-Lying Playmaker", "Inverted Winger", "False 9", "Target Man", and more. You can:

- **Search any player** (autocomplete) and read a full dossier: position, archetype, percentile radar, and how they rank on every key stat against their position group.
- **Browse the 20 archetypes** — what each one means and which players are closest to it.
- **Compare two players** head-to-head with position-scoped percentiles.
- **See the distribution** of players across archetypes and position groups.

## Quick start

```bash
pip install -r requirements.txt
streamlit run app.py
```

The World Cup 2022 dataset is bundled in `data/wc2022_players_master.csv` (217 players), so it runs out of the box. Switch to the legacy Big-5 view from the ⚙️ Settings menu.

## Tech stack

| Area | Tools |
|---|---|
| Language | Python 3.10+ |
| App / UI | Streamlit + custom CSS theming |
| Data | pandas, NumPy |
| ML | scikit-learn (K-Means, StandardScaler, silhouette / Davies-Bouldin / adjusted-Rand) |
| Visualization | Plotly |
| Persistence | joblib + SHA256-validated metadata |
| Data sources | StatsBomb Open Data (events, lineups), FBref |
| Testing / lint | pytest, ruff |
| CI | GitHub Actions |

## Skills demonstrated

This project was built as a portfolio-grade demonstration of production data/ML engineering. Concretely, it exercises:

**Data engineering**
- End-to-end ETL: raw StatsBomb event JSON + FBref CSVs → a clean **217-row × 193-column** master dataset.
- **44 event-derived features** engineered from raw match events (pressures, recoveries, duels, shots/xG, passes, touches-by-zone), normalized per-90.
- Defensive data cleaning: per-90 normalization, percentage-vs-count handling, div-by-zero/overflow guards, missing-value policy, column normalization.

**Machine learning**
- Deliberate, documented unsupervised methodology: **position-scoped K-Means** (one model per position group), `StandardScaler` standardization, fixed k driven by the product taxonomy, seeded (`random_state=42`) for full reproducibility.
- Interpretable **archetype labeling** via σ-offset prototypes with a dimension-aware threshold — not black-box cluster IDs.
- Evaluation beyond scores: silhouette + Davies-Bouldin **and** **bootstrap stability** (adjusted Rand index) to quantify how trustworthy the partition is, including a small-sample degeneracy guard.
- Model persistence with dataset-hash invalidation, plus a **headless engine** (`--persist` / `--evaluate`) cleanly separated from the UI.

**Visualization & UX**
- Interactive Plotly dashboards: faceted distributions, percentile radar charts, horizontal percentile bars, player comparison.
- Modern dashboard UX: dark theme, KPI strip, tabbed/progressive-disclosure navigation, autocomplete search, nationality flags.

**Software engineering**
- Clean modular architecture with strict one-way dependency direction and a UI-independent ML engine.
- **130+ unit tests** locking contracts (data pipeline, determinism, persistence round-trip, archetype maps).
- CI (ruff + pytest on every push), linting, and a documented decision log (ADRs) + project constitution.

## Architecture

```
FBref CSVs  +  StatsBomb Open Data (events, lineups)
        │
        ▼
statsbomb_parser.py      → 44 event-derived features + position
build_master_dataset.py  → data/wc2022_players_master.csv (217 × 193)
        │
        ▼
v2_model_engine.py       → per-position K-Means + 20 σ-offset archetypes (headless)
        │
        ▼
v2_features.py           → app-facing load / filter / percentile / radar helpers
app.py + charts.py       → Streamlit UI + pure Plotly figures
```

| File | Purpose |
|---|---|
| `app.py` | Streamlit UI, navigation, sections |
| `v2_features.py` | v2 load / filter / display / radar helpers |
| `v2_model_engine.py` | headless position-scoped clustering engine |
| `statsbomb_parser.py` | StatsBomb events + lineups → features + position |
| `build_master_dataset.py` | FBref + StatsBomb → master dataset |
| `charts.py` | pure Plotly figure builders |
| `features.py` / `model_engine.py` / `data_loader.py` | v1 legacy app |

## ML methodology

1. Standardize each position group's features (`StandardScaler`).
2. Fit K-Means per group (k = 2/3/3/5/3/3 for GK / CB / FB-WB / MF / Wide / ST).
3. Match each cluster centroid to the nearest σ-offset archetype prototype.
4. Evaluate with silhouette + Davies-Bouldin, plus bootstrap ARI stability.

Every stochastic step is seeded, so results are reproducible run-to-run.

## Dataset

- **v2 (default):** FIFA World Cup 2022 — 217 players, 193 features, 6 position groups, 20 archetypes.
- **v1 (legacy):** Big-5 European leagues (2025/26) — 2,183 players, 10 archetypes.

## Testing & CI

```bash
python -m pytest tests/ -v
ruff check .
```

CI runs linting + the full suite on every push to `main`.

## Limitations

- The v2 build uses a single tournament, so a few archetypes are unrepresented and small position groups are less stable — quantified and documented via the bootstrap evaluation.
- v1 (legacy) lacks progressive-carrying/dribbling data, which limits separation of some attacking playstyles.
