"""App-facing v2 layer: cached load, filtering, display, and radar helpers.

The v2 engine (``v2_model_engine.py``) is deliberately headless (no Streamlit
import) so it can run ``--persist`` / ``--evaluate`` standalone. This module is
the Streamlit-facing counterpart that the app imports: it caches the CSV read +
clustering, exposes the v2 filter/percentile/display helpers, and computes the
σ-space radar data the explorer charts. The 20-archetype taxonomy and per-group
feature lists are imported from ``v2_model_engine`` — never redefined here
(Constitution §14 rule 2: no second source of truth).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

import v2_model_engine as ve


# --- per-group H2H compare stats (display-level constant, mirrors v1's
# POSITION_COMPARE_STATS; each key is a verified GROUP_FEATURES column) ------
V2_COMPARE_STATS = {
    "GK": (
        ["Saves_p90", "save_pct", "goals_prevented_p90", "passes_p90", "long_passes_p90"],
        ["Saves per 90", "Save %", "Goals Prevented per 90", "Passes per 90", "Long Passes per 90"],
    ),
    "CB": (
        ["clearances_p90", "aerial_duels_won_p90", "Int_p90", "prog_passes_p90", "pass_completion_pct"],
        ["Clearances per 90", "Aerial Duels Won per 90", "Interceptions per 90", "Progressive Passes per 90", "Pass Completion %"],
    ),
    "FB/WB": (
        ["Crs_p90", "att_p90_sb", "prgcarries_p90_sb", "TklW_p90", "Ast_p90"],
        ["Crosses per 90", "Take-ons per 90", "Progressive Carries per 90", "Tackles Won per 90", "Assists per 90"],
    ),
    "MF": (
        ["gls_p90", "Ast_p90", "key_passes_p90", "TklW_p90", "Int_p90", "prog_passes_p90"],
        ["Goals per 90", "Assists per 90", "Key Passes per 90", "Tackles Won per 90", "Interceptions per 90", "Progressive Passes per 90"],
    ),
    "Wide": (
        ["gls_p90", "xG_p90", "Ast_p90", "att_p90_sb", "Crs_p90", "prgcarries_p90_sb"],
        ["Goals per 90", "xG per 90", "Assists per 90", "Take-ons per 90", "Crosses per 90", "Progressive Carries per 90"],
    ),
    "ST": (
        ["gls_p90", "xG_p90", "shots_p90", "conversion_pct", "Ast_p90", "aerial_duels_won_p90"],
        ["Goals per 90", "xG per 90", "Shots per 90", "Conversion %", "Assists per 90", "Aerial Duels Won per 90"],
    ),
}


V2_DISPLAY_LABELS = {
    "player": "Player",
    "player_display": "Player",
    "squad_display": "Squad",
    "position_v2": "Position Group",
    "position_detail": "Position",
    "playstyle_cluster_v2": "Playstyle",
}

# Token replacements for v2 feature column names (camelCase acronyms + specials).
_TOKEN_LABELS = {
    "TklW": "Tackles Won",
    "Int": "Interceptions",
    "Crs": "Crosses",
    "Ast": "Assists",
    "Fls": "Fouls Committed",
    "Fld": "Fouls Drawn",
    "prog": "Progressive",
    "prgcarries": "Progressive Carries",
    "att": "Take-ons",
    "gls": "Goals",
    "6yard": "6-yard",
}


def v2_friendly_label(feature):
    """Turn a v2 feature column into a plain-English axis label.

    v2 columns mix per-90 rates (``_p90``), percentages (``_pct``), a StatsBomb
    suffix (``_sb``), and camelCase acronyms (``TklW``, ``Int``, ``Crs``, …).
    e.g. ``"Saves_p90"`` → ``"Saves per 90"``, ``"save_pct"`` → ``"Save %"``.
    """
    if not isinstance(feature, str):
        return str(feature)
    if feature == "npxG_per_shot":
        return "npxG per Shot"

    label = feature[:-3] if feature.endswith("_sb") else feature
    suffix = ""
    if label.endswith("_p90"):
        label, suffix = label[:-4], " per 90"
    elif label.endswith("_pct"):
        label, suffix = label[:-4], " %"

    words = []
    for token in label.split("_"):
        if not token:
            continue
        if token in ("xG", "npxG"):
            words.append(token)
        elif token in _TOKEN_LABELS:
            words.append(_TOKEN_LABELS[token])
        else:
            words.append(token.title())
    if not words:
        words = [label]
    out = " ".join(words)
    return f"{out}{suffix}" if suffix else out


def format_v2_display_table(df, columns):
    """Select columns and render a v1-style display table with a '#' index."""
    display_df = df[columns].copy().reset_index(drop=True)
    display_df.insert(0, "#", range(1, len(display_df) + 1))
    rename_map = {
        col: V2_DISPLAY_LABELS.get(col, v2_friendly_label(col)) for col in columns
    }
    return display_df.rename(columns=rename_map)


def _squad_display(squad):
    """FBref squad strings are ``"au Australia"`` — strip the leading country code."""
    if not isinstance(squad, str):
        return squad
    parts = squad.split(" ", 1)
    if len(parts) == 2 and len(parts[0]) <= 3 and parts[0].islower():
        return parts[1]
    return squad


def country_flag(squad):
    """Flag emoji for a player's national team (FBref ``"au Australia"`` → 🇦🇺)."""
    if not isinstance(squad, str):
        return ""
    code = squad.split(" ")[0].upper()
    special = {
        "ENG": "\U0001f3f4\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067\U000e007f",  # England
        "WLS": "\U0001f3f4\U000e0067\U000e0062\U000e0077\U000e006c\U000e0073\U000e007f",  # Wales
    }
    if code in special:
        return special[code]
    if len(code) == 2 and code.isalpha():
        return chr(0x1F1E6 + ord(code[0]) - 65) + chr(0x1F1E6 + ord(code[1]) - 65)
    return ""


def _add_player_label(df):
    """Add ``player_label`` (name, squad-suffixed only for duplicate names)."""
    df = df.copy()
    name_counts = df["player"].value_counts()
    duplicated = set(name_counts[name_counts > 1].index)
    df["player_label"] = df["player"]
    dup_mask = df["player"].isin(duplicated)
    df.loc[dup_mask, "player_label"] = (
        df.loc[dup_mask, "player"] + " (" + df.loc[dup_mask, "squad"].astype(str) + ")"
    )
    return df


@st.cache_data
def load_v2_clustered_data(filepath):
    """Load + cluster the v2 master CSV and add display columns.

    Fits fresh via ``group_and_cluster`` (deterministic seed 42, <1s for 217
    rows) rather than loading persisted artifacts — this sidesteps the
    "stale labels on code change" persistence caveat in CLAUDE.md. ``models_v2/``
    remains for the headless ``--persist`` / ``--evaluate`` workflow only.
    """
    master = pd.read_csv(filepath)
    clustered = ve.group_and_cluster(master)
    clustered = _add_player_label(clustered)
    clustered["squad_display"] = clustered["squad"].map(_squad_display)
    clustered["flag"] = clustered["squad"].map(country_flag)
    clustered["player_display"] = clustered["flag"] + " " + clustered["player"]
    clustered = add_v2_percentiles(clustered)
    return clustered


def filter_v2_dataframe(df, positions=None, squads=None, playstyles=None):
    """Filter the clustered v2 frame on fine position / squad / playstyle."""
    filtered = df.copy()
    if positions:
        filtered = filtered[filtered["position_detail"].isin(positions)]
    if squads:
        filtered = filtered[filtered["squad_display"].isin(squads)]
    if playstyles:
        filtered = filtered[filtered["playstyle_cluster_v2"].isin(playstyles)]
    return filtered


def add_v2_percentiles(df):
    """Add position_v2-scoped percentiles for the H2H compare stats.

    A stat is only ranked within the position group(s) that list it in
    ``V2_COMPARE_STATS`` (irrelevant stat-position pairs stay NaN — mirrors v1's
    ML-02 fix).
    """
    df = df.copy()
    all_stats = sorted({stat for keys, _ in V2_COMPARE_STATS.values() for stat in keys})
    for stat in all_stats:
        if stat not in df.columns:
            continue
        col = f"{stat}_percentile"
        df[col] = float("nan")
        for group, (keys, _) in V2_COMPARE_STATS.items():
            if stat not in keys:
                continue
            mask = df["position_v2"] == group
            df.loc[mask, col] = df.loc[mask, stat].fillna(0).rank(pct=True) * 100
    return df


def get_compare_stats_for_group(group):
    """Return (stat_keys, display_names) for a position_v2 group, or the MF set."""
    if group in V2_COMPARE_STATS:
        return V2_COMPARE_STATS[group]
    return V2_COMPARE_STATS["MF"]


def get_unrepresented_archetypes(clustered_df):
    """Archetypes across all groups that no player was assigned to."""
    represented = set(clustered_df["playstyle_cluster_v2"].dropna().unique())
    return {
        name
        for group in ve.GROUP_ORDER
        for name in ve.GROUP_ARCHETYPES[group]
        if name not in represented
    }


def build_distribution_dataframe(clustered_df):
    """One row per archetype (count 0 = unrepresented) + a row per non-empty fallback label.

    Duplicate labels (e.g. two "Attacking Fullback" clusters) are summed by label.
    """
    rows = []
    for group in ve.GROUP_ORDER:
        g = clustered_df[clustered_df["position_v2"] == group]
        for archetype in ve.GROUP_ARCHETYPES[group]:
            count = int((g["playstyle_cluster_v2"] == archetype).sum())
            rows.append({
                "position_v2": group,
                "label": archetype,
                "count": count,
                "kind": "archetype",
            })
        fallback = ve.GROUP_FALLBACK_LABEL[group]
        fb_count = int((g["playstyle_cluster_v2"] == fallback).sum())
        if fb_count > 0:
            rows.append({
                "position_v2": group,
                "label": fallback,
                "count": fb_count,
                "kind": "fallback",
            })
    return pd.DataFrame(rows)


# --- σ-space radar helpers ---------------------------------------------------

def _group_sigma_profile(group_df, player_row, features):
    """Standardize the player's features against their group (ddof=0, fillna 0)."""
    vals = group_df[features].fillna(0)
    mean = vals.mean()
    std = vals.std(ddof=0).replace(0.0, 1.0)
    player_vals = player_row[features].astype(float).fillna(0)
    return (player_vals - mean) / std


def _archetype_distances(player_sigma, group):
    """Euclidean σ-distance from the player to each archetype prototype in the group."""
    features = ve.GROUP_FEATURES[group]
    player_vec = player_sigma.values
    distances = {}
    for name, offsets in ve.GROUP_ARCHETYPES[group].items():
        proto = np.array([offsets.get(f, 0.0) for f in features], dtype=float)
        distances[name] = float(np.linalg.norm(player_vec - proto))
    return distances


def _group_percentile(group_df, player_row, feature):
    """Position-scoped percentile (0-100) of one player on one feature."""
    col = group_df[feature].astype(float).fillna(0)
    val = player_row[feature]
    player_val = float(val) if pd.notna(val) else 0.0
    return round(float((col <= player_val).mean()) * 100.0, 1)


def build_player_radar_data(full_df, player_row, group):
    """Compute percentile-radar data for a player within their position group.

    The radar axes are the player's assigned archetype's defining traits (or the
    *nearest* archetype's, for a fallback-labelled player). Each value is the
    player's position-scoped **percentile (0-100)** on that trait, so "Goals per
    90: 95" reads as "95th percentile among this position group". σ-distances to
    every archetype are still returned for the fit/similarity bars.
    """
    features = ve.GROUP_FEATURES[group]
    group_df = full_df[full_df["position_v2"] == group]
    player_sigma = _group_sigma_profile(group_df, player_row, features)
    distances = _archetype_distances(player_sigma, group)

    assigned = player_row["playstyle_cluster_v2"]
    nearest = min(distances, key=distances.get)
    reference = assigned if assigned in ve.GROUP_ARCHETYPES[group] else nearest
    offsets = ve.GROUP_ARCHETYPES[group][reference]
    axes = [f for f in features if offsets.get(f, 0.0) != 0.0]

    return {
        "player_name": player_row["player"],
        "group": group,
        "assigned": assigned,
        "nearest": nearest,
        "reference": reference,
        "is_fallback": assigned not in ve.GROUP_ARCHETYPES[group],
        "axes": axes,
        "axis_labels": [v2_friendly_label(f) for f in axes],
        "player_values": [_group_percentile(group_df, player_row, f) for f in axes],
        "distances": distances,
    }


def archetype_traits(group, name):
    """An archetype's defining traits as (friendly label, σ-offset), sorted desc."""
    offsets = ve.GROUP_ARCHETYPES[group][name]
    return sorted(
        ((v2_friendly_label(feature), sigma) for feature, sigma in offsets.items() if sigma > 0),
        key=lambda item: -item[1],
    )


def all_archetypes():
    """All 20 archetypes as (group, name) pairs in display order."""
    return [(group, name) for group in ve.GROUP_ORDER for name in ve.GROUP_ARCHETYPES[group]]


def nearest_players_to_archetype(full_df, group, name, top_n=5):
    """Players in the group nearest (σ-space) to an archetype prototype."""
    features = ve.GROUP_FEATURES[group]
    offsets = ve.GROUP_ARCHETYPES[group][name]
    group_df = full_df[full_df["position_v2"] == group]
    vals = group_df[features].astype(float).fillna(0)
    mean = vals.mean()
    std = vals.std(ddof=0).replace(0.0, 1.0)
    sigma = (vals - mean) / std
    proto = np.array([offsets.get(f, 0.0) for f in features], dtype=float)
    dist = np.linalg.norm(sigma.values - proto, axis=1)
    ranked = group_df.assign(_dist=dist).nsmallest(top_n, "_dist")
    cols = ["player", "playstyle_cluster_v2"] + (
        ["squad_display"] if "squad_display" in ranked.columns else []
    )
    return ranked[cols].to_dict("records")
