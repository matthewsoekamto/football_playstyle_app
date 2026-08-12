"""v2 position-scoped KMeans engine (P7).

Clusters the v2 master dataset (`data/wc2022_players_master.csv`) with one KMeans
per position group — GK / CB / FB/WB / MF / Wide / ST (``position_v2``) — then
labels each cluster against the 20 hand-authored archetypes of ``PLAYSTYLE_SPEC.md``.

This module deliberately does **not** import from ``model_engine`` or
``data_loader`` (both transitively import Streamlit). The pure helpers
``_archetype_matrix``, ``_assign_labels_from_archetypes``, ``evaluate_clustering``
and ``_compute_dataset_hash`` are copied verbatim from ``model_engine.py`` so the
engine runs headless against the master CSV.

Archetype prototypes are expressed as **σ-offsets above the group mean**
(``GROUP_ARCHETYPES``: Important traits ~ +2.0–2.5σ, everything else 0.0σ = the
group mean). ``_archetype_vectors_raw`` converts them to raw units via the group's
fitted scaler, so after ``_assign_labels_from_archetypes`` re-standardises them the
prototypes live *in the real data distribution*. This was the review-gate fix for
the P7 first-fit outcome where every cluster labelled "Mixed Profile": raw-unit
hand-guesses and the ``absent -> 0.0`` default put archetypes 2–40σ away from real
centroids on low-variance features (e.g. ``avg_def_position_y``, ``pass_completion_pct``).
The label threshold is dimension-aware (``LABEL_THRESHOLD * sqrt(n/6)``) so it
preserves v1's 3.5-at-6-features semantics as dimensionality grows.

Usage
-----
python v2_model_engine.py --evaluate   # fit + log per-group silhouette / Davies-Bouldin
python v2_model_engine.py --persist    # fit + evaluate + save artifacts to models_v2/

Persistence lives in ``models_v2/`` (never touches the v1 ``models/`` directory):
``{group}_scaler.joblib`` / ``{group}_kmeans.joblib``, ``cluster_labels_v2.json``,
``metadata_v2.json`` (SHA256 of the dataset; a changed CSV invalidates the cache).
"""

import hashlib
import json
import logging
import os
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import davies_bouldin_score, silhouette_score
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

MODELS_DIR_V2 = Path("models_v2")

RANDOM_STATE = 42
N_INIT = 10
# v1's threshold was 3.5 in a 6-feature space. In σ-space, distance grows ~sqrt(#features),
# so the threshold scales accordingly (3.5*sqrt(n/6) == 1.43*sqrt(n)).
LABEL_THRESHOLD = 3.5
V1_FEATURE_SPAN = 6.0

# Fallback label for a cluster whose nearest archetype is beyond the threshold — the
# honest "no clean match", never forcing a misleading archetype name. Per-group because
# the WC 2022 GK pool is genuinely homogeneous: 18/28 GKs land here, and "Mixed Profile"
# was a poor user-facing output for 64% of a position group. The quiet keepers are
# better described as "Traditional Goalkeeper" (verified: below-mean on saves and on every
# sweeping/distribution trait, deeper line — the stay-at-home keeper). Other groups have
# at most 1-2 such players and keep the honest "Mixed Profile".
GROUP_FALLBACK_LABEL = {
    "GK": "Traditional Goalkeeper",
    "CB": "Mixed Profile",
    "FB/WB": "Mixed Profile",
    "MF": "Mixed Profile",
    "Wide": "Mixed Profile",
    "ST": "Mixed Profile",
}

DATASET_PATH = "data/wc2022_players_master.csv"

GROUP_ORDER = ["GK", "CB", "FB/WB", "MF", "Wide", "ST"]
GROUP_K = {
    "GK": 2,
    "CB": 3,
    "FB/WB": 3,
    "MF": 5,
    "Wide": 3,
    "ST": 4,
}

# Per-group feature sets = union of Important + Not Important across each group's
# archetypes in PLAYSTYLE_SPEC.md, aliased to concrete master columns (proxies:
# xA→Ast_p90, dribbles→att_p90_sb, box_touches→touches_att_pen_p90,
# hold_up→passes_received_p90, line_breaking→prog_passes_p90,
# box_entries→carries_into_box_p90, carries/prog_carries→SB per-90 columns).
GROUP_FEATURES = {
    "GK": [
        "Saves_p90", "save_pct", "goals_prevented_p90", "claims_p90",
        "reflex_saves_p90", "passes_p90", "long_passes_p90", "prog_passes_p90",
        "def_actions_outside_box_p90", "avg_def_position_y", "launch_passes_p90",
        "sweeper_clearances_p90", "penalty_save_pct",
    ],
    "CB": [
        "clearances_p90", "blocks_p90", "aerial_duels_won_p90", "aerial_duel_pct",
        "Int_p90", "TklW_p90", "headed_clearances_p90", "prog_passes_p90",
        "carries_p90_sb", "prgcarries_p90_sb", "pass_completion_pct",
        "key_passes_p90", "gls_p90", "Ast_p90", "long_passes_p90",
        "passes_into_final_third_p90", "switches_p90", "Fls_p90", "pressures_p90",
        "pressures_final_third_p90", "duels_won_p90", "recoveries_p90",
    ],
    "FB/WB": [
        "TklW_p90", "Int_p90", "recoveries_p90", "pressures_p90", "blocks_p90",
        "clearances_p90", "duels_won_p90", "Fls_p90", "Crs_p90",
        "prgcarries_p90_sb", "prog_passes_p90", "final_third_entries_p90",
        "att_p90_sb", "Ast_p90", "key_passes_p90", "gls_p90",
        "cross_accuracy_pct", "touches_att_pen_p90", "carries_p90_sb",
        "dribble_success_pct", "shot_creating_actions_p90", "aerial_duels_won_p90",
    ],
    "MF": [
        "TklW_p90", "Int_p90", "recoveries_p90", "pressures_p90",
        "pressures_mid_third_p90", "Fls_p90", "duels_won_p90", "blocks_p90",
        "pass_completion_pct", "prog_passes_p90", "long_passes_p90",
        "key_passes_p90", "carries_p90_sb", "prgcarries_p90_sb", "shots_p90",
        "xG_p90", "gls_p90", "Ast_p90", "switches_p90",
        "passes_into_final_third_p90", "att_p90_sb", "carries_into_box_p90",
        "final_third_touches_p90", "Crs_p90", "aerial_duels_won_p90",
        "clearances_p90", "through_balls_p90", "shot_creating_actions_p90",
        "passes_into_box_p90", "touches_att_pen_p90", "shots_on_target_p90",
        "npxG_per_shot",
    ],
    "Wide": [
        "Crs_p90", "cross_accuracy_pct", "att_p90_sb", "dribble_success_pct",
        "prgcarries_p90_sb", "touches_wide_p90", "final_third_entries_p90",
        "Ast_p90", "key_passes_p90", "shots_p90", "xG_p90", "gls_p90",
        "through_balls_p90", "touches_halfspace_p90", "prog_passes_p90",
        "touches_att_pen_p90", "shots_on_target_p90", "npxG_per_shot",
        "shot_creating_actions_p90", "passes_into_box_p90", "TklW_p90",
        "Int_p90", "pressures_p90",
    ],
    "ST": [
        "gls_p90", "xG_p90", "shots_p90", "conversion_pct", "npxG_per_shot",
        "shots_on_target_pct", "touches_att_pen_p90", "touches_6yard_box_p90",
        "one_touch_finishes_p90", "Ast_p90", "key_passes_p90",
        "through_balls_p90", "prog_passes_p90", "carries_p90_sb",
        "prgcarries_p90_sb", "att_p90_sb", "aerial_duels_won_p90",
        "pressures_final_third_p90", "aerial_duel_pct", "headers_p90",
        "headed_goals_p90", "Fld_p90", "passes_received_p90", "passes_p90",
        "pass_completion_pct", "touches_halfspace_p90", "final_third_touches_p90",
        "passes_into_box_p90", "shot_creating_actions_p90", "TklW_p90",
        "Int_p90", "pressures_p90", "Crs_p90", "long_passes_p90",
    ],
}

# Prototype vectors for all 20 archetypes as **σ-offsets above the group mean**:
# a feature's value is how many group-std the prototype sits above the mean
# (+2.0 to +2.5σ for the archetype's defining traits, per PLAYSTYLE_SPEC.md's
# Important lists). Features not listed (Not Important / absent) default to 0.0σ
# = the group mean, so they contribute ~0 to the label distance. Keys use master
# column names. Converted to raw units at fit time by `_archetype_vectors_raw`.
GROUP_ARCHETYPES = {
    "GK": {
        "Shot Stopper": {
            "Saves_p90": 2.5, "save_pct": 2.5, "goals_prevented_p90": 2.0,
            "claims_p90": 1.5, "reflex_saves_p90": 2.5,
        },
        "Sweeper Keeper": {
            "def_actions_outside_box_p90": 2.5, "passes_p90": 2.0,
            "long_passes_p90": 2.0, "prog_passes_p90": 2.0,
            "launch_passes_p90": 2.5, "avg_def_position_y": 2.5,
            "claims_p90": 1.5, "sweeper_clearances_p90": 2.0,
        },
    },
    "CB": {
        "Traditional Centre Back": {
            "clearances_p90": 2.5, "blocks_p90": 2.0, "aerial_duels_won_p90": 2.5,
            "aerial_duel_pct": 2.0, "Int_p90": 2.0, "TklW_p90": 2.0,
            "headed_clearances_p90": 2.5,
        },
        "Ball-Playing Centre Back": {
            "prog_passes_p90": 2.5, "pass_completion_pct": 2.5,
            "long_passes_p90": 2.0, "carries_p90_sb": 2.0,
            "prgcarries_p90_sb": 2.0, "passes_into_final_third_p90": 2.0,
            "switches_p90": 2.0,
        },
        "Stopper / Destroyer": {
            "TklW_p90": 2.5, "Int_p90": 2.5, "pressures_p90": 2.0,
            "pressures_final_third_p90": 2.0, "Fls_p90": 2.0, "duels_won_p90": 2.0,
            "recoveries_p90": 2.0, "blocks_p90": 1.5,
        },
    },
    "FB/WB": {
        "Defensive Fullback": {
            "TklW_p90": 2.5, "Int_p90": 2.5, "recoveries_p90": 2.0,
            "pressures_p90": 2.0, "blocks_p90": 1.5, "clearances_p90": 2.0,
            "duels_won_p90": 2.0, "Fls_p90": 1.5,
        },
        "Attacking Fullback": {
            "Crs_p90": 2.5, "cross_accuracy_pct": 2.0, "prgcarries_p90_sb": 2.0,
            "prog_passes_p90": 2.0, "final_third_entries_p90": 2.0,
            "touches_att_pen_p90": 2.0, "key_passes_p90": 2.0, "Ast_p90": 2.0,
            "att_p90_sb": 1.5,
        },
        "Wingback": {
            "Crs_p90": 2.5, "prgcarries_p90_sb": 2.5, "carries_p90_sb": 2.0,
            "final_third_entries_p90": 2.5, "touches_att_pen_p90": 2.0,
            "att_p90_sb": 2.0, "dribble_success_pct": 1.5, "Ast_p90": 2.0,
            "prog_passes_p90": 2.0, "shot_creating_actions_p90": 2.0,
        },
    },
    "MF": {
        "Defensive Midfielder": {
            "TklW_p90": 2.5, "Int_p90": 2.5, "recoveries_p90": 2.0,
            "pressures_p90": 2.0, "pressures_mid_third_p90": 2.0, "Fls_p90": 1.5,
            "duels_won_p90": 2.0, "blocks_p90": 1.5, "pass_completion_pct": 2.0,
        },
        "Deep-Lying Playmaker": {
            "prog_passes_p90": 2.5, "pass_completion_pct": 2.5,
            "long_passes_p90": 2.0, "switches_p90": 2.0,
            "passes_into_final_third_p90": 2.0, "Ast_p90": 1.5,
            "key_passes_p90": 2.0,
        },
        "Box-to-Box Midfielder": {
            "TklW_p90": 2.0, "Int_p90": 2.0, "pressures_p90": 2.0,
            "prgcarries_p90_sb": 2.0, "carries_p90_sb": 2.0, "prog_passes_p90": 2.0,
            "shots_p90": 2.0, "xG_p90": 2.0, "gls_p90": 2.0, "Ast_p90": 2.0,
            "carries_into_box_p90": 2.0, "final_third_touches_p90": 2.0,
        },
        "Advanced Playmaker": {
            "key_passes_p90": 2.5, "through_balls_p90": 2.5,
            "shot_creating_actions_p90": 2.5, "Ast_p90": 2.0,
            "prog_passes_p90": 2.0, "passes_into_box_p90": 2.0,
            "touches_att_pen_p90": 2.0, "att_p90_sb": 1.5,
        },
        "Shadow Striker": {
            "gls_p90": 2.5, "shots_p90": 2.0, "xG_p90": 2.5,
            "touches_att_pen_p90": 2.0, "shots_on_target_p90": 2.0,
            "npxG_per_shot": 2.0, "prgcarries_p90_sb": 1.5,
            "carries_into_box_p90": 2.0, "shot_creating_actions_p90": 2.0,
        },
    },
    "Wide": {
        "Traditional Winger": {
            "Crs_p90": 2.5, "cross_accuracy_pct": 2.0, "att_p90_sb": 2.0,
            "dribble_success_pct": 1.5, "prgcarries_p90_sb": 2.0,
            "touches_wide_p90": 2.5, "final_third_entries_p90": 2.0,
            "Ast_p90": 2.0,
        },
        "Inverted Winger": {
            "shots_p90": 2.5, "xG_p90": 2.5, "gls_p90": 2.5, "att_p90_sb": 2.0,
            "dribble_success_pct": 1.5, "prgcarries_p90_sb": 2.0,
            "touches_halfspace_p90": 2.5, "touches_att_pen_p90": 2.0,
            "shots_on_target_p90": 2.0, "npxG_per_shot": 2.0,
        },
        "Wide Playmaker": {
            "key_passes_p90": 2.5, "through_balls_p90": 2.0,
            "shot_creating_actions_p90": 2.5, "Ast_p90": 2.0,
            "prog_passes_p90": 2.0, "passes_into_box_p90": 2.0, "Crs_p90": 1.5,
            "touches_halfspace_p90": 2.0, "prgcarries_p90_sb": 2.0,
        },
    },
    "ST": {
        "Poacher": {
            "gls_p90": 2.5, "xG_p90": 2.5, "shots_p90": 2.0,
            "conversion_pct": 2.0, "npxG_per_shot": 2.0,
            "shots_on_target_pct": 2.0, "touches_att_pen_p90": 2.5,
            "touches_6yard_box_p90": 2.5, "one_touch_finishes_p90": 2.0,
        },
        "Target Man": {
            "aerial_duels_won_p90": 2.5, "aerial_duel_pct": 2.5,
            "headers_p90": 2.5, "headed_goals_p90": 2.5, "Fld_p90": 2.0,
            "passes_received_p90": 2.0, "touches_att_pen_p90": 1.5,
            "gls_p90": 2.0,
        },
        "Complete Forward": {
            "gls_p90": 2.0, "xG_p90": 2.0, "shots_p90": 2.0,
            "npxG_per_shot": 1.5, "shot_creating_actions_p90": 2.5,
            "key_passes_p90": 2.0, "prgcarries_p90_sb": 2.0,
            "passes_received_p90": 2.0, "touches_att_pen_p90": 2.0,
            "aerial_duels_won_p90": 1.5,
        },
        "False 9": {
            "touches_halfspace_p90": 2.5, "passes_received_p90": 2.5,
            "key_passes_p90": 2.5, "shot_creating_actions_p90": 2.5,
            "Ast_p90": 2.0, "prog_passes_p90": 2.0, "passes_into_box_p90": 2.0,
            "through_balls_p90": 2.0, "att_p90_sb": 2.0, "xG_p90": 1.5,
        },
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


def _archetype_vectors_raw(group, features, scaler):
    """Convert a group's σ-offset archetype profiles into raw-unit prototype vectors.

    prototype[f] = group_mean[f] + σ[f] * group_std[f]; features not listed in a
    profile default to σ=0.0 (the group mean). Passing these raw vectors to
    ``_assign_labels_from_archetypes`` — which re-standardises with the same
    player-level scaler — recovers the σ-offsets in scaled space, so distances are
    measured in group-standard deviations instead of raw units.
    """
    means, scales = scaler.mean_, scaler.scale_
    return {
        name: {
            feature: means[i] + profile.get(feature, 0.0) * scales[i]
            for i, feature in enumerate(features)
        }
        for name, profile in GROUP_ARCHETYPES[group].items()
    }


def _label_threshold(n_features):
    """Dimension-aware label threshold: v1's 3.5 at 6 features scales with sqrt(n)."""
    return LABEL_THRESHOLD * np.sqrt(n_features / V1_FEATURE_SPAN)


def _assign_labels_from_archetypes(centroids, archetypes, feature_cols, scaler=None, threshold=3.5, fallback_label="Mixed Profile"):
    """Assign each cluster its true nearest archetype by Euclidean distance.

    Unlike the previous greedy-with-deduplication approach, this version lets
    multiple clusters share a label if that's genuinely their closest archetype.
    If no archetype is within ``threshold`` standardized units, the cluster is
    labelled ``fallback_label`` (default "Mixed Profile") instead of forcing a
    misleading name — per-group overrides live in ``GROUP_FALLBACK_LABEL``.

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
            labels[cluster_id] = fallback_label

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
        Optional label for log output (e.g. "GK" or "CB").

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


def _compute_dataset_hash(filepath: str) -> str:
    """SHA256 hash of the dataset file for change detection."""
    with open(filepath, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _fit_group(gdf, group, evaluate=False):
    """Cluster one position group and label it. Returns (grouped_df, artifacts)."""
    features = _available_features(gdf, GROUP_FEATURES[group])
    if not features:
        logger.warning("Group %s has no available features — skipped", group)
        return None, None

    data = gdf[features].fillna(0)
    scaler = StandardScaler()
    scaled = scaler.fit_transform(data)

    k = min(GROUP_K[group], len(gdf) - 1)
    if k < 1:
        logger.warning("Group %s has %d players — fewer than 2, skipped", group, len(gdf))
        return None, None

    kmeans = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=N_INIT)
    gdf = gdf.copy()
    gdf["cluster_id_v2"] = kmeans.fit_predict(scaled)

    centroids = gdf.groupby("cluster_id_v2")[features].mean()
    archetype_vectors = _archetype_vectors_raw(group, features, scaler)
    labels = _assign_labels_from_archetypes(
        centroids,
        archetype_vectors,
        features,
        scaler=scaler,
        threshold=_label_threshold(len(features)),
        fallback_label=GROUP_FALLBACK_LABEL.get(group, "Mixed Profile"),
    )
    gdf["playstyle_cluster_v2"] = gdf["cluster_id_v2"].map(labels)

    if evaluate and scaled.shape[0] >= 3 and len(np.unique(gdf["cluster_id_v2"])) >= 2:
        evaluate_clustering(scaled, gdf["cluster_id_v2"].values, prefix=group)

    artifacts = {"scaler": scaler, "kmeans": kmeans, "features": features}
    return gdf, artifacts


def group_and_cluster(df, evaluate=False):
    """Cluster the master dataset by ``position_v2`` group.

    One KMeans per group in ``GROUP_ORDER``, labeled against the group's
    archetypes. Players whose ``position_v2`` is outside ``GROUP_ORDER`` are
    warned about and excluded from the result.
    """
    if "position_v2" not in df.columns:
        raise ValueError("DataFrame has no 'position_v2' column — build it with build_master_dataset.py")

    unknown = df.loc[~df["position_v2"].isin(GROUP_ORDER), "position_v2"]
    if not unknown.empty:
        logger.warning(
            "Excluding %d players with position_v2 outside %s: %s",
            len(unknown), GROUP_ORDER, sorted(map(str, unknown.unique())),
        )

    parts = []
    for group in GROUP_ORDER:
        gdf = df[df["position_v2"] == group].copy()
        if gdf.empty:
            logger.warning("Group %s has no players — skipped", group)
            continue
        grouped, artifacts = _fit_group(gdf, group, evaluate=evaluate)
        if grouped is not None:
            parts.append(grouped)

    if not parts:
        return df[df["position_v2"].isin(GROUP_ORDER)].copy()
    return pd.concat(parts, ignore_index=True)


def _artifact_stem(group: str) -> str:
    """Filesystem-safe stem for a group name ('FB/WB' -> 'FB_WB')."""
    return group.replace("/", "_")


def _get_artifacts_paths_v2() -> dict[str, Path]:
    return {
        **{f"{group}_scaler": MODELS_DIR_V2 / f"{_artifact_stem(group)}_scaler.joblib" for group in GROUP_ORDER},
        **{f"{group}_kmeans": MODELS_DIR_V2 / f"{_artifact_stem(group)}_kmeans.joblib" for group in GROUP_ORDER},
        "cluster_labels": MODELS_DIR_V2 / "cluster_labels_v2.json",
    }


def _persist_models_v2(clustered, filepath: str):
    """Refit each group deterministically and persist scalers, KMeans, labels, metadata.

    ``clustered`` already carries ``cluster_id_v2``/``playstyle_cluster_v2`` from
    ``group_and_cluster``; the fitted objects are re-derived here (same seed →
    identical results) and written to ``models_v2/``. Never touches v1 ``models/``.
    """
    MODELS_DIR_V2.mkdir(exist_ok=True)
    paths = _get_artifacts_paths_v2()

    cluster_labels = {}
    group_counts = {}
    per_group_features = {}
    for group in GROUP_ORDER:
        gdf = clustered[clustered["position_v2"] == group]
        if gdf.empty:
            logger.info("Group %s empty — nothing persisted", group)
            continue
        _, artifacts = _fit_group(gdf, group, evaluate=False)
        if artifacts is None:
            continue
        joblib.dump(artifacts["scaler"], paths[f"{group}_scaler"])
        joblib.dump(artifacts["kmeans"], paths[f"{group}_kmeans"])
        label_map = (
            gdf.groupby("cluster_id_v2")["playstyle_cluster_v2"]
            .first()
            .to_dict()
        )
        cluster_labels[group] = {str(k): v for k, v in label_map.items()}
        group_counts[group] = int(len(gdf))
        per_group_features[group] = artifacts["features"]

    with open(paths["cluster_labels"], "w") as f:
        json.dump(cluster_labels, f)

    metadata = {
        "dataset_file": os.path.basename(filepath),
        "dataset_hash": _compute_dataset_hash(filepath),
        "row_count": int(clustered.shape[0]),
        "group_counts": group_counts,
        "group_features": per_group_features,
        "group_k": {g: min(GROUP_K[g], max(group_counts.get(g, 0) - 1, 1)) for g in GROUP_ORDER},
        "fit_timestamp": datetime.now().isoformat(),
        "sklearn_version": __import__("sklearn").__version__,
        "numpy_version": np.__version__,
        "joblib_version": joblib.__version__,
        "kmeans_params": {"random_state": RANDOM_STATE, "n_init": N_INIT},
        "label_threshold": LABEL_THRESHOLD,
    }
    with open(MODELS_DIR_V2 / "metadata_v2.json", "w") as f:
        json.dump(metadata, f, indent=2)

    logger.info("Saved v2 model artifacts to %s", MODELS_DIR_V2)


def _load_model_artifacts_v2(filepath: str) -> dict | None:
    """Load v2 persisted artifacts if they exist and match the current dataset hash."""
    paths = _get_artifacts_paths_v2()
    metadata_path = MODELS_DIR_V2 / "metadata_v2.json"

    if not all(p.exists() for p in paths.values()) or not metadata_path.exists():
        logger.info("No persisted v2 model artifacts found")
        return None

    with open(metadata_path) as f:
        metadata = json.load(f)

    current_hash = _compute_dataset_hash(filepath)
    if metadata.get("dataset_hash") != current_hash:
        logger.info("Dataset hash mismatch — invalidating persisted v2 model")
        return None

    try:
        artifacts = {}
        for group in GROUP_ORDER:
            scaler_path = paths[f"{group}_scaler"]
            kmeans_path = paths[f"{group}_kmeans"]
            if not scaler_path.exists() or not kmeans_path.exists():
                return None
            artifacts[group] = {
                "scaler": joblib.load(scaler_path),
                "kmeans": joblib.load(kmeans_path),
                "features": metadata["group_features"].get(group, GROUP_FEATURES[group]),
            }
        with open(paths["cluster_labels"]) as f:
            artifacts["cluster_labels"] = json.load(f)
        logger.info("Loaded v2 model from %s (fitted %s)", MODELS_DIR_V2, metadata["fit_timestamp"])
        return artifacts
    except Exception as e:
        logger.warning("Failed to load v2 persisted artifacts: %s", e)
        return None


def _apply_loaded_model_v2(df, artifacts) -> pd.DataFrame:
    """Apply loaded scalers + KMeans + label mappings to fresh data by position group."""
    parts = []
    for group in GROUP_ORDER:
        gdf = df[df["position_v2"] == group].copy()
        if gdf.empty:
            continue
        entry = artifacts.get(group)
        if entry is None:
            continue
        features = _available_features(gdf, entry["features"])
        if not features:
            continue
        scaled = entry["scaler"].transform(gdf[features].fillna(0))
        gdf["cluster_id_v2"] = entry["kmeans"].predict(scaled)
        cluster_names = {int(k): v for k, v in artifacts["cluster_labels"].get(group, {}).items()}
        gdf["playstyle_cluster_v2"] = gdf["cluster_id_v2"].map(cluster_names)
        parts.append(gdf)

    if not parts:
        return df[df["position_v2"].isin(GROUP_ORDER)].copy()
    return pd.concat(parts, ignore_index=True)


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    persist = "--persist" in sys.argv
    evaluate = "--evaluate" in sys.argv or persist

    try:
        logger.info("Loading data from %s ...", DATASET_PATH)
        data = pd.read_csv(DATASET_PATH)
        logger.info("Loaded %d rows", data.shape[0])

        artifacts = _load_model_artifacts_v2(DATASET_PATH) if persist else None
        if artifacts is not None:
            logger.info("Applying persisted v2 model (dataset unchanged)")
            clustered = _apply_loaded_model_v2(data, artifacts)
            from_cache = True
        else:
            clustered = group_and_cluster(data, evaluate=evaluate)
            from_cache = False
            if persist:
                logger.info("Persisting v2 model artifacts...")
                _persist_models_v2(clustered, DATASET_PATH)

        logger.info(
            "SUCCESS: %d players grouped into position-scoped playstyles%s",
            clustered.shape[0], " (from cache)" if from_cache else "",
        )
        for group in GROUP_ORDER:
            gdf = clustered[clustered["position_v2"] == group]
            if gdf.empty:
                continue
            dist = gdf["playstyle_cluster_v2"].value_counts()
            logger.info("\n%s (%d players):\n%s", group, len(gdf), dist)
    except Exception as e:
        logger.error("ERROR: %s", e)
