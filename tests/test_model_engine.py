"""Tests for model_engine.py — clustering and archetype labeling.

The single highest-value test in this file is `test_determinism`:
it proves that `group_players` produces identical playstyle labels
across two independent runs on the same input, which enforces the
`random_state=42` reproducibility requirement.
"""

import numpy as np
import pandas as pd

from data_loader import load_and_clean_data
from model_engine import (
    _apply_loaded_model,
    _load_model_artifacts,
    _save_model_artifacts,
    get_cluster_profiles,
    group_players,
)


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

    def test_labels_use_raw_archetype_names(self, fixture_csv_path):
        """Every playstyle label is an archetype name from OUTFIELD_ARCHETYPES
        or GK_ARCHETYPES (or "Mixed Profile" if beyond threshold), never a
        synthetic or truncated string.

        With K=8 outfield + K=2 GK the non-greedy labeler may assign the
        same archetype name to multiple clusters — that is correct behaviour
        (honest nearest-neighbour, not forced-unique).
        """
        from model_engine import GK_ARCHETYPES, OUTFIELD_ARCHETYPES
        result = _run_clustering(fixture_csv_path)

        outfield_archetypes = set(OUTFIELD_ARCHETYPES.keys()) | {"Mixed Profile"}
        gk_archetypes = set(GK_ARCHETYPES.keys()) | {"Mixed Profile"}

        outfield_labels = result.loc[
            result["primary_position"] != "GK", "playstyle_cluster"
        ].unique()
        gk_labels = result.loc[
            result["primary_position"] == "GK", "playstyle_cluster"
        ].unique()

        bad_outfield = set(outfield_labels) - outfield_archetypes
        assert len(bad_outfield) == 0, (
            f"Outfield labels not in archetype set: {bad_outfield}"
        )
        bad_gk = set(gk_labels) - gk_archetypes
        assert len(bad_gk) == 0, (
            f"GK labels not in archetype set: {bad_gk}"
        )

    def test_shared_labels_under_non_greedy(self, fixture_csv_path):
        """With K=8 outfield on a small fixture, at least one archetype
        label is shared across multiple cluster IDs, proving the non-greedy
        assignment is active (no forced-unique constraint)."""
        result = _run_clustering(fixture_csv_path)
        outfield = result[result["primary_position"] != "GK"].copy()

        label_to_cluster = (
            outfield[["cluster_id", "playstyle_cluster"]]
            .drop_duplicates()
            .groupby("playstyle_cluster")["cluster_id"]
            .nunique()
        )
        shared = label_to_cluster[label_to_cluster > 1]
        assert len(shared) >= 1, (
            "Expected at least one label shared across clusters "
            "with the non-greedy labeler (9 rows, K=8), "
            f"but all labels are unique: {label_to_cluster.to_dict()}. "
            "This means every KMeans centroid happened to map to a "
            "different archetype, which is vanishingly unlikely."
        )

    def test_assign_labels_allows_shared_names(self):
        """_assign_labels_from_archetypes correctly assigns the same
        archetype name to two different clusters when both are closest
        to that archetype — proving the non-greedy constraint is active."""
        import numpy as np
        from sklearn.preprocessing import StandardScaler

        from model_engine import _assign_labels_from_archetypes

        # Two centroids deliberately close to the first archetype
        centroids = pd.DataFrame(
            {"gls_p90": [0.48, 0.45], "sh_p90": [3.1, 3.0],
             "ast_p90": [0.1, 0.1], "crs_p90": [0.5, 0.5],
             "tklw_p90": [0.5, 0.5], "int_p90": [0.3, 0.3]},
            index=[0, 1],
        )
        archetypes = {
            "Elite Finishers": {"gls_p90": 0.5, "sh_p90": 3.2,
                                "ast_p90": 0.15, "crs_p90": 0.8,
                                "tklw_p90": 0.6, "int_p90": 0.3},
            "Wide Creators": {"gls_p90": 0.1, "sh_p90": 1.0,
                              "ast_p90": 0.2, "crs_p90": 4.5,
                              "tklw_p90": 1.0, "int_p90": 0.5},
        }
        features = ["gls_p90", "ast_p90", "sh_p90", "crs_p90", "tklw_p90", "int_p90"]

        # Fit a scaler on a wider data distribution so the centroid scaling
        # is not degenerate (avoiding the ML-01 fallback path with only 2 points)
        scaler = StandardScaler()
        scaler.fit(np.array([
            [0.5, 0.2, 3.0, 1.0, 1.0, 0.5],
            [0.4, 0.2, 2.5, 2.0, 0.8, 0.4],
            [0.3, 0.25, 1.5, 3.0, 0.6, 0.3],
        ]))

        labels = _assign_labels_from_archetypes(
            centroids, archetypes, features, scaler=scaler, threshold=5.0,
        )
        assert labels[0] == "Elite Finishers", f"Expected 'Elite Finishers', got '{labels[0]}'"
        assert labels[1] == "Elite Finishers", f"Expected 'Elite Finishers', got '{labels[1]}'"

    def test_mixed_profile_fallback(self):
        """_assign_labels_from_archetypes returns 'Mixed Profile' when no
        archetype is within the threshold distance."""
        from model_engine import _assign_labels_from_archetypes

        # A centroid far from every archetype
        centroids = pd.DataFrame(
            {"gls_p90": [5.0], "sh_p90": [15.0], "ast_p90": [0.01],
             "crs_p90": [0.01], "tklw_p90": [0.01], "int_p90": [0.01]},
            index=[99],
        )
        archetypes = {
            "Low": {"gls_p90": 0.1, "sh_p90": 0.5, "ast_p90": 0.1,
                    "crs_p90": 0.5, "tklw_p90": 0.5, "int_p90": 0.3},
            "Very Low": {"gls_p90": 0.05, "sh_p90": 0.3, "ast_p90": 0.05,
                         "crs_p90": 0.3, "tklw_p90": 0.3, "int_p90": 0.2},
        }
        features = ["gls_p90", "ast_p90", "sh_p90", "crs_p90", "tklw_p90", "int_p90"]

        labels = _assign_labels_from_archetypes(centroids, archetypes, features, threshold=1.0)
        assert labels[99] == "Mixed Profile", (
            f"Expected 'Mixed Profile' for outlier centroid, got '{labels[99]}'"
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


class TestModelPersistence:
    """Tests for model persistence (joblib) and metadata validation."""

    def test_save_and_load_roundtrip(self, fixture_csv_path, tmp_path):
        """Persisted model loads and produces identical labels to fresh fit."""
        from sklearn.cluster import KMeans
        from sklearn.preprocessing import StandardScaler

        from model_engine import (
            GK_ARCHETYPES,
            GK_FEATURES,
            OUTFIELD_ARCHETYPES,
            OUTFIELD_FEATURES,
            group_players,
        )

        # First fit and save
        cleaned = load_and_clean_data(fixture_csv_path)
        clustered = group_players(cleaned)

        outfield = clustered[clustered["primary_position"] != "GK"]
        gk = clustered[clustered["primary_position"] == "GK"]

        outfield_features = [f for f in OUTFIELD_FEATURES if f in outfield.columns]
        gk_features = [f for f in GK_FEATURES if f in gk.columns]

        outfield_data = outfield[outfield_features].fillna(0)
        gk_data = gk[gk_features].fillna(0)

        scaler_out = StandardScaler()
        scaled_out = scaler_out.fit_transform(outfield_data)
        kmeans_out = KMeans(n_clusters=8, random_state=42, n_init=10)
        kmeans_out.fit(scaled_out)

        scaler_gk = StandardScaler()
        scaled_gk = scaler_gk.fit_transform(gk_data)
        kmeans_gk = KMeans(n_clusters=2, random_state=42, n_init=10)
        kmeans_gk.fit(scaled_gk)

        outfield_names = clustered[clustered["primary_position"] != "GK"].groupby("cluster_id")["playstyle_cluster"].first().to_dict()
        gk_names = clustered[clustered["primary_position"] == "GK"].groupby("cluster_id")["playstyle_cluster"].first().to_dict()

        # Use a temp directory for this test
        import model_engine
        original_models_dir = model_engine.MODELS_DIR
        model_engine.MODELS_DIR = tmp_path / "models"
        model_engine.MODELS_DIR.mkdir()

        try:
            _save_model_artifacts(
                scaler_out, kmeans_out, scaler_gk, kmeans_gk,
                outfield_names, gk_names,
                fixture_csv_path, clustered.shape
            )

            # Load and apply
            artifacts = _load_model_artifacts(fixture_csv_path)
            assert artifacts is not None, "Should load saved artifacts"

            applied = _apply_loaded_model(
                cleaned, artifacts, outfield_features, gk_features,
                OUTFIELD_ARCHETYPES, GK_ARCHETYPES
            )

            # Labels should match
            assert (applied["playstyle_cluster"] == clustered["playstyle_cluster"]).all(), \
                "Loaded model produces different labels than fresh fit"
        finally:
            model_engine.MODELS_DIR = original_models_dir

    def test_load_returns_none_on_hash_mismatch(self, fixture_csv_path, tmp_path):
        """Changed dataset invalidates persisted artifacts."""
        from sklearn.cluster import KMeans
        from sklearn.preprocessing import StandardScaler

        import model_engine

        original_models_dir = model_engine.MODELS_DIR
        model_engine.MODELS_DIR = tmp_path / "models"
        model_engine.MODELS_DIR.mkdir()

        try:
            cleaned = load_and_clean_data(fixture_csv_path)
            clustered = group_players(cleaned)

            outfield = clustered[clustered["primary_position"] != "GK"]
            gk = clustered[clustered["primary_position"] == "GK"]
            outfield_features = [f for f in model_engine.OUTFIELD_FEATURES if f in outfield.columns]
            gk_features = [f for f in model_engine.GK_FEATURES if f in gk.columns]

            outfield_data = outfield[outfield_features].fillna(0)
            gk_data = gk[gk_features].fillna(0)

            scaler_out = StandardScaler()
            kmeans_out = KMeans(n_clusters=8, random_state=42, n_init=10).fit(scaler_out.fit_transform(outfield_data))
            scaler_gk = StandardScaler()
            kmeans_gk = KMeans(n_clusters=2, random_state=42, n_init=10).fit(scaler_gk.fit_transform(gk_data))

            outfield_names = clustered[clustered["primary_position"] != "GK"].groupby("cluster_id")["playstyle_cluster"].first().to_dict()
            gk_names = clustered[clustered["primary_position"] == "GK"].groupby("cluster_id")["playstyle_cluster"].first().to_dict()

            _save_model_artifacts(
                scaler_out, kmeans_out, scaler_gk, kmeans_gk,
                outfield_names, gk_names,
                fixture_csv_path, clustered.shape
            )

            # Modify the CSV file
            with open(fixture_csv_path, "a") as f:
                f.write("\n99,Test,DF,Test,eng Premier League,1000,11.1,5,5,10,5,20,10,5,None,None,None")

            artifacts = _load_model_artifacts(fixture_csv_path)
            assert artifacts is None, "Should return None when dataset hash changes"
        finally:
            model_engine.MODELS_DIR = original_models_dir
