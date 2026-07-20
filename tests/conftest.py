"""Shared test fixtures for the Football Playstyle App.

Provides a small synthetic CSV fixture covering:
- Goalkeepers (2)
- Outfield players across multiple positions (DF, MF, FW)
- Multi-position player (MF,FW)
- Duplicate player name (different squads)
- Player below the Min>=270 filter threshold (should be excluded)
- Player at exactly 270 minutes (boundary case)
- Player with 90s=0 (division-by-zero guard)
"""

import tempfile
import os
import pandas as pd
import pytest


FIXTURE_COLUMNS = [
    "Rk", "Player", "Pos", "Squad", "Comp",
    "Min", "90s",
    "Gls", "Ast", "Sh", "SoT", "Crs", "TklW", "Int",
    "Saves", "Save%", "CS",
]

FIXTURE_ROWS = [
    # GK — traditional shot-stopper profile
    [1, "Alice Keeper",   "GK",      "Arsenal", "eng Premier League",
     1500, 16.7, 0, 0, 0, 0, 0, 0, 2, 45, 78.0, 5],
    # Outfield DF — defensive, high tackles/interceptions
    [2, "Bob Defender",   "DF",      "Arsenal", "eng Premier League",
     1400, 15.6, 1, 2, 10, 4, 30, 25, 20, None, None, None],
    # Outfield MF — creative, balanced
    [3, "Carol Midfielder", "MF",    "Arsenal", "eng Premier League",
     1300, 14.4, 4, 6, 20, 8, 25, 15, 12, None, None, None],
    # Outfield FW — goalscorer, high shots
    [4, "Dan Forward",    "FW",      "Chelsea", "eng Premier League",
     1000, 11.1, 12, 3, 45, 18, 5, 3, 2, None, None, None],
    # Multi-position winger (MF,FW)
    [5, "Eve Winger",     "MF,FW",   "Chelsea", "eng Premier League",
     900, 10.0, 5, 4, 25, 9, 15, 5, 3, None, None, None],
    # Duplicate name, different squad
    [6, "Bob Defender",   "DF",      "Liverpool", "eng Premier League",
     800, 8.9, 1, 1, 8, 3, 20, 20, 18, None, None, None],
    # Below Min>=270 threshold — should be filtered out
    [7, "Frank Fodder",   "MF",      "Chelsea", "eng Premier League",
     100, 1.1, 0, 0, 5, 1, 3, 2, 1, None, None, None],
    # Exactly at 270 minute boundary
    [8, "Grace Boundary", "DF",      "Liverpool", "eng Premier League",
     270, 3.0, 0, 0, 2, 0, 5, 8, 6, None, None, None],
    # Zero 90s — tests division-by-zero guard in _add_per90_rates
    [9, "Henry Zero",     "FW",      "Arsenal", "eng Premier League",
     300, 0.0, 2, 1, 15, 6, 2, 1, 1, None, None, None],
    # GK — sweeper profile (high interceptions)
    [10, "Irene Sweeper", "GK",      "Liverpool", "eng Premier League",
     1200, 13.3, 0, 0, 0, 0, 0, 0, 10, 30, 72.0, 3],
]


@pytest.fixture
def fixture_csv_path():
    """Write the synthetic fixture to a temporary CSV and return the path.

    Cleans up the temp file after the test completes.
    """
    df = pd.DataFrame(FIXTURE_ROWS, columns=FIXTURE_COLUMNS)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, encoding="utf-8",
    ) as f:
        df.to_csv(f.name, index=False)
        temp_path = f.name

    yield temp_path

    os.unlink(temp_path)


@pytest.fixture
def cleaned_fixture_df():
    """Return a small DataFrame that mimics the shape and columns of
    the cleaned + clustered output, without actually running clustering.

    This fixture is for tests in test_features.py and test_charts.py
    that only need a DataFrame with the right column names and dtypes,
    not actual cluster assignments.
    """
    df = pd.DataFrame({
        "player": ["Alice", "Bob", "Carol", "Dan"],
        "player_label": ["Alice", "Bob", "Carol", "Dan"],
        "squad": ["Arsenal", "Chelsea", "Arsenal", "Liverpool"],
        "comp": ["eng Premier League"] * 4,
        "primary_position": ["GK", "DF", "MF", "FW"],
        "Playstyle": ["Shot-Stoppers", "Defensive Rotators",
                      "Creative Playmakers", "Elite Finishers"],
        "gls": [0, 1, 4, 12],
        "ast": [0, 2, 6, 3],
        "sh": [0, 10, 20, 45],
        "tklw": [0, 25, 15, 3],
        "int": [2, 20, 12, 2],
        "gls_p90": [0.0, 0.06, 0.28, 1.08],
        "ast_p90": [0.0, 0.13, 0.42, 0.27],
        "sh_p90": [0.0, 0.64, 1.39, 4.05],
        "saves": [45, None, None, None],
        "saves_p90": [2.69, 0.0, 0.0, 0.0],
        "save%": [78.0, None, None, None],
        "save%_percentile": [100.0, 50.0, 50.0, 50.0],
        "gls_percentile": [50.0, 25.0, 50.0, 100.0],
        "ast_percentile": [50.0, 50.0, 75.0, 25.0],
    })
    return df
