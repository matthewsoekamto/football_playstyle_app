"""Tests for model_engine.py — clustering and archetype labeling.

The single highest-value test in this file is `test_determinism`:
it proves that `group_players` produces identical playstyle labels
across two independent runs on the same input, which enforces the
`random_state=42` reproducibility requirement.
"""

import numpy as np
import pandas as pd
import pytest
from data_loader import load_and_clean_data
from model_engine import group_players, get_cluster_profiles


def _run_clustering(csv_path):
    """Helper: load, clean, and cluster. Returns the labelled DataFrame."""
    cleaned = load_and_clean_data(csv_path)
    return group_players(cleaned)


class TestDeterminism:
    """The clustering pipeline must produce identical results run-to-run.

    This is the single highest-priority test in the project
    (TESTING_GUIDE.md §3, model_engine.py). It directly enforces
    `PROJECT_CONSTITUTION.md §8` (reproducibility is non-negotiable)
    and `ML_GUIDELINES.md §10` (every stochastic operation must be seeded).
    """

    def test_group_players_determinism(self, fixture_csv_path):
        """group_players produces identical playstyle_cluster labels
        across two independent runs on the same fixture."""
        result_a = _run_clustering(fixture_csv_path)
        result_b = _run_clustering(fixture_csv_path)

        assert (
            result_a["playstyle_cluster"] == result_b["playstyle_cluster"]
        ).all(), (
            "playstyle_cluster labels differ between runs. "
            "This likely means random_state was removed or changed "
            "on a KMeans or StandardScaler call."
        )

    def test_cluster_id_assignment_order(self, fixture_csv_path):
        """Even the raw cluster_id integers (before archetype mapping)
        are identical across runs, confirming KMeans initialization is
        fully deterministic."""
        cleaned = load_and_clean_data(fixture_csv_path)
        df_a = group_players(cleaned.copy())
        df_b = group_players(cleaned.copy())

        assert (
            df_a["cluster_id"] == df_b["cluster_id"]
        ).all(), (
            "cluster_id values differ between runs — KMeans "
            "initialization may not be seeded consistently."
        )


class TestClusterOutput:
    """Structural properties of the clustering output."""

    def test_all_rows_have_playstyle_label(self, fixture_csv_path):
        """Every row in the output has a non-null playstyle_cluster."""
        result = _run_clustering(fixture_csv_path)
        null_count = result["playstyle_cluster"].isna().sum()
        assert null_count == 0, f"{null_count} rows have no playstyle label"

    def test_gk_and_outfield_labels_are_disjoint(self, fixture_csv_path):
        """GK playstyle labels never appear on outfield rows and vice versa."""
        result = _run_clustering(fixture_csv_path)

        gk_labels = set(
            result.loc[
                result["primary_position"] == "GK", "playstyle_cluster"
            ].unique()
        )
        outfield_labels = set(
            result.loc[
                result["primary_position"] != "GK", "playstyle_cluster"
            ].unique()
        )

        overlap = gk_labels & outfield_labels
        assert len(overlap) == 0, (
            f"GK and outfield labels overlap: {overlap}. "
            "The two KMeans models may have been merged."
        )

    def test_gk_clustering_handles_no_gk(self, fixture_csv_path):
        """group_players handles a DataFrame with zero GK rows
        without raising — exercises the `if gk_features and not
        df_gk.empty:` guard."""
        cleaned = load_and_clean_data(fixture_csv_path)
        no_gk = cleaned[cleaned["primary_position"] != "GK"].copy()

        result = group_players(no_gk)
        assert len(result) == len(no_gk), "Row count changed unexpectedly"
        assert result["playstyle_cluster"].notna().all(), (
            "Some outfield rows missing playstyle label"
        )

    def test_each_cluster_has_unique_label(self, fixture_csv_path):
        """No two clusters share the same playstyle name."""
        result = _run_clustering(fixture_csv_path)
        label_to_cluster = (
            result[["cluster_id", "playstyle_cluster"]]
            .drop_duplicates()
            .groupby("playstyle_cluster")["cluster_id"]
            .nunique()
        )
        duplicates = label_to_cluster[label_to_cluster > 1]
        assert len(duplicates) == 0, (
            f"Labels assigned to multiple clusters: {duplicates.to_dict()}. "
            "The archetype matching may have broken deduplication."
        )


class TestClusterProfiles:
    """get_cluster_profiles returns sensible summary data."""

    def test_top_players_limited_to_five(self):
        """get_cluster_profiles returns at most 5 top players per cluster.

        Uses a manually-constructed DataFrame with proper float64 dtypes
        to avoid object-dtype issues that can arise from the small
        synthetic fixture's per-90 computation.
        """
        # Build a DataFrame with explicit float64 dtype
        rng = np.random.default_rng(42)
        n_players = 20
        features = ["gls_p90", "ast_p90", "sh_p90"]
        data = {
            "player": [f"Player_{i}" for i in range(n_players)],
            "playstyle_cluster": ["Type_A"] * 10 + ["Type_B"] * 10,
        }
        for feat in features:
            data[feat] = rng.random(n_players).astype(np.float64)

        test_df = pd.DataFrame(data)

        profiles = get_cluster_profiles(
            test_df, features, playstyle_col="playstyle_cluster",
        )

        assert len(profiles) == 2, "Expected 2 profile rows"
        for _, row in profiles.iterrows():
            assert len(row["top_players"]) <= 5, (
                f"Cluster '{row['playstyle']}' has "
                f"{len(row['top_players'])} top players, expected ≤5"
            )

    def test_empty_profiles_on_missing_column(self):
        """get_cluster_profiles returns empty DataFrame when the
        playstyle column is absent."""
        df = pd.DataFrame({"player": ["A"], "gls_p90": [0.5]})
        result = get_cluster_profiles(df, ["gls_p90"], playstyle_col="nonexistent")
        assert isinstance(result, pd.DataFrame)
        assert result.empty
