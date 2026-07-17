"""
Run this script locally to fetch FBref possession stats.
Requirements: pip install requests beautifulsoup4 pandas lxml

It will save a file called: fbref_possession_2025_2026.csv
"""

import time
import pandas as pd
import requests
from bs4 import BeautifulSoup

URL = "https://fbref.com/en/comps/Big5/possession/players/Big-5-European-Leagues-Stats"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

OUTPUT_FILE = "fbref_possession_2025_2026.csv"


def fetch():
    print("Fetching FBref possession stats...")
    time.sleep(3)  # polite delay before request

    response = requests.get(URL, headers=HEADERS, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.content, "lxml")

    # FBref wraps the actual table in a comment to prevent easy scraping
    # We need to find and uncomment it
    import re
    comments = soup.find_all(string=lambda text: isinstance(text, type(soup.find(string=True).__class__) or True)
                             if False else True)

    # Get all comment nodes
    from bs4 import Comment
    comments = soup.find_all(string=lambda text: isinstance(text, Comment))

    table = None
    for comment in comments:
        if 'stats_possession' in comment:
            comment_soup = BeautifulSoup(comment, "lxml")
            table = comment_soup.find("table", {"id": "stats_possession"})
            if table:
                break

    # Sometimes the table is not in a comment
    if table is None:
        table = soup.find("table", {"id": "stats_possession"})

    if table is None:
        print("ERROR: Could not find the possession table.")
        print("FBref may have changed their page structure.")
        print("Try running the script again — sometimes it's a temporary issue.")
        return

    print("Table found. Parsing...")

    df = pd.read_html(str(table))[0]

    # FBref uses multi-level headers — flatten them
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            f"{b}" if a.startswith("Unnamed") else f"{a}_{b}"
            if not b.startswith("Unnamed") else f"{a}"
            for a, b in df.columns
        ]

    # Drop repeated header rows that FBref inserts mid-table
    df = df[df["Player"] != "Player"].copy()
    df = df[df["Player"].notna()].copy()

    # Drop the Matches column (just a link)
    if "Matches" in df.columns:
        df = df.drop(columns=["Matches"])

    print(f"Rows fetched: {len(df)}")
    print(f"Columns: {list(df.columns)}")
    print(df.head(3).to_string())

    df.to_csv(OUTPUT_FILE, index=False)
    print(f"\nSaved to: {OUTPUT_FILE}")
    print("Drop this file into your project and share it here to continue.")


if __name__ == "__main__":
    fetch()