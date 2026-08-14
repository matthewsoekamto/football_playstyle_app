#!/usr/bin/env python3
"""StatsBomb Open Data parser — per-player raw event aggregates (P3).

Pure parsing/aggregation layer. Input is raw StatsBomb event JSON for the
FIFA World Cup 2022 (competition 43 / season 106); output is a tidy
per-player DataFrame of RAW aggregates that ``build_master_dataset.py``
converts into the 21 locked per-90 features.

Design rules (locked P3 contract):
  * No downloading, no FBref data, no player matching in this module.
  * Deterministic: matches are consumed in ascending ``match_id`` order and
    every aggregate is a sum/mean, so processing order cannot change output.
  * Counts are raw; per-90 normalisation happens downstream with the FBref
    ``90s`` denominator (``count / 90s``).
  * GK-scoped features are computed for any player who has the events; the
    integration step zero-fills non-GKs after the join.
  * The three authorised heuristics use the documented definitions:
      - goals_prevented_raw = SUM(statsbomb_xg over shots linked to the
        GK's "Shot Faced" events) - COUNT of the GK's "Goal Conceded" events
        (StatsBomb ``statsbomb_xg2`` is all-zero in this dataset, so the
        documented xG fallback is used; penalties/own-goals are excluded on
        both sides by the Shot-Faced linkage).
      - reflex_saves = GK "Shot Saved" events whose linked shot was taken
        within 5.5 yards of the goal line (perpendicular distance to x=120,
        i.e. inside the 6-yard box).
      - cross_accuracy = completed crosses / attempted crosses, where a
        cross is ``pass.cross == true`` and complete means ``pass.outcome``
        is absent (StatsBomb has no "Complete" outcome value).

Pitch model: 120 x 80, origin bottom-left. Every event is in the ACTING
team's frame (their attacking goal is x=120, their own goal is x=0), so a
player's events share one orientation and per-player zone logic needs no
flip. The one mirror is the GK's OWN penalty box used for
``def_actions_outside_box``: the docs' opponent-end box (x >= 102) would
classify every GK event (x ~ 0-10) as "outside", so the own box is
``x <= 18, 18 <= y <= 62`` and "outside" is its complement.

Touch-zone features (touches_wide / touches_halfspace / touches_6yard_box)
count the player's "Ball Receipt*" events (the StatsBomb touch event) whose
``location`` falls in the zone. This diverges from FEATURE_VALIDATION's
looser "all events" phrasing but is the football-correct touch definition.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator

import pandas as pd

# ---------------------------------------------------------------------------
# Pitch model / zones (yards, 120x80, origin bottom-left)
# ---------------------------------------------------------------------------
FINAL_THIRD_X = 80.0
MID_THIRD_MIN_X = 40.0                # mid third: 40 < x < 80
BOX_X_MIN = 102.0
BOX_Y_MIN = 18.0
BOX_Y_MAX = 62.0
SIX_YARD_X_MIN = 114.0
SIX_YARD_Y_MIN = 27.0
SIX_YARD_Y_MAX = 53.0
WIDE_Y_BOUND = 16.0                   # wide: y <= 16 or y >= 64
HALFSPACE_Y_LO = (16.0, 25.0)         # 16 < y < 25
HALFSPACE_Y_HI = (55.0, 64.0)         # 55 < y < 64
GK_OWN_BOX_X_MAX = 18.0               # GK own box: x<=18, 18<=y<=62 (mirror)
GK_OWN_BOX_Y_MIN = 18.0
GK_OWN_BOX_Y_MAX = 62.0
GOAL_LINE_X = 120.0                   # goal line (attacking team's frame)
REFLEX_DISTANCE_YDS = 5.5             # close-range threshold (inside 6-yd box)
LAUNCH_PASS_LENGTH = 40.0             # long GK pass threshold (units: yards)
PROG_PASS_DISTANCE = 10.0             # progressive pass: end_x - start_x >= 10
LONG_PASS_LENGTH = 25.0               # long pass threshold (yards)
HIGH_PASS_NAME = "High Pass"          # pass.height.name of lofted passes
SHOT_TYPE_PENALTY = "Penalty"         # shot.type.name of penalty kicks
DUEL_WON_OUTCOMES = frozenset({"Won", "Success In Play", "Success Out"})
SOT_OUTCOMES = frozenset({"Goal", "Saved", "Saved to Post", "Saved Off Target"})

# Event type names (exact strings from StatsBomb Open Data)
TYPE_BALL_RECEIPT = "Ball Receipt*"   # the asterisk is part of the type name

# GK-scoped master columns (zero-filled for non-GKs by the integration step)
GK_FEATURES = (
    "claims_p90",
    "sweeper_clearances_p90",
    "launch_passes_p90",
    "def_actions_outside_box_p90",
    "avg_def_position_y",
    "goals_prevented_p90",
    "reflex_saves_p90",
)

# Raw aggregate keys the integration step reads off the parser frame.
COUNT_FEATURES = (
    "pressures",
    "pressures_final_third",
    "pressures_mid_third",
    "claims",
    "sweeper_clearances",
    "headed_clearances",
    "recoveries",
    "passes_received",
    "one_touch_finishes",
    "launch_passes",
    "def_actions_outside_box",
    "touches_wide",
    "touches_halfspace",
    "touches_6yard_box",
    "final_third_entries",
    "carries_into_box",
    "reflex_saves",
    "headers",
)

# P6: position-scoped feature extension (additive — the locked P3 contract
# above is untouched). Raw per-90 count keys that the integration step reads
# off the parser frame via the build module's ``_P6_COUNT_MAP``.
P6_COUNT_FEATURES = (
    "passes",
    "prog_passes",
    "long_passes",
    "passes_into_final_third",
    "switches",
    "key_passes",
    "through_balls",
    "passes_into_box",
    "clearances",
    "blocks",
    "aerial_won",
    "duels_won",
    "shots",
    "shots_on_target",
    "headed_goals",
    "touches_att_pen",
    "final_third_touches",
)

# P6 ratio/sum components: not per-90 themselves, but the integration step
# reads them to build pass_completion_pct, aerial_duel_pct, npxG_per_shot,
# penalty_save_pct and xG_p90.
_P6_RATIO_KEYS = (
    "pass_completed",
    "aerial_lost",
    "penalty_saved",
    "penalty_faced",
    "xg_sum",
    "npxg_sum",
    "non_pen_shots",
)

# Every raw column the P6 extension appends to the parser frame.
P6_RAW_KEYS = P6_COUNT_FEATURES + _P6_RATIO_KEYS


def _loc(obj: object):
    """Return a [x, y] pair, or None when the object isn't a 2+ element list."""
    if isinstance(obj, (list, tuple)) and len(obj) >= 2:
        return (float(obj[0]), float(obj[1]))
    return None


def _in_box(x: float, y: float) -> bool:
    return x >= BOX_X_MIN and BOX_Y_MIN <= y <= BOX_Y_MAX


def _in_gk_own_box(x: float, y: float) -> bool:
    return x <= GK_OWN_BOX_X_MAX and GK_OWN_BOX_Y_MIN <= y <= GK_OWN_BOX_Y_MAX


def _new_record(player_name: str, team: str) -> dict:
    rec = {
        "player_name": player_name,
        "name_variants": {player_name},
        "teams": {team} if team else set(),
        "pressures": 0,
        "pressures_final_third": 0,
        "pressures_mid_third": 0,
        "claims": 0,
        "sweeper_clearances": 0,
        "headed_clearances": 0,
        "recoveries": 0,
        "passes_received": 0,
        "one_touch_finishes": 0,
        "launch_passes": 0,
        "def_actions_outside_box": 0,
        "touches_wide": 0,
        "touches_halfspace": 0,
        "touches_6yard_box": 0,
        "final_third_entries": 0,
        "carries_into_box": 0,
        "reflex_saves": 0,
        "headers": 0,
        "xg_faced": 0.0,
        "goals_conceded": 0,
        "cross_attempted": 0,
        "cross_completed": 0,
        "def_y_sum": 0.0,
        "def_y_n": 0,
    }
    for key in P6_RAW_KEYS:
        rec[key] = 0
    return rec


def _accumulate(ev: dict, rec: dict, shot_index: dict) -> None:
    """Fold one event into a player's aggregate record."""
    et = ev.get("type", {}).get("name")
    loc = _loc(ev.get("location"))

    # avg_def_position_y / def_actions_outside_box share the "GK's own box"
    # frame (x<=18, 18<=y<=62). Integration zero-fills these for non-GKs.
    if loc is not None:
        x, y = loc
        rec["def_y_sum"] += y
        rec["def_y_n"] += 1
        if not _in_gk_own_box(x, y):
            rec["def_actions_outside_box"] += 1

    if et == "Pressure":
        rec["pressures"] += 1
        if loc is not None:
            x = loc[0]
            if x >= FINAL_THIRD_X:
                rec["pressures_final_third"] += 1
            elif MID_THIRD_MIN_X < x < FINAL_THIRD_X:
                rec["pressures_mid_third"] += 1

    elif et == TYPE_BALL_RECEIPT:
        rec["passes_received"] += 1
        if loc is not None:
            x, y = loc
            if y <= WIDE_Y_BOUND or y >= 80.0 - WIDE_Y_BOUND:
                rec["touches_wide"] += 1
            elif (HALFSPACE_Y_LO[0] < y < HALFSPACE_Y_LO[1]
                  or HALFSPACE_Y_HI[0] < y < HALFSPACE_Y_HI[1]):
                rec["touches_halfspace"] += 1
            if x >= SIX_YARD_X_MIN and SIX_YARD_Y_MIN < y < SIX_YARD_Y_MAX:
                rec["touches_6yard_box"] += 1
            if x >= FINAL_THIRD_X:
                rec["final_third_touches"] += 1
            if _in_box(x, y):
                rec["touches_att_pen"] += 1

    elif et == "Clearance":
        rec["clearances"] += 1
        if ev.get("clearance", {}).get("head"):
            rec["headed_clearances"] += 1
        if ev.get("clearance", {}).get("aerial_won"):
            rec["aerial_won"] += 1

    elif et == "Block":
        rec["blocks"] += 1

    elif et == "Duel":
        duel = ev.get("duel", {})
        if duel.get("type", {}).get("name") == "Aerial Lost":
            rec["aerial_lost"] += 1
        if duel.get("outcome", {}).get("name") in DUEL_WON_OUTCOMES:
            rec["duels_won"] += 1

    elif et == "Ball Recovery":
        rec["recoveries"] += 1

    elif et == "Shot":
        shot = ev.get("shot", {})
        if shot.get("first_time"):
            rec["one_touch_finishes"] += 1
        if shot.get("body_part", {}).get("name") == "Head":
            rec["headers"] += 1
        rec["shots"] += 1
        xg = shot.get("statsbomb_xg")
        outcome = shot.get("outcome", {}).get("name")
        if xg is not None:
            rec["xg_sum"] += xg
        if outcome in SOT_OUTCOMES:
            rec["shots_on_target"] += 1
        if shot.get("type", {}).get("name") != SHOT_TYPE_PENALTY:
            rec["non_pen_shots"] += 1
            if xg is not None:
                rec["npxg_sum"] += xg
        if shot.get("body_part", {}).get("name") == "Head" and outcome == "Goal":
            rec["headed_goals"] += 1

    elif et == "Pass":
        p = ev.get("pass", {})
        if p.get("cross"):
            rec["cross_attempted"] += 1
            if "outcome" not in p:      # absent outcome == complete
                rec["cross_completed"] += 1
        if p.get("length", 0.0) > LAUNCH_PASS_LENGTH:
            rec["launch_passes"] += 1
        end = _loc(p.get("end_location"))
        if end is not None and loc is not None:
            if end[0] >= FINAL_THIRD_X and loc[0] < FINAL_THIRD_X:
                rec["final_third_entries"] += 1
        # --- P6 pass features ---
        rec["passes"] += 1
        if "outcome" not in p:          # absent outcome == complete
            rec["pass_completed"] += 1
        if end is not None and loc is not None:
            if end[0] - loc[0] >= PROG_PASS_DISTANCE:
                rec["prog_passes"] += 1
            if loc[0] < FINAL_THIRD_X <= end[0]:
                rec["passes_into_final_third"] += 1
            if _in_box(end[0], end[1]):
                rec["passes_into_box"] += 1
        if (p.get("length", 0.0) > LONG_PASS_LENGTH
                or p.get("height", {}).get("name") == HIGH_PASS_NAME):
            rec["long_passes"] += 1
        if p.get("switch"):
            rec["switches"] += 1
        if p.get("shot_assist"):
            rec["key_passes"] += 1
        if p.get("through_ball"):
            rec["through_balls"] += 1
        if p.get("aerial_won"):
            rec["aerial_won"] += 1

    elif et == "Carry":
        end = _loc(ev.get("carry", {}).get("end_location"))
        if end is not None and loc is not None:
            if end[0] >= FINAL_THIRD_X and loc[0] < FINAL_THIRD_X:
                rec["final_third_entries"] += 1
            if _in_box(end[0], end[1]) and not _in_box(loc[0], loc[1]):
                rec["carries_into_box"] += 1

    elif et == "Goal Keeper":
        gk = ev.get("goalkeeper", {})
        gk_type = gk.get("type", {}).get("name")
        if gk_type == "Collected":
            rec["claims"] += 1
        elif gk_type == "Keeper Sweeper":
            rec["sweeper_clearances"] += 1
        elif gk_type == "Goal Conceded":
            rec["goals_conceded"] += 1
        elif gk_type == "Shot Faced":
            for rid in ev.get("related_events", []):
                shot = shot_index.get(rid)
                if shot is not None and shot["xg"] is not None:
                    rec["xg_faced"] += shot["xg"]
            # P6: a penalty that was missed (post / off target) surfaces as a
            # "Shot Faced" event linked to the Penalty shot — it is still a
            # penalty faced. Scored and saved penalties have their own GK
            # types ("Penalty Conceded" / "Penalty Saved") handled below.
            for rid in ev.get("related_events", []):
                shot = shot_index.get(rid)
                if shot is not None and shot["shot_type"] == SHOT_TYPE_PENALTY:
                    rec["penalty_faced"] += 1
                    break
        elif gk_type == "Shot Saved":
            for rid in ev.get("related_events", []):
                shot = shot_index.get(rid)
                if shot is not None and shot["location"] is not None:
                    sx, _sy = shot["location"]
                    # Perpendicular distance to the goal line (x=120): a
                    # save qualifies as reflex when the shot was taken
                    # within 5.5 yards of goal (inside the 6-yard box).
                    if GOAL_LINE_X - sx < REFLEX_DISTANCE_YDS:
                        rec["reflex_saves"] += 1
                        break
        elif gk_type == "Penalty Saved":
            rec["penalty_saved"] += 1
            rec["penalty_faced"] += 1
        elif gk_type == "Penalty Conceded":
            rec["penalty_faced"] += 1


def parse_events(events: Iterable[dict]) -> pd.DataFrame:
    """Aggregate raw StatsBomb events into one row per StatsBomb player_id.

    Two passes over the event stream: the first indexes Shot events (their
    ``statsbomb_xg`` and origin location are needed to resolve the GK's
    "Shot Faced" / "Shot Saved" related_events links); the second folds each
    event into its player's aggregate.
    """
    events = list(events)

    shot_index: dict = {}
    for ev in events:
        if ev.get("type", {}).get("name") == "Shot":
            shot = ev.get("shot", {})
            shot_index[ev["id"]] = {
                "xg": shot.get("statsbomb_xg"),
                # Shot ORIGIN (top-level location), not shot.end_location
                # (which is where the ball ended, near goal). Reflex distance
                # is measured from where the shot was taken.
                "location": _loc(ev.get("location")),
                # shot.type.name (e.g. "Penalty") for the P6 penalty linkage.
                "shot_type": shot.get("type", {}).get("name"),
            }

    players: dict = {}
    for ev in events:
        player = ev.get("player")
        if player is None:
            continue
        pid = player["id"]
        rec = players.get(pid)
        if rec is None:
            team = ev.get("team", {}).get("name")
            rec = _new_record(player["name"], team)
            players[pid] = rec
        else:
            rec["name_variants"].add(player["name"])
            team = ev.get("team", {}).get("name")
            if team:
                rec["teams"].add(team)
        _accumulate(ev, rec, shot_index)

    rows = []
    for pid, rec in players.items():
        row = {
            "player_id": pid,
            "player_name": rec["player_name"],
            "name_variants": ";".join(sorted(rec["name_variants"])),
            "teams": ";".join(sorted(rec["teams"])),
            "pressures": rec["pressures"],
            "pressures_final_third": rec["pressures_final_third"],
            "pressures_mid_third": rec["pressures_mid_third"],
            "claims": rec["claims"],
            "sweeper_clearances": rec["sweeper_clearances"],
            "headed_clearances": rec["headed_clearances"],
            "recoveries": rec["recoveries"],
            "passes_received": rec["passes_received"],
            "one_touch_finishes": rec["one_touch_finishes"],
            "launch_passes": rec["launch_passes"],
            "def_actions_outside_box": rec["def_actions_outside_box"],
            "touches_wide": rec["touches_wide"],
            "touches_halfspace": rec["touches_halfspace"],
            "touches_6yard_box": rec["touches_6yard_box"],
            "final_third_entries": rec["final_third_entries"],
            "carries_into_box": rec["carries_into_box"],
            "goals_prevented_raw": rec["xg_faced"] - rec["goals_conceded"],
            "reflex_saves": rec["reflex_saves"],
            "headers": rec["headers"],
            "cross_attempted": rec["cross_attempted"],
            "cross_completed": rec["cross_completed"],
            "avg_def_y": (rec["def_y_sum"] / rec["def_y_n"]
                          if rec["def_y_n"] else None),
        }
        for key in P6_RAW_KEYS:
            row[key] = rec[key]
        rows.append(row)

    df = pd.DataFrame(rows, columns=list(rows[0]) if rows else None)
    if not df.empty:
        df = df.sort_values("player_id").reset_index(drop=True)
    return df


def iter_match_events(data_dir: str | Path) -> Iterator[dict]:
    """Yield every event in ``<data_dir>/events/*.json``, match order."""
    events_dir = Path(data_dir) / "events"
    for path in sorted(events_dir.glob("*.json")):
        with open(path, encoding="utf-8") as fh:
            yield from json.load(fh)


def parse_competition(data_dir: str | Path) -> pd.DataFrame:
    """Aggregate all matches under ``data_dir`` (raw events + lineups)."""
    return parse_events(iter_match_events(data_dir))


# ---------------------------------------------------------------------------
# Position groups from StatsBomb lineups (P6 ``position_v2``)
# ---------------------------------------------------------------------------
# 23 StatsBomb lineup position names -> 6 clustering groups. The group names
# are the identifiers the v2 engine clusters by (GK/CB/FB-WB/MF/Wide/ST).
POSITION_GROUP_MAP = {
    "Goalkeeper": "GK",
    "Center Back": "CB", "Right Center Back": "CB", "Left Center Back": "CB",
    "Right Back": "FB/WB", "Left Back": "FB/WB",
    "Right Wing Back": "FB/WB", "Left Wing Back": "FB/WB",
    "Defensive Midfield": "MF", "Right Defensive Midfield": "MF",
    "Center Defensive Midfield": "MF", "Left Defensive Midfield": "MF",
    "Right Center Midfield": "MF", "Center Midfield": "MF",
    "Left Center Midfield": "MF",
    "Right Attacking Midfield": "MF", "Center Attacking Midfield": "MF",
    "Left Attacking Midfield": "MF",
    "Right Midfield": "MF", "Left Midfield": "MF",
    "Right Wing": "Wide", "Left Wing": "Wide",
    "Right Center Forward": "ST", "Center Forward": "ST",
    "Left Center Forward": "ST",
}

# Display-only fine position labels (ADR-013): the same raw lineup position,
# mapped to conventional side/role naming for the UI. Clustering stays on the
# coarse POSITION_GROUP_MAP above; this map is never used by the engine.
POSITION_FINE_MAP = {
    "Goalkeeper": "GK",
    "Center Back": "CB", "Right Center Back": "CB", "Left Center Back": "CB",
    "Right Back": "RB", "Left Back": "LB",
    "Right Wing Back": "RWB", "Left Wing Back": "LWB",
    "Defensive Midfield": "DM", "Right Defensive Midfield": "DM",
    "Center Defensive Midfield": "DM", "Left Defensive Midfield": "DM",
    "Right Center Midfield": "CM", "Center Midfield": "CM",
    "Left Center Midfield": "CM",
    "Right Attacking Midfield": "AM", "Center Attacking Midfield": "AM",
    "Left Attacking Midfield": "AM",
    "Right Midfield": "RM", "Left Midfield": "LM",
    "Right Wing": "RW", "Left Wing": "LW",
    "Right Center Forward": "ST", "Center Forward": "ST",
    "Left Center Forward": "ST",
}


def _ts_to_seconds(ts) -> float | None:
    """Parse a StatsBomb match-clock timestamp (``"MM:SS"``) into seconds."""
    if not ts:
        return None
    parts = str(ts).split(":")
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]) * 60 + int(parts[1])
    except ValueError:
        return None


def parse_lineups(data_dir: str | Path) -> pd.DataFrame:
    """Derive each player's most-played position across all matches.

    Reads ``<data_dir>/lineups/*.json``. Lineup ``positions[]`` segments carry
    match-clock ``from``/``to`` timestamps (``"MM:SS"``); a segment with
    ``to == null`` runs to the final whistle. The final-whistle clock is taken
    from the match's events file (``max(minute*60 + second)`` — the official
    match clock, exact through stoppage/extra time); if the events file is
    missing it falls back to the latest explicit lineup endpoint. Each player's
    position is duration-weighted across segments and matches; ties break to
    the lowest ``position_id``.

    Returns one row per player with ``position_v2`` (one of the 6 groups, or
    ``"Unknown"`` when no lineup data exists) and ``position_minutes``.
    """
    records: dict = {}
    lineups_dir = Path(data_dir) / "lineups"
    events_dir = Path(data_dir) / "events"
    for path in sorted(lineups_dir.glob("*.json")):
        with open(path, encoding="utf-8") as fh:
            match = json.load(fh)

        # Final-whistle clock. The events file's max (minute*60 + second) is
        # the exact end of play; the latest explicit lineup endpoint is only a
        # lower bound (a null-to segment's ``from``) and would truncate the
        # last position segment for anyone who plays to the whistle.
        match_end = None
        events_path = events_dir / path.name
        if events_path.is_file():
            with open(events_path, encoding="utf-8") as fh:
                clock = [
                    (ev.get("minute", 0) or 0) * 60 + (ev.get("second", 0) or 0)
                    for ev in json.load(fh)
                ]
            if clock:
                match_end = max(clock)
        if match_end is None:
            endpoints = [
                s for seg in (
                    (seg.get("from"), seg.get("to"))
                    for team in match
                    for ply in team.get("lineup", [])
                    for seg in ply.get("positions", []))
                for s in (_ts_to_seconds(seg[0]), _ts_to_seconds(seg[1]))
                if s is not None
            ]
            match_end = max(endpoints) if endpoints else 90 * 60

        for team in match:
            team_name = team.get("team_name", "")
            for ply in team.get("lineup", []):
                pid = ply["player_id"]
                rec = records.setdefault(pid, {
                    "player_name": ply["player_name"],
                    "name_variants": set(),
                    "teams": set(),
                    "duration_by_pos": {},
                    "minutes": 0.0,
                })
                rec["name_variants"].add(ply["player_name"])
                if team_name:
                    rec["teams"].add(team_name)
                for seg in ply.get("positions", []):
                    start = _ts_to_seconds(seg.get("from"))
                    end = _ts_to_seconds(seg.get("to"))
                    if end is None:
                        end = match_end
                    pos_name = seg.get("position")
                    pos_id = seg.get("position_id")
                    if (start is None or end <= start
                            or pos_name is None or pos_id is None):
                        continue
                    dur = (end - start) / 60.0
                    rec["duration_by_pos"].setdefault(pos_id, [0.0, pos_name])
                    rec["duration_by_pos"][pos_id][0] += dur
                    rec["minutes"] += dur

    rows = []
    for pid, rec in records.items():
        best = None
        if rec["duration_by_pos"]:
            # max key (duration, -position_id): ties -> lowest position_id.
            pos_id, (dur, name) = max(
                rec["duration_by_pos"].items(),
                key=lambda kv: (kv[1][0], -kv[0]))
            best = name
        rows.append({
            "player_id": pid,
            "player_name": rec["player_name"],
            "name_variants": ";".join(sorted(rec["name_variants"])),
            "teams": ";".join(sorted(rec["teams"])),
            "position_v2": (POSITION_GROUP_MAP.get(best, "Unknown")
                            if best else "Unknown"),
            "position_detail": (POSITION_FINE_MAP.get(best, "Unknown")
                                if best else "Unknown"),
            "position_minutes": rec["minutes"],
        })

    df = pd.DataFrame(rows, columns=list(rows[0]) if rows else None)
    if not df.empty:
        df = df.sort_values("player_id").reset_index(drop=True)
    return df


def main() -> None:
    data_dir = Path(__file__).resolve().parent / "data" / "statsbomb"
    print(f"Parsing StatsBomb events from {data_dir} ...")
    df = parse_competition(data_dir)
    print(f"Parsed {len(df)} players "
          f"({df['player_id'].nunique()} unique player_ids)")
    for col in COUNT_FEATURES:
        total = int(df[col].sum())
        nz = int((df[col] > 0).sum())
        print(f"  {col:>26}: total={total:>7}  players>0={nz}")
    print(f"  {'goals_prevented_raw':>26}: "
          f"sum={df['goals_prevented_raw'].sum():.2f}")
    print(f"  {'avg_def_y':>26}: mean={df['avg_def_y'].mean():.2f} "
          f"(players={int(df['avg_def_y'].notna().sum())})")
    print(f"  {'cross_completed':>26}: {int(df['cross_completed'].sum())} / "
          f"{int(df['cross_attempted'].sum())}")


if __name__ == "__main__":
    main()
