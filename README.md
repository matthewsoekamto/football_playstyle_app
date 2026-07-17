# Football Playstyle App

A Streamlit dashboard that clusters football players into human-readable playstyles using per-90 performance stats and K-Means clustering.

## Features

- **Playstyle clustering** for outfield players (5 archetypes) and goalkeepers (2 archetypes)
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
| `model_engine.py` | K-Means clustering and playstyle labeling |
| `features.py` | Filters, percentiles, position stat sets |
| `charts.py` | Plotly chart builders |

## Data

The bundled CSV contains player season stats from five leagues (Premier League, La Liga, Serie A, Bundesliga, Ligue 1). Players with fewer than 270 minutes played are excluded.

## Deploy

To deploy on [Streamlit Community Cloud](https://streamlit.io/cloud):

1. Push this repo to GitHub
2. Connect the repo in Streamlit Cloud
3. Set the main file to `app.py`
4. Ensure `requirements.txt` is at the repo root

## Development

Run clustering standalone:

```bash
python model_engine.py
```

Run data loading standalone:

```bash
python data_loader.py
```
