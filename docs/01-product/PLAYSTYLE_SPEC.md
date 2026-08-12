20 Archetypes — Feature Design Specs

---
Goalkeepers (2)

1. Shot Stopper

Important
- saves_p90
- save_pct
- goals_prevented_p90 (psxG − GA)
- claims_p90 (high crosses caught)
- reflex_saves_p90 (close-range)

Not Important
- passes_p90
- long_passes_p90
- prog_passes_p90
- def_actions_outside_box_p90
- avg_def_position_y

---
2. Sweeper Keeper

Important
- def_actions_outside_box_p90
- passes_p90
- long_passes_p90
- prog_passes_p90
- launch_passes_p90 (>40m)
- avg_def_position_y (high, 12–20m off line)
- claims_p90
- sweeper_clearances_p90

Not Important
- save_pct (average is fine)
- reflex_saves_p90
- penalty_save_pct

---
Centre-Backs (3)

3. Traditional Centre Back

Important
- clearances_p90
- blocks_p90
- aerial_duels_won_p90
- aerial_duel_pct
- interceptions_p90
- tackles_won_p90
- headed_clearances_p90

Not Important
- prog_passes_p90
- carries_p90
- prog_carries_p90
- pass_completion_pct (basic is fine)
- key_passes_p90
- gls_p90 / ast_p90

---
4. Ball-Playing Centre Back

Important
- prog_passes_p90
- pass_completion_pct (>85%)
- long_passes_p90
- carries_p90
- prog_carries_p90
- passes_into_final_third_p90
- switches_p90
- line_breaking_passes_p90

Not Important
- clearances_p90 (average)
- blocks_p90
- aerial_duels_won_p90 (average)
- tackles_won_p90 (low)
- fouls_p90

---
5. Stopper / Destroyer

Important
- tackles_won_p90
- interceptions_p90
- pressures_p90
- pressures_final_third_p90
- fouls_p90
- duels_won_p90
- recoveries_p90
- blocks_p90

Not Important
- prog_passes_p90
- carries_p90
- pass_completion_pct
- long_passes_p90
- gls_p90 / ast_p90

---
Full-Backs / Wing-Backs (3)

6. Defensive Fullback

Important
- tackles_won_p90
- interceptions_p90
- recoveries_p90
- pressures_p90
- blocks_p90
- clearances_p90
- duels_won_p90
- fouls_p90

Not Important
- crosses_p90
- prog_carries_p90
- prog_passes_p90
- final_third_entries_p90
- dribbles_p90
- ast_p90 / xA_p90
- gls_p90

---
7. Attacking Fullback

Important
- crosses_p90
- cross_accuracy_pct
- prog_carries_p90
- prog_passes_p90
- final_third_entries_p90
- touches_att_pen_p90
- key_passes_p90
- xA_p90
- dribbles_p90

Not Important
- tackles_won_p90 (average)
- clearances_p90
- blocks_p90
- aerial_duels_won_p90
- interceptions_p90 (low)

---
8. Wingback

Important
- crosses_p90 (highest volume)
- prog_carries_p90 (highest volume)
- carries_p90
- final_third_entries_p90 (highest)
- touches_att_pen_p90
- dribbles_p90
- dribble_success_pct
- ast_p90 / xA_p90
- prog_passes_p90
- shot_creating_actions_p90

Not Important
- tackles_won_p90
- interceptions_p90
- clearances_p90
- blocks_p90
- aerial_duels_won_p90
- pressures_p90 (low relative to attacking output)

---
Midfielders (5)

9. Defensive Midfielder (Anchor)

Important
- tackles_won_p90
- interceptions_p90
- recoveries_p90
- pressures_p90
- pressures_mid_third_p90
- fouls_p90
- duels_won_p90
- blocks_p90
- pass_completion_pct (high, short passes)

Not Important
- prog_passes_p90
- long_passes_p90
- key_passes_p90
- carries_p90
- prog_carries_p90
- shots_p90
- xG_p90
- gls_p90 / ast_p90

---
10. Deep-Lying Playmaker (DLP)

Important
- prog_passes_p90
- pass_completion_pct (>88%)
- long_passes_p90
- switches_p90
- passes_into_final_third_p90
- line_breaking_passes_p90
- xA_p90
- key_passes_p90

Not Important
- tackles_won_p90 (low)
- interceptions_p90 (low)
- pressures_p90 (low)
- dribbles_p90
- carries_p90
- shots_p90
- gls_p90

---
11. Box-to-Box Midfielder

Important
- tackles_won_p90
- interceptions_p90
- pressures_p90
- prog_carries_p90
- carries_p90
- prog_passes_p90
- shots_p90
- xG_p90
- gls_p90
- ast_p90
- box_entries_p90
- final_third_touches_p90

Not Important
- long_passes_p90
- switches_p90
- crosses_p90
- aerial_duels_won_p90
- clearances_p90

---
12. Advanced Playmaker (Number 10)

Important
- key_passes_p90
- through_balls_p90
- shot_creating_actions_p90
- xA_p90
- ast_p90
- prog_passes_p90
- passes_into_box_p90
- touches_att_box_p90
- dribbles_p90

Not Important
- tackles_won_p90
- interceptions_p90
- pressures_p90
- clearances_p90
- blocks_p90
- long_passes_p90
- aerial_duels_won_p90
- carries_p90 (low progressive)

---
13. Shadow Striker

Important
- gls_p90
- shots_p90
- xG_p90
- box_touches_p90
- shots_on_target_p90
- npxG_per_shot
- prog_carries_p90
- carries_into_box_p90
- shot_creating_actions_p90

Not Important
- tackles_won_p90
- interceptions_p90
- pressures_p90
- key_passes_p90 (low)
- ast_p90 (low)
- crosses_p90
- long_passes_p90
- pass_completion_pct

---
Wide Players (3)

14. Traditional Winger

Important
- crosses_p90 (high volume)
- cross_accuracy_pct
- dribbles_p90
- dribble_success_pct
- prog_carries_p90 (wide channel)
- touches_wide_p90
- final_third_entries_p90
- ast_p90 / xA_p90

Not Important
- shots_p90 (low)
- xG_p90
- gls_p90
- through_balls_p90
- key_passes_p90 (from crossing, not through balls)
- touches_halfspace_p90
- prog_passes_p90

---
15. Inverted Winger / Inside Forward

Important
- shots_p90
- xG_p90
- gls_p90
- dribbles_p90
- dribble_success_pct
- prog_carries_p90 (into half-space/box)
- touches_halfspace_p90
- box_touches_p90
- shots_on_target_p90
- npxG_per_shot

Not Important
- crosses_p90 (very low)
- cross_accuracy_pct
- touches_wide_p90
- key_passes_p90 (low)
- through_balls_p90
- ast_p90

---
16. Wide Playmaker

Important
- key_passes_p90
- through_balls_p90
- shot_creating_actions_p90
- xA_p90
- ast_p90
- prog_passes_p90
- passes_into_box_p90
- crosses_p90 (accurate, not volume)
- touches_halfspace_p90
- prog_carries_p90

Not Important
- shots_p90
- xG_p90
- gls_p90
- dribbles_p90
- touches_wide_p90
- tackles_won_p90
- interceptions_p90
- pressures_p90

---
Strikers (4)

17. Poacher

Important
- gls_p90
- xG_p90
- shots_p90
- conversion_pct (G/Sh)
- npxG_per_shot
- shots_on_target_pct
- box_touches_p90
- touches_6yard_box_p90
- one_touch_finishes_p90

Not Important
- ast_p90 / xA_p90
- key_passes_p90
- through_balls_p90
- prog_passes_p90
- carries_p90
- prog_carries_p90
- dribbles_p90
- aerial_duels_won_p90
- pressures_final_third_p90

---
18. Target Man

Important
- aerial_duels_won_p90
- aerial_duel_pct
- headers_p90
- headed_goals_p90
- fouls_won_p90
- hold_up_passes_p90 (layoffs)
- passes_received_p90
- touches_opp_box_p90
- gls_p90 (from headers)

Not Important
- shots_p90 (low volume, mostly headers)
- prog_carries_p90
- dribbles_p90
- key_passes_p90 (low)
- through_balls_p90
- prog_passes_p90
- pressures_final_third_p90
- xG_per_shot (low, headed xG is low)
