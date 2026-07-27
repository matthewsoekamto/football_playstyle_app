# Football Playstyle App

A Streamlit dashboard that clusters football players into human-readable playstyles using per-90 performance stats and K-Means clustering.

## Features

- **Playstyle clustering** for outfield players (8 archetypes) and goalkeepers (2 archetypes)
- **Sidebar filters** by league, position, squad, and playstyle
- **Playstyle Explorer** with distribution chart, centroid radar, and representative players
- **Elite outlier scatter plot** colored by playstyle
- **Head-to-head comparison** with position-aware stats and position-scoped percentiles

## Requirements

- Python 3.10+
- Dependencies listed in `requirements.txt`

## Setup

```bash
pip install -r requirements.txt
```

Place the dataset `players_data_light-2025_2026.csv` in the project root (included in this repo).

## Run locally

```bash
streamlit run app.py
```

The app opens at `http://localhost:8501`.

## Project structure

| File | Purpose |
|------|---------|
| `app.py` | Streamlit UI |
| `data_loader.py` | CSV loading, cleaning, per-90 feature derivation |
| `model_engine.py` | K-Means clustering, playstyle labeling, **model persistence** |
| `features.py` | Filters, percentiles, position stat sets |
| `charts.py` | Plotly chart builders |

## Dataset

The application uses a processed dataset containing player season statistics from Europe's Big Five leagues:

- Premier League
- La Liga
- Serie A
- Bundesliga
- Ligue 1

Only players with at least 270 minutes played are included to improve clustering stability.

## Clustering Pipeline

1. Load and clean player statistics
2. Compute per-90 features
3. Separate outfield players and goalkeepers
4. Standardize features
5. Cluster players using K-Means
6. Assign human-readable playstyle labels
7. Visualize results in Streamlit

## Development

Run clustering standalone (with evaluation metrics):

```bash
python model_engine.py
```

Run data loading standalone:

```bash
python data_loader.py
```

Run tests:

```bash
python -m pytest tests/ -v
```

## CI

[![CI](https://github.com/matthew/football-playstyle-app/actions/workflows/ci.yml/badge.svg)](https://github.com/matthew/football-playstyle-app/actions/workflows/ci.yml)

Every push runs linting (ruff) and the full test suite.

## Model Persistence

The app persists fitted `StandardScaler` + `KMeans` models to `models/` (gitignored) with metadata (dataset SHA256, row count, fit timestamp, library versions). On cold start, it loads persisted artifacts instead of refitting when the dataset hasn't changed — enabling fast startup and auditability.

**The `models/` directory is auto-generated.** If no artifacts exist, the app fits a new model on first run and saves them. A fresh clone works immediately without these files.

To explicitly fit and persist:

```bash
python model_engine.py --persist
```
## Tech Stack

- Python
- Streamlit
- Pandas
- NumPy
- Scikit-learn
- Plotly
- Pytest
- Ruff

## Deploy

To deploy on [Streamlit Community Cloud](https://streamlit.io/cloud):

1. Push this repo to GitHub
2. Connect the repo in Streamlit Cloud
3. Set the main file to `app.py`
4. Ensure `requirements.txt` is at the repo root

## Current Limitations

The current clustering model is trained using six outfield performance features.
Because progression and dribbling statistics (e.g. carries, progressive carries,
take-ons) are unavailable in the source dataset, some attacking playstyles
cannot yet be distinguished reliably.

These richer event-based features are planned for a future iteration.