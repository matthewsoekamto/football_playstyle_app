# Football Playstyle App — Option C Implementation Plan

> **For the next AI:** This document captures the full context of an ongoing refactoring session. Read it entirely before touching any code. The bugs, decisions, and tradeoffs below were established through real data analysis on the actual CSV. Do not re-derive — trust what's written here and implement accordingly.

---

## Project Overview

A Streamlit dashboard that clusters football players from the Big 5 European leagues (2025/26 season) into named playstyle archetypes using K-Means clustering on per-90 stats. The dataset is `players_data_light-2025_2026.csv` (2183 rows after filtering for ≥270 minutes played).

**File structure:**

| File | Purpose |
|------|---------|
| `app.py` | Streamlit UI — search, filters, scatter plot, H2H comparison |
| `data_loader.py` | CSV loading, cleaning, per-90 rate derivation |
| `model_engine.py` | K-Means clustering and archetype labeling |
| `features.py` | Filters, percentiles, position stat sets |
| `charts.py` | Plotly chart builders |

---

## Bugs Already Fixed (Do Not Redo)

These were fixed in a prior session. The fixed files are `app.py` and `data_loader.py`.

### Fix 1 — `data_loader.py`: Hardcoded `min` column
**Was:** `min_col = [col for col in df.columns if "min" in col][0]` — fragile substring match.  
**Now:** `df = df[df["min"] >= 270].copy()` — hardcoded. Row count confirmed identical (2183).

### Fix 2 — `app.py`: Duplicate player names in H2H selector
50 players appear twice (mid-season transfers, e.g. Simon Adingra: Sunderland + Monaco).  
**Was:** H2H used raw `player` name for selection and lookup — `.iloc[0]` silently picked the wrong row.  
**Now:** `add_unique_player_labels()` function builds a `player_label` column. Only duplicated names get a `"Name (Squad)"` suffix. H2H selects and looks up by `player_label`. Confirmed: `player_label` is unique across all 2183 rows.

---

## The Core Problem — Why Option C Is Needed

The current clustering (5 outfield archetypes, K=5) produces **systematically wrong labels**. This is not a borderline edge case — it's a structural failure confirmed by data.

### Root cause 1: Greedy "no repeats" archetype assignment

`_assign_labels_from_archetypes()` in `model_engine.py` assigns cluster→archetype labels greedily: each cluster gets its closest archetype by Euclidean distance in standardized space, but **no archetype name can be reused**. This forces the 4th and 5th clusters to take their 2nd or 3rd-best matches.

**Measured result across all 5 clusters:**

| Cluster | Assigned label | Actual closest archetype | Min distance |
|---------|---------------|--------------------------|-------------|
| 0 | Utility / Depth Players | Utility / Depth Players | 2.29 ✅ |
| 1 | Creative Playmakers | Creative Playmakers | 2.51 ✅ |
| 2 | Defensive Rotators | **Utility / Depth Players** | 0.76 ❌ wrong label |
| 3 | Elite Finishers | **Creative Playmakers** | 2.79 ❌ wrong label |
| 4 | Ball-Winning Anchors | **Elite Finishers** | 2.09 ❌ wrong label |

3 of 5 clusters have wrong labels due to the greedy no-repeats constraint.

### Root cause 2: Too few archetypes (K=5) — no winger archetype exists

Antoine Semenyo (Bournemouth winger, 2.45 shots/90, 1.4 crosses/90) is labeled "Ball-Winning Anchors." His cluster's centroid (`gls_p90` 0.37, `sh_p90` 2.55, `tklw_p90` 0.50) contains Viktor Gyökeres, Vinicius Júnior, and Hugo Ekitike. The "Ball-Winning Anchors" archetype definition requires `tklw_p90` 3.5 and `int_p90` 3.0 — the actual distance is **8.24 standard deviations**. This is a near-inversion, not a borderline case.

The current 5 archetypes are: Elite Finishers, Creative Playmakers, Ball-Winning Anchors, Defensive Rotators, Utility / Depth Players. **There is no winger/wide attacker archetype.**

### Root cause 3: `primary_position` mislabeling for wide players

`primary_position` uses `pos.split(",")[0]`, which takes whatever FBref lists first. Semenyo is listed as `"MF"` in one club stint and `"MF,FW"` in another — so he's bucketed as a midfielder, not a forward/winger, affecting which archetype pool he's compared against.

---

## Data Limitation — Dribbling Signal (Important Note)

**We attempted to add take-ons, progressive carries, and dribbling stats** from FBref's possession table. This failed for two reasons:
1. The Kaggle "full" dataset (`players_data-2025_2026.csv`) does not actually contain possession columns despite its description suggesting otherwise.
2. FBref's website blocks automated scraping (403), and their Ctrl+S HTML export doesn't capture JavaScript-rendered table data.

**Consequence:** The current feature set (`gls_p90`, `ast_p90`, `sh_p90`, `crs_p90`, `tklw_p90`, `int_p90`) **cannot distinguish a "cuts inside and shoots" winger from a penalty-box striker** — both profiles show high shots and low crosses. This is a data ceiling, not a modeling failure.

**Future fix (when possession data is available):** Add `take_ons_p90`, `take_on_succ%`, and `prg_carries_p90` to `OUTFIELD_FEATURES` in `model_engine.py` and `OUTFIELD_RATE_STATS` in `data_loader.py`. Re-run the elbow/centroid analysis before naming archetypes.

**For now:** Acknowledge this in the UI (a small info note in the Playstyle Explorer) and proceed with 8 archetypes derived from what the data can distinguish.

---

## Option C — What To Implement

Option C = more archetypes (Option A) + remove greedy constraint + distance fallback (Option B).

### Part 1: Remove the greedy "no repeats" constraint — `model_engine.py`

Replace `_assign_labels_from_archetypes()` with a version that assigns each cluster its **true nearest archetype by Euclidean distance**, regardless of whether another cluster already has that label. Two clusters can share a label if that's genuinely their best fit — that's more honest than a forced wrong label.

Additionally, add a **distance threshold fallback**: if a cluster's best archetype match still exceeds a threshold (suggested: `3.5` standardized units), label it `"Mixed Profile"` instead of forcing a bad name. This prevents future mislabeling if data shifts.

```python
# Replace the current label assignment loop with this logic:
def _assign_labels_from_archetypes(centroids, archetypes, feature_cols, threshold=3.5):
    archetype_names, archetype_matrix = _archetype_matrix(archetypes, feature_cols)
    scaler = StandardScaler()
    scaled_centroids = scaler.fit_transform(centroids[feature_cols].values)
    scaled_archetypes = scaler.transform(archetype_matrix)

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
```

### Part 2: Increase to K=8 outfield clusters — `model_engine.py`

Change `KMeans(n_clusters=5, ...)` to `KMeans(n_clusters=8, ...)` for outfield players.

Analysis of K=8 centroids on the actual data revealed these natural groupings:

| Cluster profile | Proposed archetype name |
|----------------|------------------------|
| Very low attack, moderate defense (CBs, DMs) | Defensive Anchors |
| High shots, low crosses, low defense (poachers) | Elite Finishers |
| High crosses, moderate everything, low goals (deep creators) | Deep Creators |
| Near-zero everything (rotation players) | Utility / Depth Players |
| Very high crosses, low shots/goals (wide creators, wingbacks) | Wide Creators |
| Moderate shots, very low crosses/defense (direct attackers) | Direct Attackers |
| High shots + moderate crosses + moderate assists (hybrid wide) | Advanced Attackers |
| Low attack, high tackles + interceptions (ball-winners) | Ball-Winning Anchors |

**Note on "Advanced Attackers":** This is where Semenyo lands with K=8 (alongside Luis Díaz, Bowen, Antony). It's still not a clean "winger" label because the stat set lacks dribbling signal, but it's far more accurate than "Ball-Winning Anchors."

**GK archetypes stay at K=2:** Shot-Stoppers and Sweeper-Keepers. No change needed.

### Part 3: Update `OUTFIELD_ARCHETYPES` dict — `model_engine.py`

Replace the current 5-archetype dict with 8 entries matching the names above. Use these approximate centroid targets derived from the K=8 analysis (standardized space — these are real-world stat targets for the archetype, not scaled values):

```python
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
```

### Part 4: Add a data limitation note in the UI — `app.py`

Inside `render_playstyle_explorer()`, below the subheader, add:

```python
st.info(
    "ℹ️ Playstyles are clustered from goals, assists, shots, crosses, "
    "tackles, and interceptions per 90. Dribbling and progressive carrying "
    "data is not available in this dataset, which limits separation between "
    "wide attackers who cut inside and shoot vs. those who cross or carry. "
    "This will be improved when possession data is sourced."
)
```

### Part 5: Validate after implementing

After making all changes, run this to confirm Semenyo's new label and check no cluster gets "Mixed Profile" under K=8 (they shouldn't — all K=8 centroids were within ~2.8 units of their best archetype in testing):

```python
# Run standalone: python model_engine.py
# Check output includes:
# 1. Semenyo labeled "Advanced Attackers" or "Elite Finishers" (not Ball-Winning Anchors)
# 2. All 8 clusters have named labels (not "Mixed Profile")
# 3. Distribution looks reasonable — no cluster with <50 or >600 players
```

---

## What Not To Change

- `data_loader.py` — the `min` hardcode fix is already in. No other changes needed.
- `app.py` — the `add_unique_player_labels()` fix is already in. Only add the info note in Part 4 above.
- `charts.py` — no changes needed.
- `features.py` — no changes needed unless new stat columns are added in future.
- GK clustering — K=2 with Shot-Stoppers / Sweeper-Keepers is working correctly.

---

## Open Issues (Out of Scope for This Session)

- **Cross-position H2H fallback:** When comparing a GK vs outfield player, the app silently substitutes MF stats for the GK. The warning message exists but doesn't explain the stat substitution. Low priority.
- **Unpinned `requirements.txt`:** `>=` version constraints will cause instability on redeploy. Pin exact versions before pushing to Streamlit Cloud.
- **Possession data:** See the dribbling limitation section above. The path forward is running a Selenium/Playwright script locally to render FBref's JavaScript table, save the data once as a static CSV, and treat it as a permanent supplement to the Kaggle dataset.
