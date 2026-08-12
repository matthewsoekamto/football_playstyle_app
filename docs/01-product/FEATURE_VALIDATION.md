# Feature Validation — StatsBomb Open Data (WC 2022)

**Source:** StatsBomb Open Data v4, competition_id=43 (FIFA World Cup), season_id=106 (2022)
**Pitch model:** 120×80 coords. Origin bottom-left corner of defensive half.
**Normalization:** All count stats → per 90 minutes (`event_count / minutes_played * 90`). Minutes from lineup/event timestamps.
**Baseline filter:** Min ≥ 270 match minutes (following existing app convention).

---

## Validation Table

| # | Feature | Status | Required Events | JSON Fields | Formula | Confidence | Replacement if Unavail. |
|---|---------|--------|-----------------|-------------|---------|-----------|------------------------|
| 1 | saves_p90 | **Direct** | `Shot` (faced), `Goal Keeper` | Event type `"Goal Keeper"` w/ `goalkeeper.type.name == "Shot Saved"` | `COUNT(goalkeeper WHERE type=Shot Saved) / minutes * 90` | **High** | — |
| 2 | save_pct | **Derived** | `Shot`, `Goal Keeper` | `shot.outcome.name IN ("Goal","Saved","Saved To Post")` vs GK saves | `saves / (saves + goals_conceded)` where GK faced the shot | **High** | — |
| 3 | goals_prevented_p90 (psxG−GA) | **Derived** (proxy) | `Shot`, `Goal Keeper` | `shot.statsbomb_xg`, `goalkeeper.type.name == "Goal Conceded"` | Locked P3: `SUM(statsbomb_xg of linked shots faced) - goals_conceded` per GK. xg2 (true PSxG) unused — the xg proxy IS the implementation | **Medium** | — |
| 4 | claims_p90 | **Direct** | `Goal Keeper` | `goalkeeper.type.name == "Collected"` | `COUNT(type=Collected) / minutes * 90` | **High** | — |
| 5 | reflex_saves_p90 | **Derived** | `Goal Keeper`, `Shot` | `goalkeeper.type=Shot Saved` AND `shot.location` distance < ~5.5y | `COUNT(close-range saves) / minutes * 90`; define distance threshold from shot origin to goal | **Medium** | All saves if distance calc too noisy |
| 6 | passes_p90 | **Direct** | `Pass` | Event type `"Pass"` | `COUNT(pass) / minutes * 90` | **High** | — |
| 7 | long_passes_p90 | **Derived** | `Pass` | `pass.height.name == "High Pass"` OR `pass.length > 25y` | `COUNT(pass WHERE height=High OR length>25) / minutes * 90` | **High** | — |
| 8 | prog_passes_p90 | **Derived** | `Pass` | `location` + `pass.end_location`; pitch 120×80 | `COUNT(pass WHERE end_x - start_x > threshold) / minutes * 90`; threshold ~10y forward movement | **High** | — |
| 9 | def_actions_outside_box_p90 | **Derived** | All GK events | `location` of GK events | `COUNT(GK event WHERE location NOT IN box area) / minutes * 90`; box = x≥102, 18<y<62 | **High** | — |
| 10 | avg_def_position_y | **Derived** | All GK events | `location` | `MEAN(y-coord of all GK events)` | **High** | — |
| 11 | launch_passes_p90 (>40m) | **Derived** | `Pass` (by GK) | `pass.length` | `COUNT(pass by GK WHERE pass.length > 40) / minutes * 90` | **High** | — |
| 12 | sweeper_clearances_p90 | **Direct** | `Goal Keeper` | `goalkeeper.type.name == "Keeper Sweeper"` | `COUNT(type=Keeper Sweeper) / minutes * 90` | **High** | — |
| 13 | penalty_save_pct | **Derived** | `Goal Keeper` | `goalkeeper.type.name ∈ {"Penalty Saved", "Penalty Conceded"}` + `Shot Faced` linked to a `shot.type.name == "Penalty"` | `penalty_saved / penalty_faced` (P6; penalties faced = saved + conceded + missed) | **High** | — |
| 14 | clearances_p90 | **Direct** | `Clearance` | Event type `"Clearance"` | `COUNT(clearance) / minutes * 90` | **High** | — |
| 15 | blocks_p90 | **Direct** | `Block` | Event type `"Block"` | `COUNT(block) / minutes * 90` | **High** | — |
| 16 | aerial_duels_won_p90 | **Derived** | `Pass`, `Clearance` | `pass.aerial_won`, `clearance.aerial_won` | `COUNT(aerial_won=True on pass/clearance) / minutes * 90`. WC2022 open data has NO `Duel` outcomes, so wins come only from pass+clearance (verified: 1,483 + 536) | **High** | — |
| 17 | aerial_duel_pct | **Derived (approx.)** | `Pass`, `Clearance`, `Duel` | `aerial_won` (pass/clearance); `Duel` with `duel.type.name == "Aerial Lost"` | `aerial_won / (aerial_won + COUNT(Duel=Aerial Lost))`. Open-data duels carry no outcome, so the denominator is approximate — documented | **Medium** | — |
| 18 | interceptions_p90 | **Direct** | `Interception` | Event type `"Interception"` | `COUNT(interception) / minutes * 90` | **High** | — |
| 19 | tackles_won_p90 | **Derived** | `Duel` | `duel.type.name == "Tackle"`, `duel.outcome.name IN ("Won","Success")` | `COUNT(tackle WHERE won) / minutes * 90` | **High** | — |
| 20 | headed_clearances_p90 | **Direct** | `Clearance` | `clearance.body_part.name ≈ "Head"` OR `clearance.head` | `COUNT(clearance WHERE head) / minutes * 90` | **High** | — |
| 21 | pass_completion_pct | **Direct** | `Pass` | `pass.outcome.name` | `1 - (COUNT(outcome=Incomplete) / COUNT(pass))` | **High** | — |
| 22 | carries_p90 | **Direct** | `Carry` | Event type `"Carry"` | `COUNT(carry) / minutes * 90` | **High** | — |
| 23 | prog_carries_p90 | **Derived** | `Carry` | `location` + `carry.end_location` | `COUNT(carry WHERE end_x - start_x > threshold) / minutes * 90`; threshold ~5y forward | **High** | — |
| 24 | passes_into_final_third_p90 | **Derived** | `Pass` | `pass.end_location` (x) | `COUNT(pass WHERE end_x >= 80 AND start_x < 80) / minutes * 90` | **High** | — |
| 25 | switches_p90 | **Direct** | `Pass` | `pass.switch == True` | `COUNT(pass WHERE switch=True) / minutes * 90` | **High** | — |
| 26 | pressures_p90 | **Direct** | `Pressure` | Event type `"Pressure"` | `COUNT(pressure) / minutes * 90` | **High** | — |
| 27 | pressures_final_third_p90 | **Derived** | `Pressure` | `location` (x) | `COUNT(pressure WHERE x >= 80) / minutes * 90` | **High** | — |
| 28 | pressures_mid_third_p90 | **Derived** | `Pressure` | `location` (x) | `COUNT(pressure WHERE 40 < x < 80) / minutes * 90` | **High** | — |
| 29 | fouls_p90 | **Direct** | `Foul Committed` | Event type `"Foul Committed"` | `COUNT(foul_committed) / minutes * 90` | **High** | — |
| 30 | duels_won_p90 | **Derived** | `Duel` | `duel.outcome.name ∈ {"Won", "Success In Play", "Success Out"}` | `COUNT(duel WHERE won outcome) / minutes * 90` (outcome set verified in data) | **High** | — |
| 31 | recoveries_p90 | **Direct** | `Ball Recovery` | Event type `"Ball Recovery"` | `COUNT(ball_recovery) / minutes * 90` | **High** | — |
| 32 | crosses_p90 | **Direct** | `Pass` | `pass.cross == True` | `COUNT(pass WHERE cross=True) / minutes * 90` | **High** | — |
| 33 | cross_accuracy_pct | **Derived** | `Pass` | `pass.cross == True`, `pass.outcome.name` | `COUNT(cross WHERE outcome IS NULL=complete) / COUNT(cross)` | **Medium** | Drop accuracy; use volume only |
| 34 | final_third_entries_p90 | **Derived** | `Carry`, `Pass` | Both end_location coords | `COUNT(carry OR pass ending in final third) / minutes * 90` | **High** | — |
| 35 | touches_att_pen_p90 | **Derived** | `Ball Receipt*` | `location` | `COUNT(Ball Receipt* WHERE x>=102 AND 18<=y<=62) / minutes * 90` (receptions only, P6) | **High** | — |
| 36 | key_passes_p90 | **Direct** | `Pass` | `pass.shot_assist == True` | `COUNT(pass WHERE shot_assist=True) / minutes * 90` | **High** | — |
| 37 | xA_p90 | **Impossible** | — | No expected assist model in open data | N/A | **Low** | Use `key_passes_p90` (shot assists) as proxy |
| 38 | dribbles_p90 | **Direct** | `Dribble` | Event type `"Dribble"` (take-ons) | `COUNT(dribble) / minutes * 90` | **High** | — |
| 39 | carries_into_box_p90 | **Derived** | `Carry` | `carry.end_location` | `COUNT(carry WHERE end_x>=102 AND 18<end_y<62) / minutes * 90` | **High** | — |
| 40 | dribble_success_pct | **Direct** | `Dribble` | `dribble.outcome.name` | `COUNT(outcome=Complete) / COUNT(dribble)` | **High** | — |
| 41 | shot_creating_actions_p90 | **Proxy** | `Pass` | `pass.shot_assist` | `= key_passes_p90` (P6). True SCA impossible in open data: shot `related_events` carry only outcome events, never buildup. Locked proxy | **Medium** | — |
| 42 | touches_wide_p90 | **Derived** | All events | `location` (y) | `COUNT(events WHERE y<=16 OR y>=64) / minutes * 90` | **High** | — |
| 43 | touches_halfspace_p90 | **Derived** | All events | `location` (y) | `COUNT(events WHERE 16<y<25 OR 55<y<64) / minutes * 90` | **Medium** | Merge into wide/central buckets |
| 44 | through_balls_p90 | **Direct** | `Pass` | `pass.through_ball == True` | `COUNT(pass WHERE through_ball=True) / minutes * 90` | **High** | — |
| 45 | passes_into_box_p90 | **Derived** | `Pass` | `pass.end_location` | `COUNT(pass WHERE end_x>=102 AND 18<end_y<62) / minutes * 90` | **High** | — |
| 46 | gls_p90 | **Direct** | `Shot` | `shot.outcome.name == "Goal"` | `COUNT(shot WHERE outcome=Goal) / minutes * 90` | **High** | — |
| 47 | shots_p90 | **Direct** | `Shot` | Event type `"Shot"` | `COUNT(shot) / minutes * 90` | **High** | — |
| 48 | xG_p90 | **Direct** | `Shot` | `shot.statsbomb_xg` | `SUM(shot.statsbomb_xg) / minutes * 90` | **High** | — |
| 49 | shots_on_target_p90 | **Derived** | `Shot` | `shot.outcome.name IN ("Goal","Saved","Saved To Post")` | `COUNT(shots ON TARGET) / minutes * 90` | **High** | — |
| 50 | npxG_per_shot | **Derived** | `Shot` | `shot.type.name`, `shot.statsbomb_xg` | `SUM(xg WHERE type != Penalty) / COUNT(shots WHERE type != Penalty)` | **High** | — |
| 51 | conversion_pct | **Derived** | `Shot` | `shot.outcome.name` | `COUNT(outcome=Goal) / COUNT(shot)` | **High** | — |
| 52 | shots_on_target_pct | **Derived** | `Shot` | `shot.outcome.name` | `COUNT(on target) / COUNT(shot)` | **High** | — |
| 53 | box_entries_p90 | **Derived** | `Carry` | `carry.end_location` | `COUNT(carry entering box) / minutes * 90`; distinguishes from passes-into-box | **High** | — |
| 54 | final_third_touches_p90 | **Derived** | `Ball Receipt*` | `location` (x) | `COUNT(Ball Receipt* WHERE x>=80) / minutes * 90` (receptions only, P6) | **High** | — |
| 55 | one_touch_finishes_p90 | **Direct** | `Shot` | `shot.first_time == True` | `COUNT(shot WHERE first_time=True) / minutes * 90` | **High** | — |
| 56 | headers_p90 | **Derived** | `Shot`, `Clearance`, `Pass` | `shot.body_part.name` / `clearance.head` / `pass.aerial_won` | Ambiguous — "headers" could mean headed shots, headed clearances, or aerial duels | **Low** | Define scope: headed shots only → `shot.body_part.name contains "Head"` |
| 57 | headed_goals_p90 | **Derived** | `Shot` | `shot.outcome.name=="Goal"` AND `shot.body_part.name ≈ "Head"` | `COUNT(headed goals) / minutes * 90` | **High** | — |
| 58 | fouls_won_p90 | **Direct** | `Foul Won` | Event type `"Foul Won"` | `COUNT(foul_won) / minutes * 90` | **High** | — |
| 59 | hold_up_passes_p90 | **Impossible** | — | No dedicated event type for layoffs/hold-up | N/A | **Low** | `passes_received_p90` (receptions) as weak proxy |
| 60 | passes_received_p90 | **Direct** | `Ball Receipt` | Event type `"Ball Receipt"` | `COUNT(ball_receipt) / minutes * 90` | **High** | — |
| 61 | line_breaking_passes_p90 | **Impossible** | — | Requires 360 tracking data (player positions at event time) — NOT in open data | N/A | **Low** | `passes_into_final_third_p90` or `prog_passes_p90` |
| 62 | touches_6yard_box_p90 | **Derived** | All events | `location` | `COUNT(events WHERE x>=114 AND 27<y<53) / minutes * 90` | **High** | — |
| 63 | shot_assists_p90 | **Direct** | `Pass` | `pass.shot_assist == True` | `COUNT(shot_assist) / minutes * 90` | **High** | Same as key_passes_p90 |
| 64 | ast_p90 | **Direct** | `Pass` | `pass.goal_assist == True` | `COUNT(pass WHERE goal_assist=True) / minutes * 90` | **High** | — |
| 65 | touches_opp_box_p90 | **Derived** | All events | `location` | Same as touches_att_pen_p90 (#35) | **High** | — |

---

## Notes on Ambiguous Metrics

### headers_p90 (#56)
This term appears in the Target Man spec but is undefined. Possible meanings:
1. Headed **shots** → `shot.body_part.name` containing "Head"
2. Headed **clearances** → `clearance.head == True`
3. Headed **passes** → `pass.aerial_won == True`
4. Aerial duels won → duel type "Aerial Lost" inverted
5. All of the above combined

**Recommendation:** Define scope in the spec. For Target Man, headed shots (#1) makes most sense, but the existing "headers_p90" in the spec may need clarification.

### hold_up_passes_p90 (#59)
No StatsBomb event type captures "hold-up play" or "layoffs." The closest proxy would be short passes under pressure (back-to-goal, central areas), but this is too subjective to define reliably from event data alone.

**Recommendation:** Replace with `passes_received_p90` (ball receipts) as a measure of involvement in build-up.

### goals_prevented_p90 (#3, psxG - GA)
StatsBomb provides `shot.statsbomb_xg2` (post-shot expected goals / PSxG model) in the open data. Verified presence in WC 2022 events.
- Formula: `SUM(xg2 for all shots faced by GK) - (goals_conceded)`
- Per GK attribution: group shots faced by the GK's team as the defensive team
- **Confidence:** Medium — xg2 is a proper PSxG model, but the GK attribution logic requires careful team-side filtering

### cross_accuracy_pct (#33)
StatsBomb passes have `pass.outcome.name = "Incomplete"` for failed passes. A "completed" cross is one without an `Incomplete` outcome. However, crosses to no teammate (e.g., cut-out or over-hit) still count as "completed" in the event data if they weren't flagged incomplete.

**Recommendation:** Use with caution. Accept SB's native completion labelling.

### xA_p90 (#37)
StatsBomb **does not** publish xA (expected assists) in the open data. This is a commercial product feature.

**Recommendation:** Use `key_passes_p90` (shot assists) as a count-based proxy. Note in all outputs that this is a volume metric, not an expected-goal-weighted one.

### recoveries_p90 (#31)
StatsBomb `"Ball Recovery"` includes both offensive and defensive recoveries. The `ball_recovery.offensive` flag indicates recoveries won high up the pitch.

**Recommendation:** Keep as total recoveries. The offensive flag is available for further filtering if needed.

### one_touch_finishes / first_time (#55)
Available via `shot.first_time` boolean. The Poacher archetype also cares about one-touch finishing volume, not just ratio. This is a binary flag per shot — StatsBomb collectors label it based on whether the player struck the ball without taking a controlling touch.

---

## P6 Implementation Notes (2026-08-12)

The P6 extension derives 23 more features from the same StatsBomb events (see
`statsbomb_parser.py` P6_* constants and `build_master_dataset.py`
P6_MASTER_COLUMNS). Statuses above reflect the implemented recipes:

- **Penalties** are NOT linked via "Shot Saved". Dedicated GK types drive the
  count — `Penalty Saved` (won), `Penalty Conceded` (conceded), and a missed
  penalty surfaces as `Shot Faced` linked to a `shot.type.name == "Penalty"`
  shot. Verified: 15 saved, 64 faced across the tournament.
- **aerial_duel_pct** is approximate: WC2022 open-data `Duel` events have no
  outcome (all `Aerial Lost` carry `outcome: None`), so wins come from
  `pass.aerial_won` + `clearance.aerial_won` and the denominator adds the
  `Aerial Lost` duel count.
- **shot_creating_actions_p90** = `key_passes_p90` (proxy). Shot
  `related_events` only ever reference outcome events, so buildup cannot be
  reconstructed.
- **Duel outcomes**: won set is `{Won, Success In Play, Success Out}`; `Aerial
  Lost` duels never carry an outcome.
- **Shot outcomes**: on-target set is `{Goal, Saved, Saved to Post, Saved Off
  Target}`; `Blocked`, `Off T`, `Wayward` are off-target.
- **touches_att_pen / final_third_touches** are reception-based (`Ball Receipt*`
  only), not all-touch — matches the spec's "touches" intent while staying
  derivable from events.
- **conversion_pct / save_pct / shots_on_target_pct / dribble_success_pct** use
  a zero-guard (`x/0 → 0.0`) to fix the pre-existing `conversion_pct` overflow
  (1e9 for players with 1 goal and 0 shots).
- **pkwon / pkcon** dropped from all feature sets (fully null in the FBref GK
  export).

---

## Summary

### By Count

| Status | Count |
|--------|-------|
| Direct | 22 |
| Derived | 37 |
| Proxy | 1 |
| Impossible | 3 |

### Impossible Features (3)

| Feature | Why |
|---------|-----|
| xA_p90 | xA not published in open data; requires proprietary model |
| hold_up_passes_p90 | No event type captures "hold-up / layoff" concept |
| line_breaking_passes_p90 | Requires 360 freeze-frame (full player positions); not in open data |

---

## Final Approved Feature List (Realistic for StatsBomb Open Data)

All 65 features except the 3 impossible ones are buildable. The 3 impossible features are replaced with the following:

1. ~~xA_p90~~ → **key_passes_p90** + **shot_creating_actions_p90** (volume proxies)
2. ~~hold_up_passes_p90~~ → **passes_received_p90** (build-up involvement proxy)
3. ~~line_breaking_passes_p90~~ → **passes_into_final_third_p90** + **prog_passes_p90** (progression proxies)

### Data Pipeline Shape

```
Raw SB Events (JSON per match)
  → Event type filter (per player)
  → Aggregation per player per tournament
  → Per-90 normalization (minutes from lineup data)
  → Position assignment (from lineup position, not event-level position)
  → Min 270 min filter
  → Output: player x feature matrix (players × 62 usable features)
```

### Key Implementation Details

1. **Pitch zones** for location-based features (pass_end, carry_end, event location):
   - Final third: `x ≥ 80`
   - Attack penalty box: `x ≥ 102 AND 18 ≤ y ≤ 62`
   - Six-yard box: `x ≥ 114 AND 27 ≤ y ≤ 53`
   - Wide areas: `y ≤ 16 OR y ≥ 64`
   - Half-spaces: `(16 < y < 25) OR (55 < y < 64)`
   - Defensive third: `x ≤ 40`

2. **Progressive passes/carries** threshold:
   - Pass: `end_x - start_x ≥ 10` units (approx 8m forward, following typical SB convention)
   - Carry: `end_x - start_x ≥ 5` units (less aggressive threshold for carries)

3. **GK shot attribution:**
   - A GK "faces" all shots where the shooting team ≠ GK's team, excluding own goals
   - `shot.statsbomb_xg2` summed across those shots for PSxG

4. **Header / aerial tracking:**
   - Aerial duels: Duel events with `duel.type.name == "Aerial Lost"` (inverse — "Lost" means it was an aerial duel)
   - Aerial won on passes: `pass.aerial_won == True`
   - Aerial won on clearances: `clearance.aerial_won == True` (API v4)
