import pandas as pd
import streamlit as st

OUTFIELD_RATE_STATS = ["gls", "ast", "sh", "crs", "tklw", "int"]
GK_RATE_STATS = ["saves", "cs", "int"]


def _add_per90_rates(df, stats):
    if "90s" not in df.columns:
        return df

    ninety_s = df["90s"].replace(0, pd.NA)
    for stat in stats:
        if stat in df.columns:
            df[f"{stat}_p90"] = (df[stat] / ninety_s).fillna(0)
    return df


@st.cache_data
def load_and_clean_data(filepath):
    try:
        df = pd.read_csv(filepath)
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Dataset file not found: '{filepath}'. "
            "Make sure the CSV file exists at the expected path."
        )
    except pd.errors.ParserError:
        raise ValueError(
            f"Could not parse the dataset file: '{filepath}'. "
            "The file may be corrupted or in an unexpected format."
        )

    df.columns = (
        df.columns.str.strip().str.lower().str.replace(" ", "_").str.replace("-", "_")
    )

    df = df[df["min"] >= 270].copy()

    if "pos" in df.columns:
        df["primary_position"] = df["pos"].str.split(",").str[0]

    df = _add_per90_rates(df, OUTFIELD_RATE_STATS)
    df = _add_per90_rates(df, GK_RATE_STATS)

    return df


if __name__ == "__main__":
    try:
        test_df = load_and_clean_data("data/players_data_light-2025_2026.csv")
        print("SUCCESS: Data loaded and standardized perfectly!")
        print(f"Total players available: {len(test_df)}")
        print("\nAvailable cleaned columns sample:")
        print(list(test_df.columns[:10]))
    except Exception as e:
        print(f"ERROR: Details: {e}")