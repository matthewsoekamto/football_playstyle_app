"""Tests for v2_model_engine.py — the position-scoped KMeans engine (P7).

Synthetic tests use a deterministic master-shaped frame (one group column +
all feature columns across GROUP_FEATURES). Real-dataset tests are guarded on
``data/wc2022_players_master.csv`` existing, mirroring the parser suite.
"""
import sys
import importlib

import numpy as np
import pandas as pd
import pytest

import v2_model_engine as ve

DATA_DIR = __import__("pathlib").Path(__file__).resolve().parent.parent / "data"
MASTER_PATH = DATA_DIR / "wc2022_players_master.csv"

ALL_FEATURES = sorted({f for feats in ve.GROUP_FEATURES.values() for f in feats})

REAL_DATASET = pytest.mark.skipif(
    not MASTER_PATH.is_file(),
    reason="requires data/wc2022_players_master.csv (run build_master_dataset.py)",
)


def _engine_frame(rows_per_group: int = 10, seed: int = 7) -> pd.DataFrame:
    """Deterministic master-shaped frame with enough rows per group to fit k."""
    rng = np.random.default_rng(seed)
    rows = []
    for group in ve.GROUP_ORDER:
        for i in range(rows_per_group):
            row = {"player": f"{group}-{i}", "position_v2": group}
            for feat in ALL_FEATURES:
                # Plausible feature scale: most counts/per-90 in 0-6, ratios 0-1,
                # GK saves up to ~5. Arbitrary but deterministic.
                row[feat] = float(rng.uniform(0.0, 1.0)) * 6.0
            rows.append(row)
    return pd.DataFrame(rows)


def _separable_group_frame(group: str, rows_per_cluster: int = 20, seed: int = 11) -> pd.DataFrame:
    """One group's rows drawn from GROUP_K[group] well-separated Gaussian blobs.

    Each cluster is offset +(c+1)*5.0 on EVERY feature, so after StandardScaler the
    blobs sit ~50σ apart in every dimension — KMeans(k) recovers them exactly and
    bootstrap refits are stable (ARI ~ 1). A single shifted feature would be drowned
    by the remaining ~sqrt(dims) noise dims once scaled, so all features must carry
    the separation. rows_per_cluster=20 makes a whole blob being absent from a
    bootstrap sample effectively impossible (0.5**40).
    """
    feats = ve.GROUP_FEATURES[group]
    k = ve.GROUP_K[group]
    rng = np.random.default_rng(seed)
    rows = []
    for c in range(k):
        offset = (c + 1) * 5.0
        for i in range(rows_per_cluster):
            row = {"player": f"{group}-{c}-{i}", "position_v2": group}
            for f in feats:
                row[f] = float(rng.normal(offset, 0.1))
            rows.append(row)
    return pd.DataFrame(rows)


def _group_bootstrap(frame: pd.DataFrame, group: str) -> dict:
    """Fit one group (evaluate=False) and return its bootstrap stability dict."""
    gdf, _ = ve._fit_group(frame, group, evaluate=False)
    assert gdf is not None, f"group {group} failed to fit"
    feats = ve.GROUP_FEATURES[group]
    return ve.evaluate_bootstrap_stability(
        gdf[feats].fillna(0).values,
        gdf["cluster_id_v2"].values,
        min(ve.GROUP_K[group], len(gdf) - 1),
        prefix=group,
    )


BOOTSTRAP_KEYS = frozenset({
    "bootstrap_ari_mean", "bootstrap_ari_std",
    "bootstrap_silhouette_mean", "bootstrap_silhouette_std",
    "bootstrap_davies_bouldin_mean", "bootstrap_davies_bouldin_std",
    "bootstrap_degenerate_fraction",
})


# --- constant structure -----------------------------------------------------

def test_group_order_and_k():
    """Six groups, k values match the spec (2/3/3/5/3/3), 20 archetypes total.

    ST is k=3 by ADR-011: its 4th archetype (Poacher) is retained in the taxonomy
    but unpopulated, so only 3 of 4 ST archetypes are assigned.
    """
    assert ve.GROUP_ORDER == ["GK", "CB", "FB/WB", "MF", "Wide", "ST"]
    assert ve.GROUP_K == {"GK": 2, "CB": 3, "FB/WB": 3, "MF": 5, "Wide": 3, "ST": 3}
    n_arch = sum(len(ve.GROUP_ARCHETYPES[g]) for g in ve.GROUP_ORDER)
    assert n_arch == 20, "PLAYSTYLE_SPEC defines exactly 20 archetypes"


def test_archetype_keys_subset_of_group_features():
    """Every archetype references only columns present in its group's feature set."""
    for group in ve.GROUP_ORDER:
        allowed = set(ve.GROUP_FEATURES[group])
        for name, profile in ve.GROUP_ARCHETYPES[group].items():
            unknown = set(profile) - allowed
            assert not unknown, f"{group}/{name} references non-group features {unknown}"


def test_pkwon_pkcon_not_in_any_group_set():
    """Fully-null FBref penalty columns were dropped at P6 and must stay out."""
    for group, feats in ve.GROUP_FEATURES.items():
        assert "pkwon" not in feats and "pkcon" not in feats, group
        assert "PKwon_p90" not in feats and "PKcon_p90" not in feats, group


def test_archetype_values_are_sigma_offsets():
    """Prototype values are small σ-offsets (0..~2.5), not raw units."""
    for group in ve.GROUP_ORDER:
        for name, profile in ve.GROUP_ARCHETYPES[group].items():
            for feat, sigma in profile.items():
                assert -0.01 <= sigma <= 3.5, (group, name, feat, sigma)


def test_gk_fallback_label_is_traditional_goalkeeper():
    """Review-gate decision: the homogeneous GK pool's fallback is 'Traditional Goalkeeper';
    other groups keep the honest 'Mixed Profile' for their rare outliers."""
    assert ve.GROUP_FALLBACK_LABEL["GK"] == "Traditional Goalkeeper"
    for group in ("CB", "FB/WB", "MF", "Wide", "ST"):
        assert ve.GROUP_FALLBACK_LABEL[group] == "Mixed Profile"


# --- clustering behaviour (synthetic) --------------------------------------

def test_determinism():
    """Two runs on the same input produce identical cluster ids and labels."""
    df = _engine_frame()
    a = ve.group_and_cluster(df.copy())
    b = ve.group_and_cluster(df.copy())
    assert a["cluster_id_v2"].tolist() == b["cluster_id_v2"].tolist()
    assert a["playstyle_cluster_v2"].tolist() == b["playstyle_cluster_v2"].tolist()


def test_all_rows_labeled():
    """Every clustered row gets a playstyle_cluster_v2 (archetype or Mixed)."""
    df = ve.group_and_cluster(_engine_frame())
    assert len(df) == len(_engine_frame())
    assert df["playstyle_cluster_v2"].notna().all()
    assert df["cluster_id_v2"].notna().all()


def test_label_provenance():
    """Labels come from the group's archetypes or the group's honest fallback label."""
    df = ve.group_and_cluster(_engine_frame())
    for group in ve.GROUP_ORDER:
        g = df[df["position_v2"] == group]
        allowed = set(ve.GROUP_ARCHETYPES[group]) | {ve.GROUP_FALLBACK_LABEL[group]}
        assert set(g["playstyle_cluster_v2"].unique()) <= allowed, group


def test_small_group_guard():
    """A group smaller than its k (or a single player) does not crash."""
    frame = _engine_frame(rows_per_group=2)  # 2 rows vs k=3..5 for most groups
    df = ve.group_and_cluster(frame)
    assert len(df) == len(frame)
    assert df["playstyle_cluster_v2"].notna().all()


def test_unknown_position_excluded():
    """Players outside GROUP_ORDER are excluded from the clustered result."""
    frame = _engine_frame(rows_per_group=3)
    frame = pd.concat(
        [frame, pd.DataFrame([{"player": "odd", "position_v2": "DM"}])],
        ignore_index=True,
    )
    for feat in ALL_FEATURES:
        frame.loc[frame["position_v2"] == "DM", feat] = 0.0
    df = ve.group_and_cluster(frame)
    assert "odd" not in set(df["player"])
    assert set(df["position_v2"].unique()) <= set(ve.GROUP_ORDER)


def test_missing_position_v2_raises():
    with pytest.raises(ValueError):
        ve.group_and_cluster(pd.DataFrame({"player": ["x"]}))


# --- persistence ------------------------------------------------------------

def test_persistence_roundtrip(tmp_path, monkeypatch):
    """Persist then load with an unchanged dataset returns usable artifacts."""
    monkeypatch.setattr(ve, "MODELS_DIR_V2", tmp_path)
    df = _engine_frame(rows_per_group=4)
    clustered = ve.group_and_cluster(df)

    master_file = tmp_path / "master.csv"
    df.to_csv(master_file, index=False)

    ve._persist_models_v2(clustered, str(master_file))
    artifacts = ve._load_model_artifacts_v2(str(master_file))
    assert artifacts is not None
    assert set(artifacts) == set(ve.GROUP_ORDER) | {"cluster_labels"}

    reapplied = ve._apply_loaded_model_v2(df, artifacts)
    assert len(reapplied) == len(df)
    assert reapplied["playstyle_cluster_v2"].notna().all()
    # Applying the persisted model reproduces the fresh fit's labels.
    assert reapplied["playstyle_cluster_v2"].tolist() == clustered["playstyle_cluster_v2"].tolist()


def test_hash_mismatch_invalidates(tmp_path, monkeypatch):
    """A changed dataset file (different hash) makes the loader return None."""
    monkeypatch.setattr(ve, "MODELS_DIR_V2", tmp_path)
    df = _engine_frame(rows_per_group=4)
    clustered = ve.group_and_cluster(df)

    master_file = tmp_path / "master.csv"
    df.to_csv(master_file, index=False)
    ve._persist_models_v2(clustered, str(master_file))
    assert ve._load_model_artifacts_v2(str(master_file)) is not None

    df.to_csv(master_file, index=False)  # identical content -> same hash
    df.rename(columns={"player": "player2"}).to_csv(tmp_path / "master2.csv", index=False)
    assert ve._load_model_artifacts_v2(str(tmp_path / "master2.csv")) is None


def test_import_graph_no_streamlit():
    """v2_model_engine runs headless — importing it must not pull in streamlit."""
    sys.modules.pop("v2_model_engine", None)
    before = set(sys.modules)
    importlib.import_module("v2_model_engine")
    new = set(sys.modules) - before
    assert not any(m == "streamlit" or m.startswith("streamlit.") for m in new)
    assert "model_engine" not in new and "data_loader" not in new


# --- bootstrap stability (P8) ------------------------------------------------

def test_bootstrap_deterministic():
    """Same input + same seed -> byte-identical bootstrap metrics."""
    a = _group_bootstrap(_separable_group_frame("GK"), "GK")
    b = _group_bootstrap(_separable_group_frame("GK"), "GK")
    assert a == b


def test_bootstrap_keys_and_ari_bounds():
    """Uniform-noise data: full key set, ARI in [0,1], bounded std/degen, finite."""
    res = _group_bootstrap(_engine_frame(), "GK")
    assert set(res) == BOOTSTRAP_KEYS
    assert 0.0 <= res["bootstrap_ari_mean"] <= 1.0
    assert 0.0 <= res["bootstrap_ari_std"] <= 0.5  # max sample std for [0,1] data
    assert 0.0 <= res["bootstrap_degenerate_fraction"] <= 1.0
    assert np.isfinite(res["bootstrap_ari_mean"])
    assert np.isfinite(res["bootstrap_ari_std"])


def test_bootstrap_high_stability_on_separable():
    """Well-separated blobs reproduce the deployed partition under resampling."""
    for group in ("GK", "CB", "ST"):
        res = _group_bootstrap(_separable_group_frame(group), group)
        assert res["bootstrap_ari_mean"] >= 0.9, (group, res["bootstrap_ari_mean"])
        assert res["bootstrap_degenerate_fraction"] <= 0.05, (group, res["bootstrap_degenerate_fraction"])


def test_bootstrap_refit_variance_finite():
    """Refit silhouette/DB on separable data are finite and near-optimal."""
    res = _group_bootstrap(_separable_group_frame("GK"), "GK")
    for key in ("bootstrap_silhouette_mean", "bootstrap_silhouette_std",
                "bootstrap_davies_bouldin_mean", "bootstrap_davies_bouldin_std"):
        assert np.isfinite(res[key]), key
    assert res["bootstrap_silhouette_mean"] >= 0.9
    assert res["bootstrap_davies_bouldin_mean"] <= 0.5


def test_bootstrap_uniform_frame_is_low_stability():
    """Uniform-noise data must NOT be reported as stable (ARI well below 1)."""
    res = _group_bootstrap(_engine_frame(), "GK")
    assert res["bootstrap_ari_mean"] < 0.7


def test_bootstrap_integration_does_not_change_clustering():
    """evaluate=True runs bootstrap through _fit_group but leaves the partition alone."""
    base = ve.group_and_cluster(_engine_frame())
    ev = ve.group_and_cluster(_engine_frame(), evaluate=True)
    assert base["cluster_id_v2"].tolist() == ev["cluster_id_v2"].tolist()
    assert base["playstyle_cluster_v2"].tolist() == ev["playstyle_cluster_v2"].tolist()


def test_bootstrap_small_group_returns_nan():
    """n<3 and k>=n are skipped with an all-NaN dict, never a raise."""
    tiny = ve.evaluate_bootstrap_stability(np.zeros((2, 4)), np.array([0, 1]), 1, prefix="tiny")
    assert all(np.isnan(v) for v in tiny.values())
    kge = ve.evaluate_bootstrap_stability(np.zeros((4, 4)), np.array([0, 0, 1, 1]), 4)
    assert all(np.isnan(v) for v in kge.values())


# --- real dataset (guarded) -------------------------------------------------

@REAL_DATASET
def test_master_group_features_available():
    """Every group's feature set is fully present in the real master CSV."""
    master = pd.read_csv(MASTER_PATH)
    missing_by_group = {
        g: [f for f in feats if f not in master.columns]
        for g, feats in ve.GROUP_FEATURES.items()
    }
    assert not any(missing_by_group.values()), missing_by_group


@REAL_DATASET
def test_master_data_fixes():
    """P6 data fixes hold on the real master: bounded ratios, no overflow.

    pkwon/pkcon stay as null FBref leftovers in the CSV but are excluded from
    every GROUP_FEATURES set (see test_pkwon_pkcon_not_in_any_group_set).
    """
    master = pd.read_csv(MASTER_PATH)
    assert master["conversion_pct"].between(0, 1).all(), "conversion_pct overflow regressed"
    assert master["dribble_success_pct"].notna().all()


@REAL_DATASET
def test_master_labels_not_degenerate():
    """Every position group yields a non-trivial archetype label — no 100% Mixed."""
    master = pd.read_csv(MASTER_PATH)
    df = ve.group_and_cluster(master)
    assert len(df) == 217
    assert df["playstyle_cluster_v2"].notna().all()
    for group in ve.GROUP_ORDER:
        g = df[df["position_v2"] == group]
        labeled = g["playstyle_cluster_v2"].isin(ve.GROUP_ARCHETYPES[group])
        assert labeled.any(), f"{group} produced no archetype labels (all Mixed Profile)"


@REAL_DATASET
def test_master_st_no_duplicate_label_no_micro_cluster():
    """ST k=3 (ADR-011): three clusters, no duplicate archetype label, no micro-cluster.

    Locks out the k=4 failure mode — a 2-player Messi/Memphis micro-cluster and two
    clusters both labelled "False 9".
    """
    master = pd.read_csv(MASTER_PATH)
    st = ve.group_and_cluster(master)
    st = st[st["position_v2"] == "ST"]
    sizes = st.groupby("cluster_id_v2").size()
    assert len(sizes) == 3
    assert sizes.min() >= 3, f"micro-cluster regressed: sizes {sizes.tolist()}"
    labels_per_cluster = st.groupby("cluster_id_v2")["playstyle_cluster_v2"].first()
    assert labels_per_cluster.nunique() == len(labels_per_cluster), (
        f"duplicate archetype label regressed: {labels_per_cluster.tolist()}"
    )


@REAL_DATASET
def test_master_bootstrap_stability_runs():
    """Bootstrap stability is finite and in-range on the real WC 2022 master."""
    master = pd.read_csv(MASTER_PATH)
    clustered = ve.group_and_cluster(master)
    for group in ve.GROUP_ORDER:
        gdf = clustered[clustered["position_v2"] == group]
        res = _group_bootstrap(gdf, group)
        assert set(res) == BOOTSTRAP_KEYS
        assert 0.0 <= res["bootstrap_ari_mean"] <= 1.0
        assert 0.0 <= res["bootstrap_degenerate_fraction"] <= 1.0
        assert np.isfinite(res["bootstrap_ari_mean"])
