import numpy as np
import pandas as pd
import streamlit as st
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

from data_loader import load_and_clean_data

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
        "gls_p90": 0.45,
        "ast_p90": 0.20,
        "sh_p90": 3.0,
        "crs_p90": 1.0,
        "tklw_p90": 1.0,
        "int_p90": 0.5,
    },
    "Creative Playmakers": {
        "gls_p90": 0.15,
        "ast_p90": 0.35,
        "sh_p90": 1.5,
        "crs_p90": 4.0,
        "tklw_p90": 1.5,
        "int_p90": 0.8,
    },
    "Ball-Winning Anchors": {
        "gls_p90": 0.05,
        "ast_p90": 0.08,
        "sh_p90": 0.8,
        "crs_p90": 1.5,
        "tklw_p90": 3.5,
        "int_p90": 3.0,
    },
    "Defensive Rotators": {
        "gls_p90": 0.08,
        "ast_p90": 0.12,
        "sh_p90": 1.2,
        "crs_p90": 2.0,
        "tklw_p90": 2.5,
        "int_p90": 2.0,
    },
    "Utility / Depth Players": {
        "gls_p90": 0.10,
        "ast_p90": 0.10,
        "sh_p90": 1.0,
        "crs_p90": 1.5,
        "tklw_p90": 1.5,
        "int_p90": 1.2,
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


def _assign_labels_from_archetypes(centroids, archetypes, feature_cols):
    archetype_names, archetype_matrix = _archetype_matrix(archetypes, feature_cols)

    scaler = StandardScaler()
    scaled_centroids = scaler.fit_transform(centroids[feature_cols].values)
    scaled_archetypes = scaler.transform(archetype_matrix)

    labels = {}
    used_names = set()
    for index, cluster_id in enumerate(centroids.index):
        centroid_vector = scaled_centroids[index].reshape(1, -1)
        distances = np.linalg.norm(scaled_archetypes - centroid_vector, axis=1)
        ranked_indices = np.argsort(distances)

        chosen_name = archetype_names[ranked_indices[0]]
        for idx in ranked_indices:
            candidate = archetype_names[idx]
            if candidate not in used_names:
                chosen_name = candidate
                break

        labels[cluster_id] = chosen_name
        used_names.add(chosen_name)

    return labels


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


def group_players(df):
    if "primary_position" not in df.columns:
        df["primary_position"] = df["pos"].str.split(",").str[0]

    df_gk = df[df["primary_position"] == "GK"].copy()
    df_outfield = df[df["primary_position"] != "GK"].copy()

    outfield_features = _available_features(df_outfield, OUTFIELD_FEATURES)
    if outfield_features and not df_outfield.empty:
        outfield_data = df_outfield[outfield_features].fillna(0)
        scaler_out = StandardScaler()
        scaled_out = scaler_out.fit_transform(outfield_data)

        kmeans_out = KMeans(n_clusters=5, random_state=42, n_init=10)
        df_outfield["cluster_id"] = kmeans_out.fit_predict(scaled_out)

        centroids = df_outfield.groupby("cluster_id")[outfield_features].mean()
        cluster_names = _assign_labels_from_archetypes(
            centroids,
            OUTFIELD_ARCHETYPES,
            outfield_features,
        )
        df_outfield["playstyle_cluster"] = df_outfield["cluster_id"].map(cluster_names)

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
        )
        df_gk["playstyle_cluster"] = df_gk["cluster_id"].map(cluster_names)

    return pd.concat([df_outfield, df_gk], ignore_index=True)


@st.cache_data
def get_clustered_data(filepath):
    return group_players(load_and_clean_data(filepath))


if __name__ == "__main__":
    try:
        print("Loading data...")
        my_data = load_and_clean_data("players_data_light-2025_2026.csv")

        print("Running dual-engine clustering...")
        clustered_data = group_players(my_data)

        print("SUCCESS: Players and goalkeepers have been grouped and named!")
        print("\nComplete playstyle distribution:")
        print(clustered_data["playstyle_cluster"].value_counts())
    except Exception as e:
        print(f"ERROR: {e}")
