# DECISIONS
### Architectural Decision Records (ADR-style)

Authority: subordinate to `PROJECT_CONSTITUTION.md`. Each record below is reconstructed from the current state of the code (this is a retroactive ADR log, since none existed before this doc set) or proposed for a known open question. New decisions must be appended, never edited in place — if a decision is reversed, add a new record that supersedes it.

---

## ADR-001: Two independent K-Means models (outfield vs. goalkeeper)

**Context:** Goalkeepers and outfield players have almost no overlapping meaningful stats (a goalkeeper's `save%` has no outfield analog; an outfield player's `crs_p90` has no GK analog).

**Options considered:**
- (A) One KMeans model over a shared, padded feature set (zero-fill the irrelevant stats for each group).
- (B) Two independent KMeans models, one per group, each on its own feature set.

**Chosen:** (B), implemented in `model_engine.group_players`.

**Why:** Padding irrelevant stats with zeros (Option A) would cause the model to partly cluster on "is this player a goalkeeper" rather than genuine playstyle variation, and would waste dimensions. Two independent models keep each clustering problem clean.

**Tradeoffs:** Cluster IDs are not comparable across the two models (a `cluster_id` of `0` means something different in each), which is why `playstyle_cluster` (the human-readable label) — not `cluster_id` — is the field used downstream everywhere in `app.py`.

**Future consideration:** If a third group emerges (e.g. wing-backs treated distinctly), this pattern extends naturally — add a third `_available_features` / `KMeans` / archetype-matching block.

---

## ADR-002: Archetype labeling via distance-matching, not supervised labels

**Context:** Raw KMeans output is `cluster_id` (an arbitrary integer). The product requires human-readable playstyle names.

**Options considered:**
- (A) Manually relabel `cluster_id → name` after every run by eye.
- (B) Hand-author target feature vectors per archetype (`OUTFIELD_ARCHETYPES`, `GK_ARCHETYPES`) and assign each cluster centroid to its nearest archetype by distance.
- (C) Train a small supervised classifier on manually labeled examples.

**Chosen:** (B), implemented in `model_engine._assign_labels_from_archetypes`.

**Why:** (A) doesn't scale and isn't reproducible across dataset refreshes. (C) requires labeled training data that doesn't exist. (B) is deterministic, requires no labeled data, and lets a domain expert (not a data scientist) tune the archetype definitions directly as readable dictionaries.

**Tradeoffs / known issue:** The matching `StandardScaler` in `_assign_labels_from_archetypes` is fit on only the cluster centroids themselves (**n=5 for outfield, n=2 for goalkeepers**) rather than on the full player-level feature distribution. A `StandardScaler` fit on 2–5 points is a statistically thin basis for a mean/variance estimate, and it means the archetype-matching scale is *relative to this run's centroids*, not to the underlying data. In most runs this is harmless because centroids are reasonably spread out, but it is a fragility worth fixing — see `TASK_BACKLOG.md` (ML-01) and `ML_GUIDELINES.md §Archetype Matching`.

**Also note:** matching is **greedy nearest-first with de-duplication** (`used_names`), not a globally optimal assignment. For 5 clusters vs. 5 archetypes this can, in rare cases, produce a worse total assignment than an optimal (Hungarian/`scipy.optimize.linear_sum_assignment`) solution would. Flagged, not yet fixed.

---

## ADR-003: Per-90 normalization instead of raw totals for clustering

**Context:** Players have wildly different minutes played (270 minutes minimum vs. a player who started every match).

**Options considered:**
- (A) Cluster on raw season totals (`gls`, `ast`, `sh`, ...).
- (B) Cluster on per-90 rate stats (`gls_p90`, `ast_p90`, ...), computed in `data_loader._add_per90_rates`.

**Chosen:** (B).

**Why:** Raw totals would cluster primarily on playing time, not playstyle — a prolific starter and a rarely-used player with an identical style would end up in different clusters purely due to minutes. Per-90 rates control for this.

**Tradeoffs:** Per-90 rates are noisier for players near the 270-minute floor (three matches is a small sample to estimate a rate stat). The `Min >= 270` filter (see ADR-004) is the current mitigation; it is a floor, not a fix.

---

## ADR-004: Minimum-minutes filter set at 270

**Context:** Very low-minutes players produce unstable per-90 rates (e.g. one goal in 30 minutes is a `gls_p90` of 3.0, which is not a real signal).

**Chosen:** `Min >= 270` (three full 90-minute matches), implemented in `data_loader.load_and_clean_data`, reducing 2,839 raw rows to 2,183.

**Why:** A round, defensible "three matches" floor. Not derived from a formal variance/confidence analysis.

**Tradeoffs:** Still permits meaningfully noisy rates for players at exactly 270–450 minutes. No lower bound is currently enforced beyond this.

**Future consideration:** If per-90 noise proves to materially affect cluster assignment for borderline players, consider a higher floor (e.g. 900 minutes / 10 matches) or a shrinkage/regularized rate estimator. This is a product decision, not a pure engineering one — log any change here.

---

## ADR-005: `fetch_possession_stats.py` kept as a standalone, disconnected script

**Context:** The script scrapes FBref's possession table but its output is not consumed anywhere in the app.

**Options considered:**
- (A) Delete it — it's dead code.
- (B) Wire it directly into `data_loader.py` so the app scrapes live data.
- (C) Keep it as a standalone, manually-run utility, documented as the seed of a future feature.

**Chosen:** (C) — no code change made by this documentation effort (per the instruction to document, not modify), but the recommendation is explicit: keep it, do not silently delete it, and do not wire it into the live app without addressing its dependencies and FBref's scraping etiquette.

**Why:** (A) throws away real, working scraping logic that directly serves a roadmap item (possession-based features — see `PROJECT_SPEC.md §5`). (B) would introduce a live outbound network call and a third-party HTML-parsing dependency into a Streamlit app that currently has zero network calls at request time — a meaningful architectural and reliability change that deserves its own decision record when it's actually proposed, not as a side effect of a scrape script existing.

**Tradeoffs:** Until adopted, this file provides no value to the running app and carries a small maintenance cost (its `bs4`/`requests`/`lxml` dependencies are not pinned anywhere, and FBref's page structure can change silently).

**Action item:** See `TASK_BACKLOG.md` (DATA-01) for the concrete integration proposal.

---

## ADR-006: No `st.session_state`; rely on Streamlit's default rerun model

**Context:** The app has no multi-step flows or state that must survive independent of widget values.

**Chosen:** No explicit session state; every interaction is a full top-to-bottom script rerun reading current widget values.

**Why:** Simplicity. The current feature set (filter → view) fits Streamlit's default model perfectly.

**Tradeoffs:** Any future feature requiring state that isn't a direct function of current widget values (e.g. "pin these two players for comparison across filter changes," undo, multi-page wizards) will require introducing `st.session_state` deliberately — this should be a conscious addition, not something an AI agent adds ad hoc to solve a local problem. See `AI_DEVELOPER_RULEBOOK.md`.

---

## ADR-007: `fillna(0)` before scaling/clustering and before percentile ranking

**Context:** Many stat columns are legitimately missing for a large share of rows — e.g. goalkeeper-only columns (`Saves`, `CS%`, `GA90`) are null for the ~2,645 non-GK rows out of 2,839 total.

**Chosen:** `fillna(0)` is applied before `StandardScaler` in `model_engine.group_players`, and before `rank(pct=True)` in `features.add_position_percentiles`.

**Why:** Zero is a reasonable default for count-like rate stats (an outfield player genuinely has zero saves), and it avoids `NaN` propagation crashing `StandardScaler`/`KMeans`.

**Tradeoffs:** For percentiles specifically, this means `features.add_position_percentiles` computes a `*_percentile` column for *every* stat in `get_all_compare_stats()` for *every* position group, including stats that are structurally meaningless for that position (e.g. a `saves_percentile` column exists for forwards, computed against other forwards who also all have `saves = 0`). This is currently harmless because the UI only ever displays position-appropriate stats (`get_compare_stats_for_position`), but it is dead/misleading data sitting in the DataFrame. See `TASK_BACKLOG.md` (ML-02).

---

## ADR-008: Duplicate player names resolved via squad-suffix labels, not IDs

**Context:** 152 rows in the raw dataset share a `Player` name with at least one other row (mid-season transfers create two rows for one person, and some names are simply common).

**Options considered:**
- (A) Use FBref's `Rk` column (row rank) as a synthetic unique ID.
- (B) Build a display label that appends the squad name only when a name collides (`app.add_unique_player_labels`).

**Chosen:** (B).

**Why:** (A) would work but produces an opaque, non-human-readable selector value in `st.selectbox`. (B) keeps the common case (a unique name) clean and only adds disambiguation where genuinely needed.

**Tradeoffs:** If the *same* player at the *same* squad ever appears twice (not currently possible given the dataset's shape, but not structurally prevented), (B) would not disambiguate. Not a current risk; noted for completeness.
