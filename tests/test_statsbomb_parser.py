"""Tests for statsbomb_parser.py and the P3 integration in build_master_dataset.

The fixture under ``tests/fixtures/statsbomb/events/`` is a small slice of REAL
StatsBomb Open Data (FIFA World Cup 2022, competition 43 / season 106): 25
events covering every feature path — pressures in both thirds, all three touch
zones, headed/regular clearances, ball recoveries, one-touch and header shots,
complete/incomplete crosses, launch passes, final-third entries, carries into
the box, all five GK sub-types, and the two linked-shot cases that exercise the
reflex-save distance threshold. Expected values below are hand-derived from the
pitch model, not read back from the parser.
"""
import json
from itertools import count

import pytest

import pandas as pd

import statsbomb_parser as p
import build_master_dataset as b

_UID = count()  # deterministic unique ids for synthetic events

FIXTURE_DIR = __import__("pathlib").Path(__file__).resolve().parent / "fixtures" / "statsbomb"
DATA_DIR = __import__("pathlib").Path(__file__).resolve().parent.parent / "data"

# --- locked contract guards -------------------------------------------------

def test_contract_column_counts():
    """The locked P3 contract stays 18 count features + 7 GK features."""
    assert len(p.COUNT_FEATURES) == 18
    assert len(p.GK_FEATURES) == 7
    assert len(b.P3_MASTER_COLUMNS) == 21
    assert set(p.GK_FEATURES) <= set(b.P3_MASTER_COLUMNS)
    assert set(b._P3_COUNT_MAP) == set(p.COUNT_FEATURES)


def test_p6_contract_column_counts():
    """P6 is additive: 17 count features, 24 raw keys, 23 master columns."""
    assert len(p.P6_COUNT_FEATURES) == 17
    assert len(p.P6_RAW_KEYS) == 24
    assert len(b.P6_MASTER_COLUMNS) == 23
    assert set(b._P6_COUNT_MAP) == set(p.P6_COUNT_FEATURES)
    assert set(b._P6_GK_COLUMNS) == {"penalty_save_pct"}
    # The P3 contract is untouched by the additive extension.
    assert len(p.COUNT_FEATURES) == 18
    assert len(p.GK_FEATURES) == 7
    assert len(b.P3_MASTER_COLUMNS) == 21


def test_gk_features_match_build_module():
    """Parser GK feature names and the build module's GK gate agree."""
    assert set(p.GK_FEATURES) == set(b._P3_GK_COLUMNS)


# --- synthetic event builders (match the real JSON schema) ------------------

def _ev(type_name, pid=1, pname="Player", team="Denmark", loc=None, **extra):
    e = {
        "id": f"ev-{next(_UID)}",
        "type": {"name": type_name},
        "player": {"id": pid, "name": pname},
        "team": {"name": team},
    }
    if loc is not None:
        e["location"] = list(loc)
    e.update(extra)
    return e


def _shot(loc, xg=None, pid=10, pname="Shooter", **shot_extra):
    shot = {"statsbomb_xg": xg}
    shot.update(shot_extra)
    return _ev("Shot", pid=pid, pname=pname, loc=loc, shot=shot)


def _gk(type_name, shot_id=None, pid=20, pname="Keeper", loc=(2.0, 40.0)):
    e = _ev("Goal Keeper", pid=pid, pname=pname, loc=loc,
            goalkeeper={"type": {"name": type_name}})
    if shot_id is not None:
        e["related_events"] = [shot_id]
    return e


def _parse(events):
    return p.parse_events(events)


# --- fixture-based: end-to-end parse of the real-event slice ----------------

def test_fixture_row_count_and_order():
    """One row per player, sorted ascending by player_id."""
    df = _parse(p.iter_match_events(FIXTURE_DIR))
    assert len(df) == 14
    assert df["player_id"].is_unique
    assert df["player_id"].is_monotonic_increasing
    assert len(df.columns) == 26 + len(p.P6_RAW_KEYS)


def test_fixture_pressure_zones():
    """Dolberg presses the final third, Msakni the mid third."""
    df = _parse(p.iter_match_events(FIXTURE_DIR))
    dol = df.set_index("player_name").loc["Kasper Dolberg"]
    assert dol["pressures"] == 1
    assert dol["pressures_final_third"] == 1
    assert dol["pressures_mid_third"] == 0
    msk = df.set_index("player_name").loc["Youssef Msakni"]
    assert msk["pressures"] == 1
    assert msk["pressures_final_third"] == 0
    assert msk["pressures_mid_third"] == 1


def test_fixture_touch_zones():
    """Ball Receipt* zones: wide, halfspace, 6-yard box, and neutral."""
    df = df_by_name()
    assert df["Rasmus Nissen Kristensen"]["touches_wide"] == 1
    assert df["Andreas Skov Olsen"]["touches_halfspace"] == 1
    assert df["Youssef Msakni"]["touches_6yard_box"] == 1
    assert df["Christian Dannemann Eriksen"]["touches_wide"] == 0
    assert df["Christian Dannemann Eriksen"]["touches_halfspace"] == 0
    assert df["Christian Dannemann Eriksen"]["touches_6yard_box"] == 0


def df_by_name():
    """Return {player_name: row Series} for the fixture parse."""
    df = _parse(p.iter_match_events(FIXTURE_DIR))
    return {r["player_name"]: r for _, r in df.iterrows()}


def test_fixture_clearances_and_recoveries():
    df = df_by_name()
    assert df["Yassine Meriah"]["headed_clearances"] == 1
    assert df["Ali Abdi"]["headed_clearances"] == 0     # clearance.head is None
    assert df["Joakim Mæhle"]["recoveries"] == 1


def test_fixture_shots():
    df = df_by_name()
    assert df["Kasper Dolberg"]["one_touch_finishes"] == 1   # first_time=True
    assert df["Joachim Andersen"]["one_touch_finishes"] == 1
    assert df["Youssef Msakni"]["one_touch_finishes"] == 0   # two non-first-time shots
    assert df["Youssef Msakni"]["headers"] == 1              # body_part Head
    assert df["Kasper Dolberg"]["headers"] == 0


def test_fixture_crosses():
    df = df_by_name()
    assert df["Christian Dannemann Eriksen"]["cross_completed"] == 1
    assert df["Christian Dannemann Eriksen"]["cross_attempted"] == 1
    assert df["Rasmus Nissen Kristensen"]["cross_completed"] == 0
    assert df["Rasmus Nissen Kristensen"]["cross_attempted"] == 1  # Incomplete


def test_fixture_launch_passes():
    df = df_by_name()
    assert df["Christian Dannemann Eriksen"]["launch_passes"] == 1
    assert df["Rasmus Nissen Kristensen"]["launch_passes"] == 0


def test_fixture_final_third_and_carry():
    df = df_by_name()
    assert df["Andreas Skov Olsen"]["final_third_entries"] == 1
    assert df["Ali Abdi"]["carries_into_box"] == 1
    assert df["Ali Abdi"]["final_third_entries"] == 0


def test_fixture_gk_events():
    df = df_by_name()
    assert df["Aymen Dahmen"]["claims"] == 1
    assert df["Kasper Schmeichel"]["sweeper_clearances"] == 1
    # Goal Conceded contributes to goals_prevented_raw via subtraction.
    assert df["Shūichi Gonda"]["goals_prevented_raw"] == -1.0
    # Shot Faced adds the linked shot's xg; Gonda's Goal Conceded does not.
    assert df["Kasper Schmeichel"]["goals_prevented_raw"] == pytest.approx(0.023819994)
    assert df["Aymen Dahmen"]["goals_prevented_raw"] == 0.0


def test_fixture_reflex_saves():
    """Reflex = Shot Saved whose linked shot was taken < 5.5 yds from goal."""
    df = df_by_name()
    assert df["Gregor Kobel"]["reflex_saves"] == 1      # shot at (115.4, 38.6)
    assert df["Aymen Dahmen"]["reflex_saves"] == 0      # shot at (99.7, 30.3): far


def test_fixture_gk_own_box_and_avg_def_y():
    """def_actions_outside_box uses the GK own-box frame; avg_def_y is the mean y."""
    df = df_by_name()
    # GKs: every located event is inside their own box -> outside count 0.
    for name in ("Aymen Dahmen", "Kasper Schmeichel", "Gregor Kobel", "Shūichi Gonda"):
        assert df[name]["def_actions_outside_box"] == 0, name
    # Meriah's clearance at (15.8, 39.8) is inside the own box too.
    assert df["Yassine Meriah"]["def_actions_outside_box"] == 0
    # Abdi's clearance (2.1, 24.6) is inside, but his carry origin (96.2, 13.5) is not.
    assert df["Ali Abdi"]["def_actions_outside_box"] == 1
    # Mean y over all located events.
    assert df["Kasper Schmeichel"]["avg_def_y"] == pytest.approx(47.15)
    assert df["Youssef Msakni"]["avg_def_y"] == pytest.approx(34.925)


def test_fixture_deterministic():
    """Same input twice -> identical output (pure sum/mean aggregation)."""
    df1 = _parse(p.iter_match_events(FIXTURE_DIR))
    df2 = _parse(p.iter_match_events(FIXTURE_DIR))
    assert df1.equals(df2)


# --- synthetic boundary cases ------------------------------------------------

def test_zone_helpers():
    assert p._loc([117.3, 33.7]) == (117.3, 33.7)
    assert p._loc([1.0]) is None
    assert p._loc("nope") is None
    assert p._loc(None) is None
    # Box: x >= 102, 18 <= y <= 62. Boundaries inclusive.
    assert p._in_box(102.0, 18.0)
    assert p._in_box(102.0, 62.0)
    assert not p._in_box(101.9, 40.0)
    assert not p._in_box(102.0, 17.9)
    # GK own box: x <= 18, 18 <= y <= 62. Boundaries inclusive.
    assert p._in_gk_own_box(18.0, 18.0)
    assert p._in_gk_own_box(0.0, 62.0)
    assert not p._in_gk_own_box(18.1, 40.0)
    assert not p._in_gk_own_box(2.0, 17.9)


def test_pressure_zone_boundaries():
    """x=80 is final third; x=40 is NOT mid third (mid is 40 < x < 80)."""
    evs = [
        _ev("Pressure", loc=(80.0, 40.0)),        # final third
        _ev("Pressure", loc=(79.9, 40.0)),        # not final
        _ev("Pressure", loc=(40.1, 40.0)),        # mid third
        _ev("Pressure", loc=(40.0, 40.0)),        # not mid (exclusive lower)
    ]
    rec = _parse(evs).iloc[0]
    assert rec["pressures"] == 4
    assert rec["pressures_final_third"] == 1
    assert rec["pressures_mid_third"] == 2   # (79.9, 40) and (40.1, 40) are both mid third


def test_touch_zone_boundaries():
    """Wide/halfspace split at y=16/25/55/64; 6-yard box interior is strict."""
    evs = [
        _ev("Ball Receipt*", loc=(50.0, 16.0)),   # wide (y <= 16)
        _ev("Ball Receipt*", loc=(50.0, 16.1)),   # halfspace lo (16 < y < 25)
        _ev("Ball Receipt*", loc=(50.0, 55.5)),   # halfspace hi (55 < y < 64)
        _ev("Ball Receipt*", loc=(50.0, 64.0)),   # wide (y >= 64)
        _ev("Ball Receipt*", loc=(114.0, 27.0)),  # 6-yard: x>=114 but y==27 strict
        _ev("Ball Receipt*", loc=(114.1, 27.1)),  # 6-yard: interior
        _ev("Ball Receipt*", loc=(50.0, 40.0)),   # neutral
    ]
    rec = _parse(evs).iloc[0]
    assert rec["passes_received"] == 7
    assert rec["touches_wide"] == 2
    assert rec["touches_halfspace"] == 2
    assert rec["touches_6yard_box"] == 1


def test_launch_pass_threshold():
    """Launch pass requires length strictly > 40 (yards)."""
    evs = [
        _ev("Pass", loc=(2.0, 40.0), **{"pass": {"length": 40.0, "end_location": [42.0, 40.0]}}),
        _ev("Pass", loc=(2.0, 40.0), **{"pass": {"length": 40.1, "end_location": [42.0, 40.0]}}),
    ]
    rec = _parse(evs).iloc[0]
    assert rec["launch_passes"] == 1


def test_cross_completion():
    """Absent pass.outcome == complete; any outcome value == incomplete."""
    evs = [
        _ev("Pass", loc=(60.0, 40.0), **{"pass": {"cross": True, "end_location": [90.0, 40.0]}}),
        _ev("Pass", loc=(60.0, 40.0), **{"pass": {"cross": True,
                                                  "outcome": {"name": "Incomplete"},
                                                  "end_location": [90.0, 40.0]}}),
        _ev("Pass", loc=(60.0, 40.0), **{"pass": {"cross": False, "end_location": [90.0, 40.0]}}),
    ]
    rec = _parse(evs).iloc[0]
    assert rec["cross_attempted"] == 2
    assert rec["cross_completed"] == 1


def test_final_third_entries_boundaries():
    """Pass/carry counts only when it CROSSES the x=80 line (start < 80 <= end)."""
    evs = [
        _ev("Pass", loc=(79.9, 40.0), **{"pass": {"end_location": [80.0, 40.0]}}),   # crosses
        _ev("Pass", loc=(80.0, 40.0), **{"pass": {"end_location": [90.0, 40.0]}}),   # starts at line
        _ev("Carry", loc=(79.9, 40.0), **{"carry": {"end_location": [81.0, 40.0]}}),  # crosses
        _ev("Carry", loc=(40.0, 40.0), **{"carry": {"end_location": [60.0, 40.0]}}),  # stays out
    ]
    rec = _parse(evs).iloc[0]
    assert rec["final_third_entries"] == 2


def test_carries_into_box_boundaries():
    """Carry counts when it crosses INTO the box (end in box, start not)."""
    evs = [
        _ev("Carry", loc=(101.9, 40.0), **{"carry": {"end_location": [102.0, 40.0]}}),  # crosses
        _ev("Carry", loc=(102.0, 40.0), **{"carry": {"end_location": [110.0, 40.0]}}),  # starts in box
        _ev("Carry", loc=(101.0, 17.9), **{"carry": {"end_location": [103.0, 17.9]}}),  # end y outside
    ]
    rec = _parse(evs).iloc[0]
    assert rec["carries_into_box"] == 1


def test_reflex_distance_boundary():
    """Reflex threshold is strictly < 5.5 yds from the goal line (x=120)."""
    close = _shot(loc=(114.6, 40.0), xg=0.4)     # 5.4 yds -> reflex
    edge = _shot(loc=(114.5, 40.0), xg=0.4)      # exactly 5.5 -> NOT reflex
    far = _shot(loc=(114.4, 40.0), xg=0.4)       # 5.6 yds -> NOT reflex
    evs = [
        close, _gk("Shot Saved", shot_id=close["id"]),
        edge, _gk("Shot Saved", shot_id=edge["id"]),
        far, _gk("Shot Saved", shot_id=far["id"]),
    ]
    gk_row = _parse(evs).set_index("player_id").loc[20]
    assert gk_row["reflex_saves"] == 1


def test_shot_faced_adds_linked_xg_only():
    """Shot Faced sums the linked shot's statsbomb_xg (xg2 is all-zero here)."""
    s1 = _shot(loc=(90.0, 40.0), xg=0.3)
    s2 = _shot(loc=(91.0, 40.0), xg=0.2)
    s3 = _shot(loc=(92.0, 40.0), xg=None)          # shot with no xg: ignored
    evs = [
        s1, s2, s3,
        _gk("Shot Faced", shot_id=s1["id"], pid=20),
        _gk("Shot Faced", shot_id=s2["id"], pid=20),
        _gk("Shot Faced", shot_id=s3["id"], pid=20),
        _gk("Goal Conceded", pid=20),
    ]
    gk_row = _parse(evs).set_index("player_id").loc[20]
    assert gk_row["goals_prevented_raw"] == pytest.approx(0.3 + 0.2 - 1.0)


def test_p6_pass_features():
    """P6 pass counters: progressive, completion, zones, switches, key/through."""
    evs = [
        _ev("Pass", loc=(40.0, 40.0),
            **{"pass": {"end_location": [55.0, 40.0], "length": 15.0}}),   # prog (+15)
        _ev("Pass", loc=(79.0, 40.0),
            **{"pass": {"end_location": [85.0, 40.0], "length": 6.0}}),     # into final third
        _ev("Pass", loc=(90.0, 40.0),
            **{"pass": {"end_location": [103.0, 50.0], "length": 13.0}}),   # into box + prog
        _ev("Pass", loc=(40.0, 40.0),
            **{"pass": {"end_location": [42.0, 40.0], "length": 2.0,
                        "switch": True, "shot_assist": True,
                        "through_ball": True}}),                            # switch+key+through
        _ev("Pass", loc=(40.0, 40.0),
            **{"pass": {"end_location": [41.0, 40.0], "length": 30.0,
                        "height": {"name": "Low Pass"}}}),                  # long by length
        _ev("Pass", loc=(40.0, 40.0),
            **{"pass": {"end_location": [41.0, 40.0], "length": 3.0,
                        "height": {"name": "High Pass"}}}),                 # long by height
        _ev("Pass", loc=(40.0, 40.0),
            **{"pass": {"end_location": [42.0, 40.0], "length": 2.0,
                        "outcome": {"name": "Incomplete"}}}),               # not completed
    ]
    rec = _parse(evs).iloc[0]
    assert rec["passes"] == 7
    assert rec["pass_completed"] == 6
    assert rec["prog_passes"] == 2          # pass1 (+15) and pass3 (+13)
    assert rec["passes_into_final_third"] == 1
    assert rec["passes_into_box"] == 1      # only pass3 ends inside the box
    assert rec["switches"] == 1
    assert rec["key_passes"] == 1
    assert rec["through_balls"] == 1
    assert rec["long_passes"] == 2


def test_p6_defensive_features():
    """Clearances, blocks, duels won, and aerial duels (pass + clearance)."""
    evs = [
        _ev("Clearance", loc=(20.0, 40.0),
            **{"clearance": {"head": True, "aerial_won": True}}),
        _ev("Clearance", loc=(20.0, 40.0),
            **{"clearance": {"aerial_won": True}}),
        _ev("Block", loc=(50.0, 40.0)),
        _ev("Duel", loc=(50.0, 40.0),
            **{"duel": {"type": {"name": "Tackle"}, "outcome": {"name": "Won"}}}),
        _ev("Duel", loc=(50.0, 40.0),
            **{"duel": {"type": {"name": "Tackle"},
                        "outcome": {"name": "Success In Play"}}}),
        _ev("Duel", loc=(50.0, 40.0),
            **{"duel": {"type": {"name": "Tackle"}, "outcome": {"name": "Lost Out"}}}),
        _ev("Duel", loc=(50.0, 40.0),
            **{"duel": {"type": {"name": "Aerial Lost"}}}),   # real data: no outcome
        _ev("Pass", loc=(40.0, 40.0),
            **{"pass": {"aerial_won": True, "end_location": [42.0, 40.0], "length": 2.0}}),
    ]
    rec = _parse(evs).iloc[0]
    assert rec["clearances"] == 2
    assert rec["headed_clearances"] == 1    # P3: clearance.head
    assert rec["blocks"] == 1
    assert rec["duels_won"] == 2            # Won + Success In Play; Lost Out excluded
    assert rec["aerial_won"] == 3           # 2 clearances + 1 pass
    assert rec["aerial_lost"] == 1          # the outcome-less Aerial Lost duel


def test_p6_shot_features():
    """Shots, xG, on-target, npxG (penalty-excluded), and headed goals."""
    evs = [
        _shot(loc=(90.0, 40.0), xg=0.4, outcome={"name": "Goal"}),
        _shot(loc=(91.0, 40.0), xg=0.2, outcome={"name": "Saved"}),
        _shot(loc=(92.0, 40.0), xg=0.1, outcome={"name": "Blocked"}),
        _shot(loc=(93.0, 40.0), xg=0.5, outcome={"name": "Goal"},
              body_part={"name": "Head"}),
        _shot(loc=(94.0, 40.0), xg=0.9, type={"name": "Penalty"},
              outcome={"name": "Goal"}),
    ]
    rec = _parse(evs).iloc[0]
    assert rec["shots"] == 5
    assert rec["xg_sum"] == pytest.approx(2.1)
    assert rec["shots_on_target"] == 4      # Goal, Saved, head-Goal, penalty-Goal
    assert rec["non_pen_shots"] == 4        # excludes the penalty
    assert rec["npxg_sum"] == pytest.approx(1.2)
    assert rec["headed_goals"] == 1


def test_p6_touch_features():
    """P6 touch counters from Ball Receipt*: box and final-third."""
    evs = [
        _ev("Ball Receipt*", loc=(102.0, 18.0)),   # box corner, inclusive
        _ev("Ball Receipt*", loc=(80.0, 40.0)),    # final third
        _ev("Ball Receipt*", loc=(79.9, 40.0)),    # not final third
        _ev("Ball Receipt*", loc=(50.0, 40.0)),    # neither
    ]
    rec = _parse(evs).iloc[0]
    assert rec["touches_att_pen"] == 1
    assert rec["final_third_touches"] == 2


def test_p6_penalty_linkage():
    """Penalty Saved / Penalty Conceded drive penalty_saved and penalty_faced."""
    evs = [
        _gk("Penalty Saved", pid=20),
        _gk("Penalty Conceded", pid=20),
        _gk("Penalty Conceded", pid=20),
        _gk("Collected", pid=20),
    ]
    gk_row = _parse(evs).set_index("player_id").loc[20]
    assert gk_row["penalty_saved"] == 1
    assert gk_row["penalty_faced"] == 3


def test_p6_penalty_missed_via_shot_faced():
    """A missed penalty (post/off-target) reaches the GK as a linked Shot Faced."""
    pen = _shot(loc=(100.0, 40.0), xg=0.9, type={"name": "Penalty"},
                outcome={"name": "Off T"})
    evs = [
        pen,
        _gk("Shot Faced", shot_id=pen["id"], pid=20),
        _gk("Shot Faced", pid=20),            # ordinary shot: no penalty link
    ]
    gk_row = _parse(evs).set_index("player_id").loc[20]
    assert gk_row["penalty_faced"] == 1
    assert gk_row["penalty_saved"] == 0


def test_missing_location_handled():
    """Events without a location don't poison def_y (avg_def_y becomes None)."""
    evs = [
        _ev("Pressure", loc=(50.0, 40.0)),           # located
        _ev("Pressure"),                              # no location
        _gk("Collected", pid=20, loc=None),           # GK event without location
    ]
    df = _parse(evs)
    out = df.set_index("player_id").loc[1]
    assert out["pressures"] == 2
    assert out["avg_def_y"] == 40.0
    gk = df.set_index("player_id").loc[20]
    assert pd.isna(gk["avg_def_y"]), "no located events -> NaN, not None, in a DataFrame"
    assert gk["def_actions_outside_box"] == 0


def test_event_without_player_skipped():
    """Events with no player (e.g. own-goal events) don't create rows."""
    evs = [
        _ev("Ball Recovery", pid=1),
        {"id": "no-player", "type": {"name": "Shot"}, "location": [100.0, 40.0]},
        {"id": "no-player-2", "type": {"name": "Pressure"}, "location": [50.0, 40.0]},
    ]
    df = _parse(evs)
    assert len(df) == 1
    assert df.iloc[0]["player_id"] == 1


def test_multiple_teams_and_name_variants():
    """name_variants/teams aggregate across a player's events."""
    evs = [
        _ev("Pressure", pid=1, pname="J. Name", team="Denmark"),
        _ev("Pressure", pid=1, pname="Jonas Name", team="Denmark"),
        _ev("Pressure", pid=1, pname="Jonas Name", team="Sweden"),
    ]
    rec = _parse(evs).iloc[0]
    assert rec["name_variants"] == "J. Name;Jonas Name"
    assert rec["teams"] == "Denmark;Sweden"


def test_iter_match_events_ascending_order(tmp_path):
    """iter_match_events consumes files in ascending STRING order (globs sorted)."""
    ev_dir = tmp_path / "events"
    ev_dir.mkdir()
    for fname, n in (("2.json", 2), ("10.json", 10), ("1.json", 1)):
        (ev_dir / fname).write_text(
            json.dumps([{"id": f"ev-{fname}-{i}", "type": {"name": "Pressure"},
                         "player": {"id": i, "name": f"P{i}"},
                         "team": {"name": "Denmark"}, "location": [50.0, 40.0]}
                        for i in range(n)]), encoding="utf-8")
    # Lexical sort puts "10.json" before "2.json". Real WC2022 match ids are
    # all 7 digits, so string order == numeric order there.
    ids = [e["id"] for e in p.iter_match_events(tmp_path)]
    assert ids == (["ev-1.json-0"]
                   + [f"ev-10.json-{i}" for i in range(10)]
                   + ["ev-2.json-0", "ev-2.json-1"])


# --- integration: merge_statsbomb_event_features -----------------------------

def _sb_events_frame(rows):
    cols = (["player_id", "name_variants", "teams", "goals_prevented_raw",
             "avg_def_y", "cross_attempted", "cross_completed"]
            + list(p.COUNT_FEATURES) + list(p.P6_RAW_KEYS))
    df = pd.DataFrame(rows, columns=cols)
    # P6 raw counters default to zero unless a test explicitly supplies them.
    df[list(p.P6_RAW_KEYS)] = df[list(p.P6_RAW_KEYS)].fillna(0)
    return df.astype({"player_id": int})


def _base_master():
    return pd.DataFrame({
        "player": ["Alice GK", "Bob Out", "Carol Out", "No Events", "Zero Min GK"],
        "player_sb": ["Alice GK", "Bob Out", "Carol Out", None, "Zero Min GK"],
        "squad_n": ["denmark", "tunisia", "tunisia", "qatar", "denmark"],
        "pos_n": ["GK", "DF", "MF", "FW", "GK"],
        "90s": [3.0, 4.0, 5.0, 2.0, 0.0],
    })


def test_merge_per90_and_ratio():
    """Counts divide by 90s; avg_def_y is a mean; cross_accuracy is a ratio."""
    rows = [
        {"player_id": 1, "name_variants": "Alice GK", "teams": "Denmark",
         "pressures": 90, "passes_received": 60, "goals_prevented_raw": 1.5,
         "avg_def_y": 40.0, "cross_attempted": 10, "cross_completed": 6,
         **{c: 0 for c in p.COUNT_FEATURES if c not in ("pressures", "passes_received")}},
        {"player_id": 2, "name_variants": "Bob Out", "teams": "Tunisia",
         "pressures": 120, "passes_received": 80, "goals_prevented_raw": 0.0,
         "avg_def_y": 30.0, "cross_attempted": 2, "cross_completed": 1,
         **{c: 0 for c in p.COUNT_FEATURES if c not in ("pressures", "passes_received")}},
    ]
    sb = _sb_events_frame(rows)
    master = b.merge_statsbomb_event_features(_base_master(), sb)

    alice = master.set_index("player_sb").loc["Alice GK"]
    assert alice["pressures_p90"] == pytest.approx(90 / 3.0)
    assert alice["passes_received_p90"] == pytest.approx(60 / 3.0)
    assert alice["goals_prevented_p90"] == pytest.approx(1.5 / 3.0)
    assert alice["avg_def_position_y"] == pytest.approx(40.0)
    assert alice["cross_accuracy_pct"] == pytest.approx(0.6)

    bob = master.set_index("player_sb").loc["Bob Out"]
    assert bob["pressures_p90"] == pytest.approx(120 / 4.0)
    assert bob["cross_accuracy_pct"] == pytest.approx(0.5)
    assert bob["goals_prevented_p90"] == 0.0


def test_merge_gk_gating():
    """The 7 GK features are zeroed for non-GKs; GK rows keep theirs."""
    rows = [
        {"player_id": 1, "name_variants": "Alice GK", "teams": "Denmark",
         "pressures": 90, "claims": 3, "sweeper_clearances": 2, "launch_passes": 4,
         "def_actions_outside_box": 1, "reflex_saves": 1, "goals_prevented_raw": 0.5,
         "avg_def_y": 40.0, "cross_attempted": 0, "cross_completed": 0,
         **{c: 0 for c in p.COUNT_FEATURES
            if c not in ("pressures", "claims", "sweeper_clearances",
                         "launch_passes", "def_actions_outside_box",
                         "reflex_saves")}},
        {"player_id": 2, "name_variants": "Bob Out", "teams": "Tunisia",
         "pressures": 120, "claims": 3, "sweeper_clearances": 2, "launch_passes": 4,
         "def_actions_outside_box": 1, "reflex_saves": 1, "goals_prevented_raw": 0.5,
         "avg_def_y": 30.0, "cross_attempted": 0, "cross_completed": 0,
         **{c: 0 for c in p.COUNT_FEATURES
            if c not in ("pressures", "claims", "sweeper_clearances",
                         "launch_passes", "def_actions_outside_box",
                         "reflex_saves")}},
    ]
    sb = _sb_events_frame(rows)
    master = b.merge_statsbomb_event_features(_base_master(), sb)
    master = master.set_index("player_sb")

    alice = master.loc["Alice GK"]     # GK
    assert alice["claims_p90"] == pytest.approx(3 / 3.0)
    assert alice["sweeper_clearances_p90"] == pytest.approx(2 / 3.0)
    assert alice["launch_passes_p90"] == pytest.approx(4 / 3.0)
    assert alice["def_actions_outside_box_p90"] == pytest.approx(1 / 3.0)
    assert alice["reflex_saves_p90"] == pytest.approx(1 / 3.0)
    assert alice["goals_prevented_p90"] == pytest.approx(0.5 / 3.0)

    bob = master.loc["Bob Out"]        # DF -> all 7 GK features zeroed
    for col in b._P3_GK_COLUMNS:
        assert bob[col] == 0.0, col
    # Non-GK keeps non-GK features.
    assert bob["pressures_p90"] == pytest.approx(120 / 4.0)


def test_merge_unmatched_rows_stay_zero():
    """Rows with player_sb=None (or no event activity) get all-zero P3 cols."""
    rows = [
        {"player_id": 1, "name_variants": "Alice GK", "teams": "Denmark",
         "pressures": 90, **{c: 0 for c in p.COUNT_FEATURES if c != "pressures"},
         "goals_prevented_raw": 0.0, "avg_def_y": 40.0,
         "cross_attempted": 0, "cross_completed": 0},
    ]
    sb = _sb_events_frame(rows)
    master = b.merge_statsbomb_event_features(_base_master(), sb)
    master = master.set_index("player")
    for name in ("No Events", "Carol Out"):
        for col in b.P3_MASTER_COLUMNS:
            assert master.loc[name, col] == 0.0, (name, col)


def test_merge_squad_mismatch_raises():
    """Master squad_n must match the event team (normalized) for that player."""
    rows = [
        {"player_id": 1, "name_variants": "Alice GK", "teams": "Denmark",
         "pressures": 90, **{c: 0 for c in p.COUNT_FEATURES if c != "pressures"},
         "goals_prevented_raw": 0.0, "avg_def_y": 40.0,
         "cross_attempted": 0, "cross_completed": 0},
    ]
    sb = _sb_events_frame(rows)
    master = _base_master()
    master.loc[0, "squad_n"] = "japan"     # Alice's events are Denmark-only
    with pytest.raises(AssertionError):
        b.merge_statsbomb_event_features(master, sb)


def test_merge_double_attach_raises():
    """The same StatsBomb player_id must not attach to two master rows."""
    rows = [
        {"player_id": 1, "name_variants": "Alice GK", "teams": "Denmark",
         "pressures": 90, **{c: 0 for c in p.COUNT_FEATURES if c != "pressures"},
         "goals_prevented_raw": 0.0, "avg_def_y": 40.0,
         "cross_attempted": 0, "cross_completed": 0},
    ]
    sb = _sb_events_frame(rows)
    master = _base_master()
    master.loc[4, "player_sb"] = "Alice GK"     # two GK rows, same name+squad
    with pytest.raises(AssertionError):
        b.merge_statsbomb_event_features(master, sb)


def test_merge_zero_minutes_guard():
    """A 90s=0 row must not produce NaN (division by zero -> 0)."""
    rows = [
        {"player_id": 1, "name_variants": "Zero Min GK", "teams": "Denmark",
         "claims": 3, "reflex_saves": 1, "goals_prevented_raw": 0.5, "avg_def_y": 40.0,
         "cross_attempted": 0, "cross_completed": 0,
         **{c: 0 for c in p.COUNT_FEATURES
            if c not in ("claims", "reflex_saves")}},
    ]
    sb = _sb_events_frame(rows)
    master = pd.DataFrame({
        "player": ["Zero Min GK"], "player_sb": ["Zero Min GK"],
        "squad_n": ["denmark"], "pos_n": ["GK"], "90s": [0.0],
    })
    merged = b.merge_statsbomb_event_features(master, sb)
    # avg_def_position_y is a MEAN (never divided by 90s), so it survives; the
    # per-90 / ratio columns all collapse to 0 for a zero-minute row.
    assert merged.iloc[0]["avg_def_position_y"] == pytest.approx(40.0)
    for col in b.P3_MASTER_COLUMNS:
        if col == "avg_def_position_y":
            continue
        assert merged.iloc[0][col] == 0.0, col


def test_merge_real_fixture_bridge():
    """Real parser output bridges to master rows via name + normalized squad."""
    sb_events = p.parse_competition(FIXTURE_DIR)
    master = pd.DataFrame({
        "player": ["Kasper Dolberg", "Kasper Schmeichel", "Youssef Msakni"],
        "player_sb": ["Kasper Dolberg", "Kasper Schmeichel", "Youssef Msakni"],
        "squad_n": ["denmark", "denmark", "tunisia"],
        "pos_n": ["FW", "GK", "MF"],
        "90s": [3.0, 3.0, 3.0],
    })
    merged = b.merge_statsbomb_event_features(master, sb_events)
    m = merged.set_index("player_sb")

    assert m.loc["Kasper Dolberg"]["one_touch_finishes_p90"] == pytest.approx(1 / 3.0)
    assert m.loc["Kasper Dolberg"]["claims_p90"] == 0.0          # non-GK gated
    assert m.loc["Kasper Schmeichel"]["sweeper_clearances_p90"] == pytest.approx(1 / 3.0)
    assert m.loc["Kasper Schmeichel"]["goals_prevented_p90"] == pytest.approx(0.023819994 / 3.0)
    assert m.loc["Kasper Schmeichel"]["avg_def_position_y"] == pytest.approx(47.15)
    assert m.loc["Kasper Schmeichel"]["pressures_p90"] == 0.0    # no pressures
    assert m.loc["Youssef Msakni"]["headers_p90"] == pytest.approx(1 / 3.0)


# --- P6: position_v2 (parse_lineups + merge_position_v2) ---------------------

def _seg(position, pos_id, frm, to, from_period=1, to_period=1):
    return {
        "position_id": pos_id,
        "position": position,
        "from": frm,
        "to": to,
        "from_period": from_period,
        "to_period": to_period,
        "start_reason": "Starting XI" if frm == "00:00" else "Tactical Shift",
        "end_reason": "Final Whistle" if to is None else "Tactical Shift",
    }


def _lineup_match(team_name, lineup):
    return [{"team_id": 1, "team_name": team_name, "lineup": lineup}]


def _write_position_data(tmp_path, matches, events=None):
    """Write lineup (and optional events) files so parse_lineups can read them."""
    ldir = tmp_path / "lineups"
    ldir.mkdir(exist_ok=True)
    for i, m in enumerate(matches):
        (ldir / f"{i}.json").write_text(json.dumps(m), encoding="utf-8")
    if events is not None:
        edir = tmp_path / "events"
        edir.mkdir(exist_ok=True)
        for i, evs in enumerate(events):
            (edir / f"{i}.json").write_text(json.dumps(evs), encoding="utf-8")
    return tmp_path


def test_position_group_map_covers_data_names():
    """Every position name StatsBomb used at WC2022 maps to a valid group."""
    data_names = {
        "Goalkeeper",
        "Center Back", "Right Center Back", "Left Center Back",
        "Right Back", "Left Back", "Right Wing Back", "Left Wing Back",
        "Right Defensive Midfield", "Center Defensive Midfield",
        "Left Defensive Midfield",
        "Right Center Midfield", "Left Center Midfield",
        "Right Attacking Midfield", "Center Attacking Midfield",
        "Left Attacking Midfield", "Right Midfield", "Left Midfield",
        "Right Wing", "Left Wing",
        "Right Center Forward", "Center Forward", "Left Center Forward",
    }
    groups = set(p.POSITION_GROUP_MAP.values())
    assert len(data_names) == 23
    assert groups == {"GK", "CB", "FB/WB", "MF", "Wide", "ST"}
    for name in data_names:
        assert p.POSITION_GROUP_MAP[name] in groups, name
    assert p.POSITION_GROUP_MAP["Goalkeeper"] == "GK"
    assert p.POSITION_GROUP_MAP["Right Wing Back"] == "FB/WB"
    assert p.POSITION_GROUP_MAP["Center Defensive Midfield"] == "MF"
    assert p.POSITION_GROUP_MAP["Left Wing"] == "Wide"
    assert p.POSITION_GROUP_MAP["Center Forward"] == "ST"


def test_position_fine_map():
    """The fine map refines MF/Wide/FB-WB; CB/ST/GK stay coarse; same domain."""
    assert p.POSITION_FINE_MAP["Left Back"] == "LB"
    assert p.POSITION_FINE_MAP["Right Wing Back"] == "RWB"
    assert p.POSITION_FINE_MAP["Defensive Midfield"] == "DM"
    assert p.POSITION_FINE_MAP["Center Midfield"] == "CM"
    assert p.POSITION_FINE_MAP["Left Attacking Midfield"] == "AM"
    assert p.POSITION_FINE_MAP["Right Midfield"] == "RM"
    assert p.POSITION_FINE_MAP["Left Wing"] == "LW"
    assert p.POSITION_FINE_MAP["Center Back"] == "CB"
    assert p.POSITION_FINE_MAP["Center Forward"] == "ST"
    assert p.POSITION_FINE_MAP["Goalkeeper"] == "GK"
    # Same domain as the coarse map — every raw position maps to a fine label.
    assert set(p.POSITION_FINE_MAP) == set(p.POSITION_GROUP_MAP)


def test_ts_to_seconds():
    assert p._ts_to_seconds("00:00") == 0
    assert p._ts_to_seconds("50:24") == 3024
    assert p._ts_to_seconds("105:00") == 6300   # extra time
    assert p._ts_to_seconds(None) is None
    assert p._ts_to_seconds("nope") is None


def test_parse_lineups_duration_weighted(tmp_path):
    """Most-played position is the duration-weighted mode."""
    lineup = [
        {"player_id": 1, "player_name": "Eriksen", "positions": [
            _seg("Left Center Midfield", 15, "00:00", "60:00"),
            _seg("Center Attacking Midfield", 19, "60:00", None),
        ]},
    ]
    tmp = _write_position_data(tmp_path, [_lineup_match("Denmark", lineup)],
                               events=[[{"minute": 90, "second": 0}]])
    df = p.parse_lineups(tmp)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["position_v2"] == "MF"
    assert row["position_detail"] == "CM"  # 60 min Left Center Midfield wins
    # 60 min at LCM + 30 min at CAM (final whistle from events at 90:00).
    assert row["position_minutes"] == pytest.approx(90.0)


def test_parse_lineups_tie_break(tmp_path):
    """Equal durations break deterministically to the lowest position_id."""
    lineup = [
        {"player_id": 1, "player_name": "Hybrid", "positions": [
            _seg("Right Wing", 20, "00:00", "45:00"),
            _seg("Right Center Back", 3, "45:00", None),
        ]},
    ]
    tmp = _write_position_data(tmp_path, [_lineup_match("Denmark", lineup)],
                               events=[[{"minute": 90, "second": 0}]])
    df = p.parse_lineups(tmp)
    # 45 min each; position_id 3 (CB) < 20 (Wide) -> CB wins.
    assert df.iloc[0]["position_v2"] == "CB"


def test_parse_lineups_unused_substitute(tmp_path):
    """A player with no position segments (unused sub) resolves to Unknown."""
    lineup = [
        {"player_id": 1, "player_name": "Starter", "positions": [
            _seg("Center Forward", 23, "00:00", None),
        ]},
        {"player_id": 2, "player_name": "Unused Sub", "positions": []},
    ]
    tmp = _write_position_data(tmp_path, [_lineup_match("Denmark", lineup)],
                               events=[[{"minute": 90, "second": 0}]])
    df = p.parse_lineups(tmp).set_index("player_id")
    assert df.loc[1, "position_v2"] == "ST"
    assert df.loc[2, "position_v2"] == "Unknown"
    assert df.loc[2, "position_minutes"] == 0.0


def test_parse_lineups_final_whistle_from_events(tmp_path):
    """A null-to segment runs to the EVENTS final whistle, not the max endpoint."""
    lineup = [
        {"player_id": 1, "player_name": "Full Match", "positions": [
            _seg("Center Back", 4, "00:00", None),
        ]},
        {"player_id": 2, "player_name": "Late Sub", "positions": [
            _seg("Center Back", 4, "75:00", None),
        ]},
    ]
    # Events clock runs to 96:00 (stoppage); the latest lineup endpoint is 75:00.
    tmp = _write_position_data(tmp_path, [_lineup_match("Denmark", lineup)],
                               events=[[{"minute": 96, "second": 0}]])
    df = p.parse_lineups(tmp).set_index("player_id")
    assert df.loc[1, "position_minutes"] == pytest.approx(96.0)
    assert df.loc[2, "position_minutes"] == pytest.approx(21.0)


def test_parse_lineups_multi_match_aggregate(tmp_path):
    """Durations accumulate across a player's matches (two files)."""
    match1 = _lineup_match("Denmark", [
        {"player_id": 1, "player_name": "Eriksen", "positions": [
            _seg("Center Midfield", 13, "00:00", None)]}])
    match2 = _lineup_match("Denmark", [
        {"player_id": 1, "player_name": "Eriksen", "positions": [
            _seg("Right Center Midfield", 12, "00:00", "80:00"),
            _seg("Center Attacking Midfield", 16, "80:00", None)]}])
    tmp = _write_position_data(tmp_path, [match1, match2],
                               events=[[{"minute": 90, "second": 0}],
                                       [{"minute": 90, "second": 0}]])
    df = p.parse_lineups(tmp).set_index("player_id")
    # 90 min CM (match 1) vs 80 min RCM + 10 min CAM (match 2).
    assert df.loc[1, "position_v2"] == "MF"
    assert df.loc[1, "position_minutes"] == pytest.approx(180.0)


def _sb_positions_frame(rows):
    df = pd.DataFrame(rows, columns=[
        "player_id", "player_name", "name_variants", "teams",
        "position_v2", "position_detail", "position_minutes"])
    return df.astype({"player_id": int})


def test_merge_position_v2_attaches():
    """Position groups attach via the shared identity bridge; others stay Unknown."""
    sb_pos = _sb_positions_frame([
        {"player_id": 1, "player_name": "Alice GK", "name_variants": "Alice GK",
         "teams": "Denmark", "position_v2": "GK", "position_detail": "GK", "position_minutes": 90.0},
        {"player_id": 2, "player_name": "Bob Out", "name_variants": "Bob Out",
         "teams": "Tunisia", "position_v2": "CB", "position_detail": "CB", "position_minutes": 85.0},
    ])
    master = b.merge_position_v2(_base_master(), sb_pos)
    m = master.set_index("player")
    assert m.loc["Alice GK", "position_v2"] == "GK"
    assert m.loc["Alice GK", "position_detail"] == "GK"
    assert m.loc["Bob Out", "position_v2"] == "CB"
    assert m.loc["Bob Out", "position_detail"] == "CB"
    # No lineup data (or no player_sb) -> Unknown.
    assert m.loc["Carol Out", "position_v2"] == "Unknown"
    assert m.loc["No Events", "position_v2"] == "Unknown"


def test_merge_position_v2_squad_mismatch_raises():
    sb_pos = _sb_positions_frame([
        {"player_id": 1, "player_name": "Alice GK", "name_variants": "Alice GK",
         "teams": "Denmark", "position_v2": "GK", "position_minutes": 90.0},
    ])
    master = _base_master()
    master.loc[0, "squad_n"] = "japan"
    with pytest.raises(AssertionError):
        b.merge_position_v2(master, sb_pos)


def test_merge_position_v2_double_attach_raises():
    sb_pos = _sb_positions_frame([
        {"player_id": 1, "player_name": "Alice GK", "name_variants": "Alice GK",
         "teams": "Denmark", "position_v2": "GK", "position_minutes": 90.0},
    ])
    master = _base_master()
    master.loc[4, "player_sb"] = "Alice GK"     # two GK rows, same name+squad
    with pytest.raises(AssertionError):
        b.merge_position_v2(master, sb_pos)


@pytest.mark.skipif(
    not (DATA_DIR / "statsbomb" / "events").is_dir()
    or not (DATA_DIR / "wc2022_players.csv").is_file()
    or not (DATA_DIR / "wc2022_standard.csv").is_file(),
    reason="requires the downloaded StatsBomb events and FBref tables under data/",
)
def test_real_dataset_217_cardinality():
    """Full pipeline keeps the 217-player cohort and attaches exactly 21 features."""
    fbref = b.merge_fbref()
    sb = b.load_statsbomb_players()
    master = b.match_fbref_to_sb(fbref, sb)
    assert len(master) == 680
    master = b.filter_minutes(master, min_90s=3.0)
    assert len(master) == 217

    sb_events = p.parse_competition(DATA_DIR / "statsbomb")
    assert len(sb_events) == 680
    assert sb_events["player_id"].nunique() == 680

    master = b.merge_statsbomb_event_features(master, sb_events)
    assert len(master) == 217, "P3/P6 merge must not change row count"
    missing = [c for c in b.P3_MASTER_COLUMNS if c not in master.columns]
    assert missing == [], f"Missing P3 columns: {missing}"
    missing_p6 = [c for c in b.P6_MASTER_COLUMNS if c not in master.columns]
    assert missing_p6 == [], f"Missing P6 columns: {missing_p6}"

    # Every eligible GK has event-derived GK activity; non-GKs are zeroed.
    gk = master["pos_n"].astype(str).str.upper() == "GK"
    assert gk.any()
    for col in b._P3_GK_COLUMNS:
        assert (master.loc[~gk, col] == 0).all(), col
    assert (master.loc[gk, "claims_p90"] >= 0).all()
    # P6 GK gating: penalty_save_pct is zero for every non-GK.
    assert (master.loc[~gk, "penalty_save_pct"] == 0).all(), \
        "penalty_save_pct not GK-gated"

    # P6: position_v2 from StatsBomb lineups (most-played position group).
    sb_positions = p.parse_lineups(DATA_DIR / "statsbomb")
    assert len(sb_positions) == 829
    master = b.merge_position_v2(master, sb_positions)
    assert len(master) == 217, "position_v2 merge must not change row count"
    vc = master["position_v2"].value_counts().to_dict()
    assert vc == {"GK": 28, "CB": 59, "FB/WB": 36, "MF": 55, "Wide": 21, "ST": 18}, vc
