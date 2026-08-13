"""Tests for v2_features.py — the app-facing v2 load/filter/display/radar layer.

Pure helpers are tested on a small synthetic clustered frame; the "exactly these
5 archetypes are unrepresented" fact is pinned against the real master CSV
(guarded the same way as the engine suite).
"""
import pathlib

import pandas as pd
import pytest

import v2_features as vf
import v2_model_engine as ve

DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
MASTER_PATH = DATA_DIR / "wc2022_players_master.csv"

REAL_DATASET = pytest.mark.skipif(
    not MASTER_PATH.is_file(),
    reason="requires data/wc2022_players_master.csv (run build_master_dataset.py)",
)


def _synthetic_clustered_df():
    """A tiny clustered frame spanning GK + ST with the compare-stat columns."""
    return pd.DataFrame([
        {
            "player": "gk1", "player_label": "gk1", "squad": "br Brazil",
            "squad_display": "Brazil", "position_v2": "GK", "cluster_id_v2": 0,
            "playstyle_cluster_v2": "Shot Stopper",
            "Saves_p90": 3.0, "save_pct": 0.75, "gls_p90": 0.0, "Ast_p90": 0.0,
        },
        {
            "player": "gk2", "player_label": "gk2", "squad": "ar Argentina",
            "squad_display": "Argentina", "position_v2": "GK", "cluster_id_v2": 1,
            "playstyle_cluster_v2": "Traditional Goalkeeper",
            "Saves_p90": 1.0, "save_pct": 0.60, "gls_p90": 0.0, "Ast_p90": 0.0,
        },
        {
            "player": "st1", "player_label": "st1", "squad": "fr France",
            "squad_display": "France", "position_v2": "ST", "cluster_id_v2": 0,
            "playstyle_cluster_v2": "Complete Forward",
            "Saves_p90": 0.0, "save_pct": 0.0, "gls_p90": 0.8, "Ast_p90": 0.1,
        },
        {
            "player": "st2", "player_label": "st2", "squad": "ar Argentina",
            "squad_display": "Argentina", "position_v2": "ST", "cluster_id_v2": 1,
            "playstyle_cluster_v2": "False 9",
            "Saves_p90": 0.0, "save_pct": 0.0, "gls_p90": 0.4, "Ast_p90": 0.5,
        },
    ])


def test_filter_v2_dataframe_groups():
    df = _synthetic_clustered_df()
    result = vf.filter_v2_dataframe(df, groups=["ST"])
    assert set(result["position_v2"]) == {"ST"}
    assert len(result) == 2


def test_filter_v2_dataframe_squads_and_playstyles():
    df = _synthetic_clustered_df()
    result = vf.filter_v2_dataframe(df, squads=["Argentina"], playstyles=["False 9"])
    assert len(result) == 1
    assert result.iloc[0]["player"] == "st2"


def test_filter_v2_dataframe_empty_result():
    df = _synthetic_clustered_df()
    result = vf.filter_v2_dataframe(df, groups=["CB"])
    assert result.empty


def test_squad_display_strips_country_code():
    assert vf._squad_display("au Australia") == "Australia"
    assert vf._squad_display("wls Wales") == "Wales"
    # A value with no leading lowercase code is left intact.
    assert vf._squad_display("United States") == "United States"
    assert vf._squad_display(None) is None


def test_add_v2_percentiles_is_position_scoped():
    df = vf.add_v2_percentiles(_synthetic_clustered_df())
    # gls_p90 is a compare stat for ST (not GK): GK rows stay NaN, ST rows ranked.
    assert df.loc[df["position_v2"] == "GK", "gls_p90_percentile"].isna().all()
    assert df.loc[df["position_v2"] == "ST", "gls_p90_percentile"].notna().all()
    # Saves_p90 is a compare stat for GK only.
    assert df.loc[df["position_v2"] == "ST", "Saves_p90_percentile"].isna().all()
    assert df.loc[df["position_v2"] == "GK", "Saves_p90_percentile"].notna().all()
    # Within ST, the higher gls_p90 gets the higher percentile.
    st = df[df["position_v2"] == "ST"].sort_values("gls_p90")
    assert st["gls_p90_percentile"].is_monotonic_increasing


def test_get_unrepresented_archetypes_synthetic():
    df = _synthetic_clustered_df()
    unrep = vf.get_unrepresented_archetypes(df)
    # "Shot Stopper" is assigned; every other of the 20 archetypes is not.
    assert "Shot Stopper" not in unrep
    assert "Sweeper Keeper" in unrep
    assert "Poacher" in unrep


def test_build_distribution_dataframe_counts():
    df = _synthetic_clustered_df()
    dist = vf.build_distribution_dataframe(df)
    # 20 archetype rows + fallback rows (Traditional Goalkeeper for the GK row).
    assert (dist["kind"] == "archetype").sum() == 20
    stopper = dist[(dist["label"] == "Shot Stopper")].iloc[0]
    assert stopper["count"] == 1
    fb = dist[(dist["label"] == "Traditional Goalkeeper") & (dist["kind"] == "fallback")]
    assert fb.iloc[0]["count"] == 1


def test_v2_friendly_label_representative():
    assert vf.v2_friendly_label("Saves_p90") == "Saves per 90"
    assert vf.v2_friendly_label("save_pct") == "Save %"
    assert vf.v2_friendly_label("gls_p90") == "Goals per 90"
    assert vf.v2_friendly_label("att_p90_sb") == "Take-ons per 90"
    assert vf.v2_friendly_label("npxG_per_shot") == "npxG per Shot"


def test_format_v2_display_table():
    df = _synthetic_clustered_df()
    out = vf.format_v2_display_table(df, ["player", "position_v2", "playstyle_cluster_v2"])
    assert out.columns.tolist() == ["#", "Player", "Position", "Playstyle"]
    assert len(out) == len(df)


@REAL_DATASET
def test_master_unrepresented_archetypes_exact():
    """The 5 unrepresented archetypes are pinned (taxonomy vs WC2022 reality)."""
    master = pd.read_csv(MASTER_PATH)
    clustered = ve.group_and_cluster(master)
    unrep = vf.get_unrepresented_archetypes(clustered)
    assert unrep == {
        "Sweeper Keeper", "Wingback", "Box-to-Box Midfielder",
        "Advanced Playmaker", "Poacher",
    }


@REAL_DATASET
def test_master_radar_data():
    """Radar data computes for a real player with a non-empty axis set."""
    master = pd.read_csv(MASTER_PATH)
    clustered = ve.group_and_cluster(master)
    messi = clustered[clustered["player"] == "Lionel Messi"].iloc[0]
    radar = vf.build_player_radar_data(clustered, messi, "ST")
    assert radar["assigned"] == "False 9"
    assert radar["axes"]
    assert len(radar["player_values"]) == len(radar["axes"])
    assert len(radar["reference_values"]) == len(radar["axes"])
    # Distances cover every ST archetype (incl. the unpopulated Poacher).
    assert set(radar["distances"]) == set(ve.GROUP_ARCHETYPES["ST"])


# --- chart smoke tests -------------------------------------------------------

def test_build_v2_distribution_chart_returns_figure():
    from charts import build_v2_distribution_chart
    dist = vf.build_distribution_dataframe(_synthetic_clustered_df())
    fig = build_v2_distribution_chart(dist)
    assert fig is not None
    # One bar trace per populated position group.
    assert len(fig.data) >= 1


def test_build_v2_archetype_radar_chart_returns_figure():
    from charts import build_v2_archetype_radar_chart
    labels = ["Goals per 90", "Assists per 90", "Shots per 90"]
    fig = build_v2_archetype_radar_chart("Messi", "False 9", labels, [1.0, 2.0, 1.5], [2.0, 2.5, 2.0])
    assert fig is not None
    assert len(fig.data) == 2  # player + prototype
