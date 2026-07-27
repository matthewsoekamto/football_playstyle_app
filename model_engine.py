import hashlib
import json
import logging
import os
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import streamlit as st
from sklearn.cluster import KMeans
from sklearn.metrics import davies_bouldin_score, silhouette_score
from sklearn.preprocessing import StandardScaler

from data_loader import load_and_clean_data

logger = logging.getLogger(__name__)

MODELS_DIR = Path("models")
MODELS_DIR.mkdir(exist_ok=True)

OUTFIELD_FEATURES = [
    "gls_p90",
    "ast_p90",
    "sh_p90",
    "crs_p90",
    "tklw_p90",
    "int_p90",
]
GK_FEATURES = ["saves_p90", "save%", "cs_p90", "int_p90"]

OUTFIELD_ARCHETYPES = {
    "Elite Finishers": {
        "gls_p90": 0.50, "ast_p90": 0.15, "sh_p90": 3.2,
        "crs_p90": 0.8, "tklw_p90": 0.6, "int_p90": 0.3,
    },
    "Advanced Attackers": {
        "gls_p90": 0.35, "ast_p90": 0.20, "sh_p90": 2.4,
        "crs_p90": 1.5, "tklw_p90": 0.8, "int_p90": 0.4,
    },
    "Wide Creators": {
        "gls_p90": 0.10, "ast_p90": 0.20, "sh_p90": 1.0,
        "crs_p90": 4.5, "tklw_p90": 1.0, "int_p90": 0.5,
    },
    "Deep Creators": {
        "gls_p90": 0.08, "ast_p90": 0.25, "sh_p90": 1.2,
        "crs_p90": 2.5, "tklw_p90": 1.5, "int_p90": 0.8,
    },
    "Direct Attackers": {
        "gls_p90": 0.20, "ast_p90": 0.10, "sh_p90": 1.8,
        "crs_p90": 0.8, "tklw_p90": 0.8, "int_p90": 0.4,
    },
    "Ball-Winning Anchors": {
        "gls_p90": 0.05, "ast_p90": 0.08, "sh_p90": 0.8,
        "crs_p90": 1.2, "tklw_p90": 3.5, "int_p90": 3.0,
    },
    "Defensive Anchors": {
        "gls_p90": 0.03, "ast_p90": 0.06, "sh_p90": 0.5,
        "crs_p90": 1.0, "tklw_p90": 2.0, "int_p90": 2.0,
    },
    "Utility / Depth Players": {
        "gls_p90": 0.08, "ast_p90": 0.08, "sh_p90": 0.9,
        "crs_p90": 1.2, "tklw_p90": 1.2, "int_p90": 1.0,
    },
}

GK_ARCHETYPES = {
    "Shot-Stoppers": {
        "saves_p90": 2.5,
        "save%": 72.0,
        "cs_p90": 0.25,
        "int_p90": 0.05,
    },
    "Sweeper-Keepers": {
        "saves_p90": 2.8,
        "save%": 70.0,
        "cs_p90": 0.20,
        "int_p90": 0.35,
    },
}


def _available_features(df, features):
    return [feature for feature in features if feature in df.columns]


def _archetype_matrix(archetypes, feature_cols):
    archetype_names = list(archetypes.keys())
    matrix = np.array(
        [[archetypes[name].get(feature, 0.0) for feature in feature_cols] for name in archetype_names]
    )
    return archetype_names, matrix


def _assign_labels_from_archetypes(centroids, archetypes, feature_cols, scaler=None, threshold=3.5):
    """Assign each cluster its true nearest archetype by Euclidean distance.

    Unlike the previous greedy-with-deduplication approach, this version lets
    multiple clusters share a label if that's genuinely their closest archetype.
    If no archetype is within ``threshold`` standardized units, the cluster is
    labelled "Mixed Profile" instead of forcing a misleading name.

    When ``scaler`` is provided (the player-level StandardScaler from
    ``group_players``), it is used to transform both centroids and archetypes
    so distances are anchored to the real data distribution. Otherwise a scaler
    is fit on the centroids alone — sufficient for outfield K=8 where centroids
    are numerous enough, but unreliable for GK K=2 (ML-01).

    See ADR-009 and OPTION_C_PLAN.md for the rationale.
    """
    archetype_names, archetype_matrix = _archetype_matrix(archetypes, feature_cols)

    if scaler is not None:
        scaled_centroids = scaler.transform(centroids[feature_cols].values)
        scaled_archetypes = scaler.transform(archetype_matrix)
    else:
        scaler_fallback = StandardScaler()
        scaled_centroids = scaler_fallback.fit_transform(centroids[feature_cols].values)
        scaled_archetypes = scaler_fallback.transform(archetype_matrix)

    labels = {}
    for index, cluster_id in enumerate(centroids.index):
        centroid_vector = scaled_centroids[index].reshape(1, -1)
        distances = np.linalg.norm(scaled_archetypes - centroid_vector, axis=1)
        best_idx = np.argmin(distances)
        best_dist = distances[best_idx]

        if best_dist <= threshold:
            labels[cluster_id] = archetype_names[best_idx]
        else:
            labels[cluster_id] = "Mixed Profile"

    return labels


def evaluate_clustering(
    scaled_data: np.ndarray, labels: np.ndarray, prefix: str = ""
) -> dict[str, float]:
    """Compute silhouette score and Davies-Bouldin index for a clustered dataset.

    Parameters
    ----------
    scaled_data : np.ndarray
        Standardized feature matrix, shape (n_samples, n_features).
    labels : np.ndarray
        Cluster label for each sample, shape (n_samples,).
    prefix : str
        Optional label for log output (e.g. "Outfield" or "GK").

    Returns
    -------
    dict[str, float]
        Dictionary with keys ``silhouette_score`` and ``davies_bouldin_score``.
    """
    sil = silhouette_score(scaled_data, labels)
    db = davies_bouldin_score(scaled_data, labels)
    label = f"[{prefix}] " if prefix else ""
    logger.info("%sSilhouette:     %.4f", label, sil)
    logger.info("%sDavies-Bouldin: %.4f", label, db)
    return {"silhouette_score": sil, "davies_bouldin_score": db}


def get_cluster_profiles(df, feature_cols, playstyle_col="playstyle_cluster"):
    if playstyle_col not in df.columns:
        return pd.DataFrame()

    profiles = []
    for playstyle, group in df.groupby(playstyle_col):
        centroid = group[feature_cols].mean()
        distances = np.linalg.norm(
            group[feature_cols].values - centroid.values,
            axis=1,
        )
        top_players = (
            group.assign(_distance_to_centroid=distances)
            .nsmallest(5, "_distance_to_centroid")["player"]
            .tolist()
        )

        profile = {
            "playstyle": playstyle,
            "player_count": len(group),
            "top_players": top_players,
        }
        for feature in feature_cols:
            profile[feature] = centroid[feature]
        profiles.append(profile)

    return pd.DataFrame(profiles)


def _compute_dataset_hash(filepath: str) -> str:
    """SHA256 hash of the dataset file for change detection."""
    with open(filepath, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _get_metadata_path() -> Path:
    return MODELS_DIR / "metadata.json"


def _get_artifacts_paths() -> dict[str, Path]:
    return {
        "outfield_scaler": MODELS_DIR / "outfield_scaler.joblib",
        "outfield_kmeans": MODELS_DIR / "outfield_kmeans.joblib",
        "gk_scaler": MODELS_DIR / "gk_scaler.joblib",
        "gk_kmeans": MODELS_DIR / "gk_kmeans.joblib",
        "cluster_labels": MODELS_DIR / "cluster_labels.json",
    }


def _save_model_artifacts(
    scaler_out, kmeans_out, scaler_gk, kmeans_gk,
    cluster_names_out, cluster_names_gk,
    filepath: str, df_shape: tuple
):
    """Persist fitted scalers, KMeans models, and label mappings with metadata."""
    paths = _get_artifacts_paths()

    joblib.dump(scaler_out, paths["outfield_scaler"])
    joblib.dump(kmeans_out, paths["outfield_kmeans"])
    joblib.dump(scaler_gk, paths["gk_scaler"])
    joblib.dump(kmeans_gk, paths["gk_kmeans"])

    cluster_labels = {
        "outfield": {str(k): v for k, v in cluster_names_out.items()},
        "gk": {str(k): v for k, v in cluster_names_gk.items()},
    }
    with open(paths["cluster_labels"], "w") as f:
        json.dump(cluster_labels, f)

    metadata = {
        "dataset_file": os.path.basename(filepath),
        "dataset_hash": _compute_dataset_hash(filepath),
        "row_count": df_shape[0],
        "outfield_count": int(df_shape[0] * 0.93),
        "gk_count": int(df_shape[0] * 0.07),
        "fit_timestamp": datetime.now().isoformat(),
        "sklearn_version": __import__("sklearn").__version__,
        "numpy_version": np.__version__,
        "joblib_version": joblib.__version__,
        "kmeans_params": {"n_clusters": 8, "random_state": 42, "n_init": 10},
        "gk_kmeans_params": {"n_clusters": 2, "random_state": 42, "n_init": 10},
    }
    with open(_get_metadata_path(), "w") as f:
        json.dump(metadata, f, indent=2)

    logger.info("Saved model artifacts to %s", MODELS_DIR)


def _load_model_artifacts(filepath: str) -> dict | None:
    """Load persisted artifacts if they exist and match the current dataset."""
    paths = _get_artifacts_paths()
    metadata_path = _get_metadata_path()

    if not all(p.exists() for p in paths.values()) or not metadata_path.exists():
        logger.info("No persisted model artifacts found")
        return None

    with open(metadata_path) as f:
        metadata = json.load(f)

    current_hash = _compute_dataset_hash(filepath)
    if metadata.get("dataset_hash") != current_hash:
        logger.info("Dataset hash mismatch — invalidating persisted model")
        return None

    try:
        artifacts = {
            "scaler_out": joblib.load(paths["outfield_scaler"]),
            "kmeans_out": joblib.load(paths["outfield_kmeans"]),
            "scaler_gk": joblib.load(paths["gk_scaler"]),
            "kmeans_gk": joblib.load(paths["gk_kmeans"]),
        }
        with open(paths["cluster_labels"]) as f:
            artifacts["cluster_labels"] = json.load(f)
        logger.info("Loaded persisted model from %s (fitted %s)", MODELS_DIR, metadata["fit_timestamp"])
        return artifacts
    except Exception as e:
        logger.warning("Failed to load persisted artifacts: %s", e)
        return None


def _apply_loaded_model(
    df, artifacts, outfield_features, gk_features,
    outfield_archetypes, gk_archetypes
):
    """Apply loaded scalers + KMeans + label mappings to fresh data."""
    df_gk = df[df["primary_position"] == "GK"].copy()
    df_outfield = df[df["primary_position"] != "GK"].copy()

    # Outfield
    if outfield_features and not df_outfield.empty:
        outfield_data = df_outfield[outfield_features].fillna(0)
        scaled_out = artifacts["scaler_out"].transform(outfield_data)
        df_outfield["cluster_id"] = artifacts["kmeans_out"].predict(scaled_out)
        cluster_names = {int(k): v for k, v in artifacts["cluster_labels"]["outfield"].items()}
        df_outfield["playstyle_cluster"] = df_outfield["cluster_id"].map(cluster_names)

    # GK
    if gk_features and not df_gk.empty:
        gk_data = df_gk[gk_features].fillna(0)
        scaled_gk = artifacts["scaler_gk"].transform(gk_data)
        df_gk["cluster_id"] = artifacts["kmeans_gk"].predict(scaled_gk)
        cluster_names = {int(k): v for k, v in artifacts["cluster_labels"]["gk"].items()}
        df_gk["playstyle_cluster"] = df_gk["cluster_id"].map(cluster_names)

    return pd.concat([df_outfield, df_gk], ignore_index=True)


def group_players(df, evaluate: bool = False):
    if "primary_position" not in df.columns:
        df["primary_position"] = df["pos"].str.split(",").str[0]

    df_gk = df[df["primary_position"] == "GK"].copy()
    df_outfield = df[df["primary_position"] != "GK"].copy()

    outfield_features = _available_features(df_outfield, OUTFIELD_FEATURES)
    if outfield_features and not df_outfield.empty:
        outfield_data = df_outfield[outfield_features].fillna(0)
        scaler_out = StandardScaler()
        scaled_out = scaler_out.fit_transform(outfield_data)

        kmeans_out = KMeans(n_clusters=8, random_state=42, n_init=10)
        df_outfield["cluster_id"] = kmeans_out.fit_predict(scaled_out)

        centroids = df_outfield.groupby("cluster_id")[outfield_features].mean()
        cluster_names = _assign_labels_from_archetypes(
            centroids,
            OUTFIELD_ARCHETYPES,
            outfield_features,
            scaler=scaler_out,
        )
        df_outfield["playstyle_cluster"] = df_outfield["cluster_id"].map(cluster_names)

        if evaluate and outfield_features and outfield_data.shape[0] >= 3:
            evaluate_clustering(scaled_out, df_outfield["cluster_id"].values, prefix="Outfield")

    gk_features = _available_features(df_gk, GK_FEATURES)
    if gk_features and not df_gk.empty:
        gk_data = df_gk[gk_features].fillna(0)
        scaler_gk = StandardScaler()
        scaled_gk = scaler_gk.fit_transform(gk_data)

        kmeans_gk = KMeans(n_clusters=2, random_state=42, n_init=10)
        df_gk["cluster_id"] = kmeans_gk.fit_predict(scaled_gk)

        centroids = df_gk.groupby("cluster_id")[gk_features].mean()
        cluster_names = _assign_labels_from_archetypes(
            centroids,
            GK_ARCHETYPES,
            gk_features,
            scaler=scaler_gk,
        )
        df_gk["playstyle_cluster"] = df_gk["cluster_id"].map(cluster_names)

        if evaluate and gk_features and gk_data.shape[0] >= 3:
            evaluate_clustering(scaled_gk, df_gk["cluster_id"].values, prefix="GK")

    return pd.concat([df_outfield, df_gk], ignore_index=True)


@st.cache_resource
def _get_or_fit_model(filepath: str):
    """
    Load persisted model artifacts if valid, otherwise fit new model and persist.
    Returns (clustered_df, from_cache: bool)
    """
    cleaned = load_and_clean_data(filepath)

    # Try to load persisted artifacts
    artifacts = _load_model_artifacts(filepath)
    if artifacts is not None:
        # Apply loaded model to fresh cleaned data
        outfield_features = _available_features(cleaned[cleaned["primary_position"] != "GK"], OUTFIELD_FEATURES)
        gk_features = _available_features(cleaned[cleaned["primary_position"] == "GK"], GK_FEATURES)

        clustered = _apply_loaded_model(
            cleaned, artifacts, outfield_features, gk_features,
            OUTFIELD_ARCHETYPES, GK_ARCHETYPES
        )
        return clustered, True

    # Fit new model
    logger.info("No valid persisted model — fitting new model")
    clustered = group_players(cleaned)

    # Persist artifacts
    outfield_features = _available_features(clustered[clustered["primary_position"] != "GK"], OUTFIELD_FEATURES)
    gk_features = _available_features(clustered[clustered["primary_position"] == "GK"], GK_FEATURES)

    # Re-fit to get the fitted objects (we could refactor to return them, but keep it simple)
    outfield_data = clustered[clustered["primary_position"] != "GK"][outfield_features].fillna(0)
    gk_data = clustered[clustered["primary_position"] == "GK"][gk_features].fillna(0)

    scaler_out = StandardScaler()
    scaled_out = scaler_out.fit_transform(outfield_data)
    kmeans_out = KMeans(n_clusters=8, random_state=42, n_init=10)
    kmeans_out.fit(scaled_out)

    scaler_gk = StandardScaler()
    scaled_gk = scaler_gk.fit_transform(gk_data)
    kmeans_gk = KMeans(n_clusters=2, random_state=42, n_init=10)
    kmeans_gk.fit(scaled_gk)

    # Get cluster names from the fitted model
    outfield_centroids = clustered[clustered["primary_position"] != "GK"].groupby("cluster_id")[outfield_features].mean()
    outfield_names = _assign_labels_from_archetypes(outfield_centroids, OUTFIELD_ARCHETYPES, outfield_features, scaler=scaler_out)

    gk_centroids = clustered[clustered["primary_position"] == "GK"].groupby("cluster_id")[gk_features].mean()
    gk_names = _assign_labels_from_archetypes(gk_centroids, GK_ARCHETYPES, gk_features, scaler=scaler_gk)

    _save_model_artifacts(
        scaler_out, kmeans_out, scaler_gk, kmeans_gk,
        outfield_names, gk_names,
        filepath, clustered.shape
    )

    return clustered, False


@st.cache_data
def get_clustered_data(filepath):
    clustered, from_cache = _get_or_fit_model(filepath)
    if from_cache:
        logger.info("Using persisted model for clustering")
    return clustered


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    persist = "--persist" in sys.argv
    evaluate = "--evaluate" in sys.argv or persist

    try:
        logger.info("Loading data...")
        my_data = load_and_clean_data("data/players_data_light-2025_2026.csv")

        if persist:
            logger.info("Fitting and persisting model (--persist flag)...")
            clustered_data = group_players(my_data, evaluate=evaluate)

            outfield_features = _available_features(clustered_data[clustered_data["primary_position"] != "GK"], OUTFIELD_FEATURES)
            gk_features = _available_features(clustered_data[clustered_data["primary_position"] == "GK"], GK_FEATURES)

            outfield_data = clustered_data[clustered_data["primary_position"] != "GK"][outfield_features].fillna(0)
            gk_data = clustered_data[clustered_data["primary_position"] == "GK"][gk_features].fillna(0)

            scaler_out = StandardScaler()
            scaled_out = scaler_out.fit_transform(outfield_data)
            kmeans_out = KMeans(n_clusters=8, random_state=42, n_init=10)
            kmeans_out.fit(scaled_out)

            scaler_gk = StandardScaler()
            scaled_gk = scaler_gk.fit_transform(gk_data)
            kmeans_gk = KMeans(n_clusters=2, random_state=42, n_init=10)
            kmeans_gk.fit(scaled_gk)

            outfield_centroids = clustered_data[clustered_data["primary_position"] != "GK"].groupby("cluster_id")[outfield_features].mean()
            outfield_names = _assign_labels_from_archetypes(outfield_centroids, OUTFIELD_ARCHETYPES, outfield_features, scaler=scaler_out)

            gk_centroids = clustered_data[clustered_data["primary_position"] == "GK"].groupby("cluster_id")[gk_features].mean()
            gk_names = _assign_labels_from_archetypes(gk_centroids, GK_ARCHETYPES, gk_features, scaler=scaler_gk)

            _save_model_artifacts(
                scaler_out, kmeans_out, scaler_gk, kmeans_gk,
                outfield_names, gk_names,
                "data/players_data_light-2025_2026.csv", clustered_data.shape
            )
        else:
            logger.info("Running dual-engine clustering...")
            clustered_data = group_players(my_data, evaluate=evaluate)

        logger.info("SUCCESS: Players and goalkeepers have been grouped and named!")
        logger.info("\nComplete playstyle distribution:\n%s", clustered_data["playstyle_cluster"].value_counts())
    except Exception as e:
        logger.error("ERROR: %s", e)