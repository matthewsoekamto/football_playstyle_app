# DATA_SOURCE_MAPPING.md

**Project:** Football Playstyle App — Version 2 (WC 2022 Rebuild)  
**Architecture:** Hybrid FBref (canonical season stats) + StatsBomb Open Data (event-derived spatial/pressure metrics)  
**Rule:** Every feature has ONE canonical owner. Never compute the same metric from both sources.

---

## Feature Inventory (from PLAYSTYLE_SPEC.md)

62 unique features referenced across 20 archetypes.

---

## Mapping Table

| # | Feature | Canonical Source | Why This Source | Merge Required? | Engineering Required? | Priority |
|---|---------|------------------|-----------------|-----------------|----------------------|----------|
| 1 | saves_p90 | **FBref** | Advanced GK table has `Saves` directly | No | No (divide by 90s) | P0 |
| 2 | save_pct | **FBref** | Advanced GK table has `Save%` directly | No | No | P0 |
| 3 | goals_prevented_p90 (psxG − GA) | **StatsBomb** | FBref has `PSxG` but not per-GK shots faced; SB has `statsbomb_xg2` per shot + GK attribution | Yes (GK minutes) | Yes (PSxG sum per GK) | P1 |
| 4 | claims_p90 (high crosses caught) | **StatsBomb** | FBref GK advanced has `Crosses Claimed` but not separated by type; SB `goalkeeper.type=Collected` is explicit | No | Yes (filter Collected) | P1 |
| 5 | reflex_saves_p90 (close-range) | **StatsBomb** | FBref does not have close-range save split; SB: shot location + GK save | No | Yes (distance < 5.5y) | P2 |
| 6 | passes_p90 | **FBref** | Passing table has `Cmp` + `Att`; reliable per-90 | No | No | P0 |
| 7 | long_passes_p90 | **FBref** | Pass Types table has `Long` `Cmp`/`Att` | No | No | P0 |
| 8 | prog_passes_p90 | **FBref** | Passing table has `PrgP` (Opta definition) | No | No | P0 |
| 9 | def_actions_outside_box_p90 | **StatsBomb** | FBref has no GK defensive action location; SB: all GK event locations | No | Yes (location filter) | P1 |
| 10 | avg_def_position_y | **StatsBomb** | FBref has no positional data; SB: mean y of GK events | No | Yes (mean y-coord) | P1 |
| 11 | launch_passes_p90 (>40m) | **StatsBomb** | FBref has `Long` passes but no length threshold; SB `pass.length` | No | Yes (filter length > 40) | P1 |
| 12 | sweeper_clearances_p90 | **StatsBomb** | FBref has no GK sweeper action type; SB `goalkeeper.type=Keeper Sweeper` | No | Yes (filter type) | P1 |
| 13 | penalty_save_pct | **FBref** | Advanced GK table has `PKsv%` | No | No | P0 |
| 14 | clearances_p90 | **FBref** | Defensive Actions table has `Clr` | No | No | P0 |
| 15 | blocks_p90 | **FBref** | Defensive Actions table has `Blocks` | No | No | P0 |
| 16 | aerial_duels_won_p90 | **FBref** | Defensive Actions has `Aerial Won` (Opta) | No | No | P0 |
| 17 | aerial_duel_pct | **FBref** | `Aerial Won` / `Aerial Lost` available | No | Derived (won/(won+lost)) | P0 |
| 18 | interceptions_p90 | **FBref** | Defensive Actions has `Int` | No | No | P0 |
| 19 | tackles_won_p90 | **FBref** | Defensive Actions has `TklW` | No | No | P0 |
| 20 | headed_clearances_p90 | **StatsBomb** | FBref `Clr` not split by body part; SB `clearance.head=true` | No | Yes (filter head) | P1 |
| 21 | pass_completion_pct | **FBref** | Passing table `Cmp%` | No | No | P0 |
| 22 | carries_p90 | **FBref** | Possession table has `Carries` | No | No | P0 |
| 23 | prog_carries_p90 | **FBref** | Possession table has `PrgC` | No | No | P0 |
| 24 | passes_into_final_third_p90 | **FBref** | Passing table has `1/3` (completed into final third) | No | No | P0 |
| 25 | switches_p90 | **FBref** | Pass Types table has `Sw` (switches) | No | No | P0 |
| 26 | pressures_p90 | **StatsBomb** | FBref: "don't yet have a source" (SR blog 2023); SB `Pressure` event type | No | Yes (count Pressure events) | P0 |
| 27 | pressures_final_third_p90 | **StatsBomb** | FBref lacks pressures entirely; SB location filter x≥80 | No | Yes (location filter) | P1 |
| 28 | pressures_mid_third_p90 | **StatsBomb** | Same as above; SB location filter 40<x<80 | No | Yes | P1 |
| 29 | fouls_p90 | **FBref** | Standard/Misc table has `Fls` | No | No | P0 |
| 30 | duels_won_p90 | **FBref** | Defensive Actions `TklW` + `Aerial Won` (approximation) | No | Derived | P1 |
| 31 | recoveries_p90 | **StatsBomb** | FBref has no `Recoveries`; SB `Ball Recovery` event | No | Yes (count recoveries) | P1 |
| 32 | crosses_p90 | **FBref** | Pass Types has `Crs` (completed crosses) | No | No | P0 |
| 33 | cross_accuracy_pct | **StatsBomb** | FBref `Crs` is completed only; SB `pass.cross=true` + outcome for accuracy | No | Yes (cross + outcome) | P1 |
| 34 | final_third_entries_p90 | **StatsBomb** | FBref has `1/3` (passes) + `CPA` (carries into 1/3) but not unified; SB: any event end_location in final third | No | Yes (carry+pass end_location) | P1 |
| 35 | touches_att_pen_p90 | **StatsBomb** | FBref has `Att Pen` touches; SB: any event location in pen area — cross-check consistency | Yes (minutes) | Yes (location filter) | P1 |
| 36 | key_passes_p90 | **FBref** | Passing table has `KP` | No | No | P0 |
| 37 | xA_p90 | **FBref** | Passing table has `xAG` (Opta xA) | No | No | P0 |
| 38 | dribbles_p90 | **FBref** | Possession has `Take-ons Att` (Opta "Take-ons" ≈ dribbles) | No | No | P0 |
| 39 | carries_into_box_p90 | **StatsBomb** | FBref has `CPA` (carries into pen area) but not box; SB `carry.end_location` in box | No | Yes (location filter) | P1 |
| 40 | dribble_success_pct | **FBref** | Possession has `Take-ons Succ` / `Att` | No | Derived | P0 |
| 41 | shot_creating_actions_p90 | **FBref** | GCA table has `SCA` | No | No | P0 |
| 42 | touches_wide_p90 | **StatsBomb** | FBref has `Def 3rd`/`Mid 3rd`/`Att 3rd` zones but not wide channels; SB y≤16 or y≥64 | No | Yes (location filter) | P1 |
| 43 | touches_halfspace_p90 | **StatsBomb** | FBref has no half-space zones; SB y 16-25 / 55-64 | No | Yes | P1 |
| 44 | through_balls_p90 | **FBref** | Pass Types has `TB` (through balls) | No | No | P0 |
| 45 | passes_into_box_p90 | **FBref** | Passing has `PPA` (passes into pen area) | No | No | P0 |
| 46 | gls_p90 | **FBref** | Standard stats `Gls` | No | No | P0 |
| 47 | shots_p90 | **FBref** | Shooting table `Sh` | No | No | P0 |
| 48 | xG_p90 | **FBref** | Shooting table `xG` | No | No | P0 |
| 49 | shots_on_target_p90 | **FBref** | Shooting table `SoT` | No | No | P0 |
| 50 | npxG_per_shot | **FBref** | `npxG` / `Sh` (derive; exclude pens) | No | Derived | P1 |
| 51 | conversion_pct | **FBref** | `Gls` / `Sh` | No | Derived | P0 |
| 52 | shots_on_target_pct | **FBref** | `SoT` / `Sh` | No | Derived | P0 |
| 53 | box_entries_p90 | **StatsBomb** | FBref has `CPA` + `PPA` but not combined "box entries"; SB: carry end_location in box | No | Yes | P1 |
| 54 | final_third_touches_p90 | **FBref** | Possession has `Att 3rd` touches | No | No | P0 |
| 55 | one_touch_finishes_p90 | **StatsBomb** | FBref has no first-time shot flag; SB `shot.first_time=true` | No | Yes | P1 |
| 56 | headers_p90 | **StatsBomb** | FBref shooting has `Head` but not headers total; SB `shot.body_part=Head` + `clearance.head` | No | Yes (define scope: shots only) | P2 |
| 57 | headed_goals_p90 | **FBref** | Shooting table has `Gls` by body part (Head) | No | No | P0 |
| 58 | fouls_won_p90 | **FBref** | Standard/Misc has `Fld` (fouls drawn) | No | No | P0 |
| 59 | hold_up_passes_p90 | **StatsBomb (proxy)** | Neither source has true "layoffs"; SB `passes_received` (Ball Receipt) as proxy; FBref has no equivalent | No | Yes (proxy) | P2 |
| 60 | passes_received_p90 | **StatsBomb** | FBref has no receptions metric; SB `Ball Receipt` event | No | Yes | P1 |
| 61 | line_breaking_passes_p90 | **StatsBomb (proxy)** | FBref no; SB needs 360 data (not open); proxy: `prog_passes_p90` + `passes_into_final_third_p90` from FBref | No | Proxy only | P2 |
| 62 | touches_6yard_box_p90 | **StatsBomb** | FBref has `Att Pen` but not 6-yard; SB location x≥114, 27<y<53 | No | Yes | P1 |
| 63 | touches_opp_box_p90 | **FBref** | Possession has `Att Pen` touches | No | No | P0 |
| 64 | ast_p90 | **FBref** | Standard stats `Ast` | No | No | P0 |

---

## Source Summary

| Source | Feature Count | Notes |
|--------|---------------|-------|
| **FBref** | 38 | All standard/advanced season aggregates |
| **StatsBomb** | 26 | Pressures, GK claim types, spatial zones, first-time finishes, receptions, headers, recoveries |

---

## Merge Strategy & Known Issues

### 1. Player Identity Matching
- **FBref** uses proprietary IDs (e.g., `fa031b34` for Richarlison)
- **StatsBomb** uses numeric IDs (e.g., `3515`)
- **Solution:** Build a mapping table via name + team + birthdate fuzzy match. Use `statsbombpy` `players` endpoint or manual CSV for WC 2022 (64 matches, ~736 players). One-time effort.

### 2. Minute Denominator Inconsistency
- FBref `Min` = minutes played per Opta (may differ from actual clock time)
- StatsBomb minutes = derived from lineup + event timestamps
- **Impact:** Per-90 rates will differ slightly between sources
- **Solution:** Use **FBref `90s`** as the canonical denominator for ALL features. Compute StatsBomb features as `count / fbref_90s * 90`. Requires merging on player first, then normalizing.

### 3. Feature Duplication Risk
| Feature | FBref Column | StatsBomb Equivalent | Decision |
|---------|--------------|---------------------|----------|
| prog_passes | `PrgP` | `pass.length + location` | FBref wins |
| prog_carries | `PrgC` | `carry.end_location - start` | FBref wins |
| crosses | `Crs` | `pass.cross=true` | FBref wins |
| touches_att_pen | `Att Pen` | event location in box | **FBref wins** (more reliable denominator) |
| aerial_duels_won | `Aerial Won` | `duel.type=Aerial` | FBref wins |
| xA | `xAG` | N/A | FBref wins |

**Rule:** Where both exist, FBref is canonical. StatsBomb only fills gaps.

### 4. Missing FBref Features (No Direct Equivalent)
These **must** come from StatsBomb:
- All pressure features (#26-28)
- GK claim types (#4, #12)
- Spatial zones: half-space, wide, 6-yard (#42, #43, #62)
- First-time finishes (#55)
- Receptions (#60)
- Headed clearances (#20) — FBref `Clr` not split by body part
- Recoveries (#31)
- Sweeper actions (#12)

### 5. Proxy Features (FBref has no equivalent, SB open data insufficient)
| Feature | Proxy Approach |
|---------|----------------|
| `line_breaking_passes_p90` | `prog_passes_p90` + `passes_into_final_third_p90` (both FBref) — rename to `final_third_prog_passes_p90` |
| `hold_up_passes_p90` | `passes_received_p90` (StatsBomb Ball Receipt) — document as "build-up involvement proxy" |

---

## Implementation Priority

| Priority | Features | Rationale |
|----------|----------|-----------|
| **P0** | All FBref features (38) | CSV download → parse → per-90 normalize → merge. No computation. |
| **P1** | StatsBomb core gaps: pressures (3), GK claims (3), recoveries, receptions, spatial zones (5), first-time finishes, headed clearances, box entries, passes received | Enable archetype differentiation (Stopper/Destroyer, Sweeper Keeper, Target Man, Poacher) |
| **P2** | Reflex saves, headers scope clarification, line-breaking proxy, hold-up proxy | Polish / documentation only |

---

## Pipeline Sketch

```
# 1. FBref ingestion
fbref_standard  = pd.read_csv('fbref_standard.csv')      # Gls, Ast, Sh, SoT, xG, npxG, Min, 90s
fbref_shooting  = pd.read_csv('fbref_shooting.csv')      # conversion_pct, npxG_per_shot
fbref_passing   = pd.read_csv('fbref_passing.csv')       # PrgP, KP, xAG, 1/3, PPA, CrsPA, TB, Sw, Crs
fbref_pass_types= pd.read_csv('fbref_pass_types.csv')    # Long, TB, Sw, Crs
fbref_possession= pd.read_csv('fbref_possession.csv')    # Carries, PrgC, Touches zones, Take-ons
fbref_defense   = pd.read_csv('fbref_defense.csv')       # TklW, Int, Blocks, Clr, Aerial Won, Aerial Lost
fbref_gca       = pd.read_csv('fbref_gca.csv')           # SCA, GCA
fbref_gk        = pd.read_csv('fbref_gk.csv')            # Saves, Save%, PKsv%, Crosses Claimed
fbref_gk_adv    = pd.read_csv('fbref_gk_adv.csv')        # Advanced GK

# 2. Merge FBref on player_id (fbref), compute all 38 FBref features per-90 using fbref_90s
fbref_features = merge_all(fbref_*).assign(
    prog_passes_p90 = lambda d: d.PrgP / d['90s'],
    ... # 37 more
)

# 3. StatsBomb ingestion (WC 2022: comp 43, season 106)
#    - Download events for all 64 matches
#    - Parse per-player event counts by type + location filters
#    - Compute 26 SB features per player
#    - Map SB player_id → FBref player_id via mapping table
#    - Normalize using FBref 90s: sb_count / fbref_90s * 90

# 4. Final merge
final_matrix = fbref_features.merge(sb_features, on='fbref_player_id', how='left')
#    → fillna(0) for players with no SB data (should be none for WC2022)
#    → StandardScaler per position group
#    → KMeans
```

---

## Sign-off

This mapping respects the hybrid architecture constraint. Every feature has one owner. FBref carries the heavy statistical lifting; StatsBomb plugs the structural gaps (pressures, GK micro-actions, spatial granularity). Merge risk is contained to player ID mapping and minute denominator alignment — both solved by canonicalizing on FBref `90s`.