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
    return {
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

    elif et == "Clearance":
        if ev.get("clearance", {}).get("head"):
            rec["headed_clearances"] += 1

    elif et == "Ball Recovery":
        rec["recoveries"] += 1

    elif et == "Shot":
        shot = ev.get("shot", {})
        if shot.get("first_time"):
            rec["one_touch_finishes"] += 1
        if shot.get("body_part", {}).get("name") == "Head":
            rec["headers"] += 1

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
        rows.append({
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
        })

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
