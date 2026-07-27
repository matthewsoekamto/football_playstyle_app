import glob
import os
import warnings

warnings.filterwarnings("ignore")

# 1) check local data dir
data_files = sorted(glob.glob("data/*.csv"))
print("=== Local CSV files ===")
for f in data_files:
    print(f"  {f} ({os.path.getsize(f):,} bytes)")
print()

# 2) check what version of the dataset we have
import pandas as pd  # noqa: E402
try:
    df = pd.read_csv("data/players_data_light-2025_2026.csv", nrows=0)
    print("=== Current light dataset columns ===")
    for i, c in enumerate(df.columns):
        print(f"  {i:3d}. {c}")
    print(f"\n  Total: {len(df.columns)} columns")
except Exception as e:
    print(f"Could not read light dataset: {e}")
