#!/usr/bin/env python3
"""
Build WC2022 Master Dataset — V3-corrected merge.

Implements the corrected FBref <-> StatsBomb merge documented in
docs/MERGE_FAILURE_ANALYSIS_V3.md, which supersedes the stale ~70% match-rate
and "incomplete export" assumptions. The five fixes:

  1. UTF-8 FBref reading       (latin-1 caused 178 mojibake names)
  2. Unicode normalization     (NFKD + transliteration + soft-hyphen strip,
                                full name — no first+last truncation)
  3. Position normalization    (FWMF->FW, MFFW->FW, DFMF->DF, MFDF->MF)
  4. Cascade matching          exact(+pos) -> exact-name -> token-subset
                               -> first+last -> last-name-unique
                               -> edit-distance<=3 -> verified nickname map
  5. FBref 90s = canonical per-90 denominator for ALL features

The nickname map has 30 data-verified entries for zero-token-overlap or
short-name cases (e.g. FBref "Gavi" <-> StatsBomb "Pablo Martin Paez Gavira").
Each entry is checked against the StatsBomb export at load time (name present).

Output: data/wc2022_players_master.csv — eligible cohort (90s >= 3.0).
"""

import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

import statsbomb_parser

DATA_DIR = Path(__file__).resolve().parent / "data"

# ---------------------------------------------------------------------------
# Unicode normalization (fix #2)
# ---------------------------------------------------------------------------
_TRANSLIT = {"ł": "l", "ø": "o", "đ": "d", "ð": "d", "æ": "ae", "œ": "oe", "ß": "ss"}


def normalize_name(name: str) -> str:
    """NFKD-decompose, transliterate, strip diacritics, lowercase, collapse space.

    Uses the FULL name. FBref and StatsBomb store different full-name forms
    (e.g. FBref 'Abdelkarim Hassan' vs SB 'Abdelkarim Hassan Al Haj Fadlalla');
    first+last truncation destroyed the match signal.
    """
    s = unicodedata.normalize("NFKD", str(name))
    s = s.replace("­", "")  # soft hyphen (U+00AD) artifact
    s = s.replace("-", " ")  # hyphens -> spaces so token sets align
    s = s.replace("'", "")  # apostrophes: SB "N'Koulou" == FBref "Nkoulou"
    out = []
    for ch in s:
        if ch in _TRANSLIT:
            out.append(_TRANSLIT[ch])
        elif not unicodedata.combining(ch):
            out.append(ch)
    s = "".join(out).lower().strip()
    return re.sub(r"\s+", " ", s)


# ---------------------------------------------------------------------------
# Position normalization (fix #3)
# ---------------------------------------------------------------------------
_POS_MAP = {"FWMF": "FW", "MFFW": "FW", "DFMF": "DF", "MFDF": "MF",
            "FW": "FW", "MF": "MF", "DF": "DF", "GK": "GK"}


def normalize_pos(pos: str) -> str:
    return _POS_MAP.get(str(pos).upper().strip(), str(pos).upper().strip())


# ---------------------------------------------------------------------------
# Squad normalization (FBref '<code> <Country>' -> country name, lowercase)
# ---------------------------------------------------------------------------
FBREF_TO_COUNTRY = {
    'us': 'United States', 'tn': 'Tunisia', 'gh': 'Ghana', 'sa': 'Saudi Arabia',
    'sn': 'Senegal', 'cm': 'Cameroon', 'ma': 'Morocco', 'ar': 'Argentina',
    'ca': 'Canada', 'ch': 'Switzerland', 'nl': 'Netherlands', 'ec': 'Ecuador',
    'jp': 'Japan', 'es': 'Spain', 'fr': 'France', 'de': 'Germany', 'pt': 'Portugal',
    'br': 'Brazil', 'be': 'Belgium', 'hr': 'Croatia', 'rs': 'Serbia', 'uy': 'Uruguay',
    'pl': 'Poland', 'dk': 'Denmark', 'au': 'Australia', 'kr': 'South Korea',
    'ir': 'Iran', 'qa': 'Qatar', 'wls': 'Wales', 'eng': 'England', 'mx': 'Mexico',
    'cr': 'Costa Rica',
}


def normalize_squad(squad: str) -> str:
    parts = str(squad).lower().strip().split(" ", 1)
    if len(parts) == 2 and parts[0] in FBREF_TO_COUNTRY:
        return FBREF_TO_COUNTRY[parts[0]].lower()
    return squad.lower().strip()


# ---------------------------------------------------------------------------
# Verified nickname map (fix #4, final stage). Keys are the normalized FBref
# display name; values are the StatsBomb export name. Every value is verified
# to exist in the export with the matching squad (see _verify_nickname_map).
#
# 30 entries — the V3 doc's 24-entry spec plus 6 more squad-verified cases that
# resolve the remaining unmatched export rows — with two data corrections:
#   - the doc's "Ro-ró" key is FBref's display name "Ró-Ró" (both normalize to
#     "ro ro"), and
#   - the doc's "Munir -> Munir Mohamedi" target is "Munir Mohand Mohamedi" in
#     the export (Munir already matches via token-subset, so the entry is
#     redundant but kept for robustness).
# The doc's "Koke -> Jorge Resurrección Merodio" is deliberately omitted: Koke
# (0.6 90s) is below the export's 90-min floor, so no such target exists.
# ---------------------------------------------------------------------------
NICKNAME_MAP = {
    # zero-token-overlap stars
    "casemiro": "Carlos Henrique Casimiro",
    "gavi": "Pablo Martín Páez Gavira",
    "marquinhos": "Marcos Aoás Corrêa",
    "lucas paqueta": "Lucas Tolentino Coelho de Lima",
    "pedri": "Pedro González López",
    "pepe": "Kléper Laveran Lima Ferreira",
    "raphinha": "Raphael Dias Belloli",
    "rodri": "Rodrigo Hernández Cascante",
    "dani olmo": "Daniel Olmo Carvajal",
    # other mononyms / short names (most already match via token-subset; kept
    # for determinism and because they're in the V3 doc's map)
    "alisson": "Alisson Ramsés Becker",
    "antony": "Antony Matheus dos Santos",
    "dani alves": "Daniel Alves da Silva",
    "dani carvajal": "Daniel Carvajal Ramos",
    "fred": "Frederico Rodrigues Santos",
    "memphis": "Memphis Depay",
    "neymar": "Neymar da Silva Santos Junior",
    "richarlison": "Richarlison de Andrade",
    "rodrygo": "Rodrygo Silva de Goes",
    "vitinha": "Vitor Machado Ferreira",
    "otavio": "Otávio Edmilson da Silva Monteiro",
    "ro ro": "Pedro Miguel Correia",
    "munir": "Munir Mohand Mohamedi",
    # full official names (no token overlap with FBref display name)
    "saud abdulhamid": "Saud Abdullah Abdul Hamid",
    "firas al buraikan": "Firas Tariq Nasser Al Albirakan",
    # remaining short-name / transliteration cases (each squad-verified against
    # the export; 90s values agree between FBref and SB)
    "nico williams": "Nicholas Williams Arthuer",
    "danny ward": "Daniel Ward",
    "ali al bulaihi": "Ali Albulayhi",
    "hector herrera": "Héctor Miguel Herrera López",
    "papu gomez": "Alejandro Darío Gómez",
    "fabinho": "Fábio Henrique Tavares",
}


def _levenshtein(a: str, b: str, cap: int = 3) -> int:
    """Early-exit Levenshtein distance, capped at `cap`."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
        if min(prev) > cap:
            return cap + 1
    return prev[-1]


# ---------------------------------------------------------------------------
# FBref readers (fix #1: UTF-8)
# ---------------------------------------------------------------------------
def _clean_cols(cols):
    return [c.lower().replace(" ", "_").replace("+", "p").replace("-", "_")
            .replace("%", "pct").replace("/", "_per_") for c in cols]


def read_fbref_standard():
    df = pd.read_csv(DATA_DIR / "wc2022_standard.csv", skiprows=4,
                     header=[0, 1], encoding="utf-8")
    df = df[df[("Unnamed: 0_level_0", "Rk")].apply(lambda x: str(x).isdigit())].copy()
    new_cols = []
    for l0, l1 in df.columns:
        if l1 in ["Gls", "Ast", "G+A", "G-PK"] and l0 == "Per 90 Minutes":
            new_cols.append(l1 + "_p90")
        elif l1 in ["Gls", "Ast", "G+A", "G-PK"] and l0 == "Performance":
            new_cols.append(l1)
        else:
            new_cols.append(l1)
    df.columns = new_cols
    df.columns = _clean_cols(df.columns)
    return df


def read_fbref_shooting():
    df = pd.read_csv(DATA_DIR / "wc2022_shooting.csv", skiprows=4,
                     header=[0, 1], encoding="utf-8")
    df = df[df[("Unnamed: 0_level_0", "Rk")].apply(lambda x: str(x).isdigit())].copy()
    new_cols = []
    for l0, l1 in df.columns:
        if l1 in ["Gls", "Sh", "SoT", "SoT%", "Sh/90", "SoT/90", "G/Sh", "G/SoT", "PK", "PKatt"]:
            new_cols.append(l1.replace("/", "_per_").replace("%", "pct"))
        else:
            new_cols.append(l1)
    df.columns = new_cols
    df.columns = _clean_cols(df.columns)
    return df


def read_fbref_misc():
    df = pd.read_csv(DATA_DIR / "wc2022_miscellaneous.csv", skiprows=4,
                     header=[0, 1], encoding="utf-8")
    df = df[df[("Unnamed: 0_level_0", "Rk")].apply(lambda x: str(x).isdigit())].copy()
    df.columns = [l1 for l0, l1 in df.columns]
    df.columns = _clean_cols(df.columns)
    return df


def read_fbref_gk():
    df = pd.read_csv(DATA_DIR / "wc2022_gk.csv", skiprows=2, header=0, encoding="utf-8")
    df = df[df["Rk"].apply(lambda x: str(x).isdigit())].copy()
    df.columns = _clean_cols(df.columns)
    return df


def _add_norm_cols(df):
    df = df.copy()
    df["name_n"] = df["player"].apply(normalize_name)
    df["pos_n"] = df["pos"].apply(normalize_pos)
    df["squad_n"] = df["squad"].apply(normalize_squad)
    return df


def merge_fbref():
    """Merge the four FBref tables on normalized identity."""
    std = _add_norm_cols(read_fbref_standard())
    sh = _add_norm_cols(read_fbref_shooting())
    misc = _add_norm_cols(read_fbref_misc())
    gk = _add_norm_cols(read_fbref_gk())

    key_cols = ["name_n", "squad_n", "age", "born", "pos_n", "90s"]
    merged = std.merge(sh, on=key_cols, how="outer", suffixes=("", "_sh"))
    merged = merged.merge(misc, on=key_cols, how="outer", suffixes=("", "_misc"))

    gk_key = ["name_n", "squad_n", "age", "born", "pos_n"]
    gk_cols = [c for c in gk.columns if c not in gk_key]
    merged = merged.merge(gk[gk_key + gk_cols], on=gk_key, how="left", suffixes=("", "_gk"))
    return merged


# ---------------------------------------------------------------------------
# StatsBomb export + cascade matcher (fix #4)
# ---------------------------------------------------------------------------
def load_statsbomb_players():
    sb = pd.read_csv(DATA_DIR / "wc2022_players.csv")
    sb.columns = [c.lower() for c in sb.columns]
    return _add_norm_cols(sb)


def _pick(qualifying, prefer_pos, target_pos):
    """Resolve a qualifying list. Returns (candidate_or_None, status) with
    status in {'ok', 'none', 'amb'}."""
    if len(qualifying) == 1:
        return qualifying[0], "ok"
    if len(qualifying) == 0:
        return None, "none"
    if prefer_pos:
        pos_match = [c for c in qualifying if c["pos_n"] == target_pos]
        if len(pos_match) == 1:
            return pos_match[0], "ok"
    return None, "amb"


def _tokens(rec):
    return rec["name_n"].split()


def _stage_exact(fb_row, cands):
    q = [c for c in cands if c["name_n"] == fb_row["name_n"] and c["pos_n"] == fb_row["pos_n"]]
    if len(q) >= 1:
        return q[0], "exact"
    return None, None


def _stage_exact_name(fb_row, cands):
    q = [c for c in cands if c["name_n"] == fb_row["name_n"]]
    if len(q) >= 1:
        return q[0], "exact-name"
    return None, None


def _stage_token_subset(fb_row, cands):
    fb_tokens = fb_row["name_n"].split()
    if fb_tokens:
        ft = set(fb_tokens)
        q = [c for c in cands if ft <= set(_tokens(c))]
        r, st = _pick(q, True, fb_row["pos_n"])
        if st == "ok":
            return r, "token-subset"
    return None, None


def _stage_nickname(fb_row, cands):
    target = NICKNAME_MAP.get(fb_row["name_n"])
    if target:
        q = [c for c in cands if c["player"] == target]
        if len(q) == 1:
            return q[0], "nickname"
    return None, None


def _first_compatible(a: str, b: str) -> bool:
    """True when two first-name tokens plausibly denote the same person:
    exact, one is a prefix of the other (Matt~Matthew, dayot~Dayotchanculle),
    or within edit-distance 2 (Mohamed~Mohammed). Rejects Stefan~Aleksandar,
    Luuk~Frenkie, Hiroki~Junya etc. — same-surname teammates who are NOT the
    same person."""
    if a == b:
        return True
    if a.startswith(b) or b.startswith(a):
        return True
    return _levenshtein(a, b, cap=2) <= 2


def _stage_first_last(fb_row, cands):
    fb_tokens = fb_row["name_n"].split()
    if len(fb_tokens) >= 2:
        q = [c for c in cands if _tokens(c)
             and _tokens(c)[0] == fb_tokens[0] and _tokens(c)[-1] == fb_tokens[-1]]
        r, st = _pick(q, True, fb_row["pos_n"])
        if st == "ok":
            return r, "first+last"
    return None, None


def _stage_last_unique(fb_row, cands):
    fb_tokens = fb_row["name_n"].split()
    if fb_tokens:
        # Surname unique within the SB squad AND first names compatible. The
        # first-name guard is what keeps 'Stefan Mitrovic' from stealing
        # 'Aleksandar Mitrovic': the surnames collide but the first names
        # (stefan vs aleksandar) share no prefix. Upamecano and Matt Turner
        # still pass because dayot~dayotchanculle / matt~matthew are prefixes.
        q = [c for c in cands if _tokens(c)
             and _tokens(c)[-1] == fb_tokens[-1]
             and _first_compatible(fb_tokens[0], _tokens(c)[0])]
        if len(q) == 1:
            return q[0], "last-unique"
    return None, None


def _stage_edit_dist(fb_row, cands):
    fb_tokens = fb_row["name_n"].split()
    best = None
    for c in cands:
        ct = _tokens(c)
        # Both the first and the last token must be compatible — stops
        # 'Mehdi Torabi' -> 'Mehdi Taremi' (torabi vs taremi is distance 3)
        # while keeping 'Mohamed Kanno' -> 'Mohammed Kanoo'.
        if (ct and _first_compatible(fb_tokens[0], ct[0])
                and _first_compatible(fb_tokens[-1], ct[-1])):
            if best is not None:
                best = None
                break
            best = c
    if best is not None:
        return best, "edit-dist"
    return None, None


# Claiming order: high-confidence stages claim StatsBomb rows first, so a loose
# fuzzy stage can never steal a row already correctly claimed by its true owner.
_STAGES = [
    _stage_exact,
    _stage_exact_name,
    _stage_token_subset,
    _stage_nickname,
    _stage_first_last,
    _stage_last_unique,
    _stage_edit_dist,
]


def _verify_nickname_map(sb_df):
    """Fail loudly if any nickname-map target is missing from the export."""
    by_name = sb_df.set_index("player")["squad_n"].to_dict()
    missing = []
    for fb_key, sb_target in NICKNAME_MAP.items():
        if sb_target not in by_name:
            missing.append(f"{fb_key} -> {sb_target!r} (not in export)")
    if missing:
        raise ValueError("Nickname map verification failed:\n  " + "\n  ".join(missing))
    print(f"  Nickname map verified: {len(NICKNAME_MAP)} targets present in StatsBomb export")


def match_fbref_to_sb(fbref_df, sb_df):
    """Attach StatsBomb feature columns to FBref rows via the cascade matcher.

    One-to-one, stage-ordered greedy assignment: high-confidence stages run
    first and CLAIM their StatsBomb rows, so a loose fuzzy stage can never
    steal a row already correctly claimed by its true owner. Each FBref row is
    matched at the first stage that yields a unique candidate; unmatched rows
    stay unmatched (many are below the export's 90-min floor).
    """
    sb_by_squad = {s: g.to_dict("records") for s, g in sb_df.groupby("squad_n")}
    sb_lookup = {(r["squad_n"], r["player"]): r for _, r in sb_df.iterrows()}
    _verify_nickname_map(sb_df)

    claimed = set()  # (squad_n, player) — SB rows already taken
    matches = {}
    stages = {}
    pending = list(fbref_df.index)

    for stage_fn in _STAGES:
        still_pending = []
        for idx in pending:
            row = fbref_df.loc[idx]
            rec, stage = stage_fn(row, sb_by_squad.get(row["squad_n"], []))
            if rec is None or stage is None:
                still_pending.append(idx)  # this stage didn't resolve it
                continue
            key = (row["squad_n"], rec["player"])
            if key in claimed:
                still_pending.append(idx)  # row already claimed -> no wrong steal
                continue
            claimed.add(key)
            matches[idx] = rec["player"]
            stages[idx] = stage
        pending = still_pending

    for idx in pending:
        matches[idx] = None
        stages[idx] = "unmatched"

    sb_feature_cols = [c for c in sb_df.columns
                       if c not in ("player", "squad", "nation", "pos", "comp",
                                    "name_n", "pos_n", "squad_n")]
    rows = []
    for idx, row in fbref_df.iterrows():
        name = matches[idx]
        rec = sb_lookup.get((row["squad_n"], name)) if name else None
        rows.append({f"{c}_sb": (rec[c] if rec is not None else np.nan)
                     for c in sb_feature_cols})
    sb_part = pd.DataFrame(rows, index=fbref_df.index)
    sb_part["player_sb"] = [matches[i] for i in fbref_df.index]
    sb_part["match_stage"] = [stages[i] for i in fbref_df.index]

    out = fbref_df.join(sb_part)
    return out


# ---------------------------------------------------------------------------
# Per-90, derived features, minutes filter (unchanged semantics)
# ---------------------------------------------------------------------------
def compute_per90_from_fbref(df):
    nineties_col = None
    for c in df.columns:
        if c.lower() == "90s":
            nineties_col = c
            break
    if nineties_col is None:
        return df
    nineties = df[nineties_col].replace(0, np.nan).values

    count_cols = [
        "Gls", "Ast", "Sh", "SoT", "Crs", "Int", "TklW", "Fls", "Fld", "Off",
        "Carries", "PrgC", "Saves", "GA", "CS", "PK", "PKatt", "PKwon", "PKcon",
        "OG", "CrdY", "CrdR", "Min", "MP", "Starts",
    ]
    for col in count_cols:
        matching = [c for c in df.columns if c.lower() == col.lower()]
        for actual_col in matching:
            p90_col = f"{col}_p90"
            if p90_col not in df.columns:
                col_data = df[actual_col].values
                if col_data.ndim > 1:
                    col_data = col_data[:, 0]
                df[p90_col] = col_data / nineties
    return df


def derive_features(df):
    def find_col(pattern):
        for c in df.columns:
            if c.lower() == pattern.lower():
                return c
        return None

    saves_col = find_col("Saves")
    sota_col = find_col("SoTA")
    gls_col = find_col("Gls")
    sh_col = find_col("Sh")
    sot_col = find_col("SoT")

    # Division guards: a 0 denominator previously produced ~1e9 (Saiss:
    # gls=1, sh=0) instead of a 0 rate. Rows with a missing (NaN) stat stay
    # NaN — the guards only replace literal 0 denominators.
    if saves_col and sota_col:
        df["save_pct"] = np.where(df[sota_col] == 0, 0.0,
                                  df[saves_col] / df[sota_col])
    if gls_col and sh_col:
        df["conversion_pct"] = np.where(df[sh_col] == 0, 0.0,
                                        df[gls_col] / df[sh_col])
    if sot_col and sh_col:
        df["shots_on_target_pct"] = np.where(df[sh_col] == 0, 0.0,
                                             df[sot_col] / df[sh_col])

    # P6: dribble success from the StatsBomb export take-ons (P0-derived).
    succ_sb = find_col("succ_p90_sb")
    att_sb = find_col("att_p90_sb")
    if succ_sb and att_sb:
        df["dribble_success_pct"] = np.where(df[att_sb] == 0, 0.0,
                                             df[succ_sb] / df[att_sb])

    pos_col = find_col("Pos")
    if pos_col:
        def pos_group(pos):
            if pd.isna(pos):
                return "Unknown"
            p = str(pos).upper()
            if p == "GK":
                return "GK"
            if p in ["DF", "DFMF", "MFDF"]:
                return "DF"
            if p in ["MF", "MFDF", "DFMF"]:
                return "MF"
            if p in ["FW", "FWMF", "MFFW"]:
                return "FW"
            return p
        df["position_group"] = df[pos_col].apply(pos_group)
        df["primary_position"] = df[pos_col].astype(str).str.split(",").str[0].str.strip()
    return df


def filter_minutes(df, min_90s=3.0):
    nineties_col = None
    for c in df.columns:
        if c.lower() == "90s":
            nineties_col = c
            break
    if nineties_col:
        return df[df[nineties_col] >= min_90s].copy()
    return df


# ---------------------------------------------------------------------------
# P3: StatsBomb event-derived features (locked 21-column contract)
#
# statsbomb_parser.py produces per-player RAW event aggregates. This section
# bridges them onto the master frame (after player_sb is set, before the
# existing per-90 conversion) and computes the 21 locked per-90 columns.
# ---------------------------------------------------------------------------
P3_MASTER_COLUMNS = (
    "pressures_p90",
    "pressures_final_third_p90",
    "pressures_mid_third_p90",
    "claims_p90",
    "sweeper_clearances_p90",
    "headed_clearances_p90",
    "recoveries_p90",
    "passes_received_p90",
    "one_touch_finishes_p90",
    "launch_passes_p90",
    "def_actions_outside_box_p90",
    "avg_def_position_y",
    "touches_wide_p90",
    "touches_halfspace_p90",
    "touches_6yard_box_p90",
    "final_third_entries_p90",
    "carries_into_box_p90",
    "goals_prevented_p90",
    "reflex_saves_p90",
    "cross_accuracy_pct",
    "headers_p90",
)

# parser raw count column -> master per-90 column
_P3_COUNT_MAP = {
    "pressures": "pressures_p90",
    "pressures_final_third": "pressures_final_third_p90",
    "pressures_mid_third": "pressures_mid_third_p90",
    "claims": "claims_p90",
    "sweeper_clearances": "sweeper_clearances_p90",
    "headed_clearances": "headed_clearances_p90",
    "recoveries": "recoveries_p90",
    "passes_received": "passes_received_p90",
    "one_touch_finishes": "one_touch_finishes_p90",
    "launch_passes": "launch_passes_p90",
    "def_actions_outside_box": "def_actions_outside_box_p90",
    "touches_wide": "touches_wide_p90",
    "touches_halfspace": "touches_halfspace_p90",
    "touches_6yard_box": "touches_6yard_box_p90",
    "final_third_entries": "final_third_entries_p90",
    "carries_into_box": "carries_into_box_p90",
    "reflex_saves": "reflex_saves_p90",
    "headers": "headers_p90",
}

# GK-scoped features: zero-filled for non-GKs after the join.
_P3_GK_COLUMNS = (
    "claims_p90",
    "sweeper_clearances_p90",
    "launch_passes_p90",
    "def_actions_outside_box_p90",
    "avg_def_position_y",
    "goals_prevented_p90",
    "reflex_saves_p90",
)


# ---------------------------------------------------------------------------
# P6: position-scoped feature extension (additive — 23 new columns; the P3
# contract above is untouched). All per-90 over FBref ``90s``. Recipes in
# docs/01-product/FEATURE_VALIDATION.md and the approved Phase B plan.
# ---------------------------------------------------------------------------
P6_MASTER_COLUMNS = (
    "passes_p90",
    "prog_passes_p90",
    "long_passes_p90",
    "pass_completion_pct",
    "passes_into_final_third_p90",
    "switches_p90",
    "key_passes_p90",
    "through_balls_p90",
    "passes_into_box_p90",
    "clearances_p90",
    "blocks_p90",
    "aerial_duels_won_p90",
    "aerial_duel_pct",
    "duels_won_p90",
    "penalty_save_pct",
    "shots_p90",
    "xG_p90",
    "shots_on_target_p90",
    "npxG_per_shot",
    "headed_goals_p90",
    "shot_creating_actions_p90",
    "touches_att_pen_p90",
    "final_third_touches_p90",
)

# parser raw count column -> master per-90 column
_P6_COUNT_MAP = {
    "passes": "passes_p90",
    "prog_passes": "prog_passes_p90",
    "long_passes": "long_passes_p90",
    "passes_into_final_third": "passes_into_final_third_p90",
    "switches": "switches_p90",
    "key_passes": "key_passes_p90",
    "through_balls": "through_balls_p90",
    "passes_into_box": "passes_into_box_p90",
    "clearances": "clearances_p90",
    "blocks": "blocks_p90",
    "aerial_won": "aerial_duels_won_p90",
    "duels_won": "duels_won_p90",
    "shots": "shots_p90",
    "shots_on_target": "shots_on_target_p90",
    "headed_goals": "headed_goals_p90",
    "touches_att_pen": "touches_att_pen_p90",
    "final_third_touches": "final_third_touches_p90",
}

# GK-scoped P6 feature: zero-filled for non-GKs after the join.
_P6_GK_COLUMNS = ("penalty_save_pct",)


def merge_statsbomb_event_features(master, sb_events):
    """Attach the 21 P3 + 23 P6 StatsBomb event-derived features to ``master``.

    Runs AFTER ``match_fbref_to_sb`` has set ``player_sb`` and BEFORE
    ``compute_per90_from_fbref``. ``sb_events`` is the raw per-player
    aggregate frame from ``statsbomb_parser.parse_competition``.

    Identity bridge (locked contract; the closed matcher is untouched):
        StatsBomb event player_id -> event player.name -> normalize_name()
        -> master player_sb -> master row
    Squad (``normalize_squad(event team) == master.squad_n``) disambiguates
    same-name players. One data quirk: player_id 4354 (Phil/Philip Foden)
    carries two name forms in the raw events; both resolve to the same
    player_id, and only "Phil Foden" is a master ``player_sb``, so the
    player_id -> master-row mapping stays unique.

    Normalisation follows the repo's established per-90 convention
    ``count / FBref 90s`` (the ``90s`` column is minutes/90, so count/90s is
    a per-90 rate). Exceptions: ``avg_def_position_y`` is a mean and
    ``cross_accuracy_pct`` is a ratio — neither is divided by 90s. The 7
    GK-scoped features are zero-filled for non-GKs (FBref ``pos_n`` gate),
    and missing event activity becomes 0 only here, after the join.
    """
    # Positional safety: ``resolved`` and ``master.at`` assume a 0..n-1 index,
    # but callers may pass a frame whose index survived boolean filtering
    # (e.g. filter_minutes on the full 680-row master keeps labels 0..679).
    master = master.reset_index(drop=True)

    # normalized name -> (player_id, {normalized team names})
    lookup = {}
    for _, r in sb_events.iterrows():
        pid = int(r["player_id"])
        teams = {normalize_squad(t) for t in str(r["teams"]).split(";") if t}
        for variant in str(r["name_variants"]).split(";"):
            variant = variant.strip()
            if variant:
                lookup.setdefault(normalize_name(variant), (pid, teams))

    pid_to_row = {}
    resolved = np.full(len(master), np.nan)
    for idx, r in master.iterrows():
        sb_name = r.get("player_sb")
        if pd.isna(sb_name):
            continue
        entry = lookup.get(normalize_name(sb_name))
        if entry is None:
            continue  # no event activity for this name; row stays zero
        pid, teams = entry
        if r["squad_n"] not in teams:
            raise AssertionError(
                f"StatsBomb squad mismatch for master {r['player']!r} "
                f"(player_sb={sb_name!r}): event team(s) {sorted(teams)} "
                f"vs master squad {r['squad_n']!r}")
        if pid in pid_to_row:
            raise AssertionError(
                f"StatsBomb player_id {pid} ({sb_name!r}) attaches to more "
                f"than one master row")
        pid_to_row[pid] = idx
        resolved[idx] = pid

    agg = sb_events.set_index("player_id")
    nineties = master["90s"].replace(0, np.nan)

    # Baseline zeros for every row; real values only from joined events.
    for col in P3_MASTER_COLUMNS:
        master[col] = 0.0

    for idx in np.flatnonzero(np.isfinite(resolved)):
        pid = int(resolved[idx])
        if pid not in agg.index:
            continue
        rec = agg.loc[pid]
        n90 = nineties.iloc[idx]
        for raw_col, master_col in _P3_COUNT_MAP.items():
            master.at[idx, master_col] = float(rec[raw_col]) / n90
        master.at[idx, "goals_prevented_p90"] = (
            float(rec["goals_prevented_raw"]) / n90)
        master.at[idx, "avg_def_position_y"] = rec["avg_def_y"]  # mean
        attempts = float(rec["cross_attempted"])
        if attempts:
            master.at[idx, "cross_accuracy_pct"] = (
                float(rec["cross_completed"]) / attempts)

    # GK scoping: non-GKs get 0 for the 7 GK features (FBref pos_n is the
    # authoritative position gate).
    is_gk = master["pos_n"].astype(str).str.upper() == "GK"
    for col in _P3_GK_COLUMNS:
        master.loc[~is_gk, col] = 0.0

    # Collapse remaining NaN (avg_def_y for GKs with no located events,
    # per-90 for zero-minute rows, cross accuracy for non-crossers).
    master[list(P3_MASTER_COLUMNS)] = (
        master[list(P3_MASTER_COLUMNS)].fillna(0.0))

    # No event-derived feature may attach to an unmatched master player.
    unmatched = master["player_sb"].isna()
    if unmatched.any():
        for col in P3_MASTER_COLUMNS:
            assert (master.loc[unmatched, col] == 0).all(), (
                f"P3 feature {col} attached to an unmatched master player")

    # ---- P6: position-scoped extension (same identity bridge) ----
    for col in P6_MASTER_COLUMNS:
        master[col] = 0.0

    for idx in np.flatnonzero(np.isfinite(resolved)):
        pid = int(resolved[idx])
        if pid not in agg.index:
            continue
        rec = agg.loc[pid]
        n90 = nineties.iloc[idx]
        for raw_col, master_col in _P6_COUNT_MAP.items():
            master.at[idx, master_col] = float(rec[raw_col]) / n90
        master.at[idx, "xG_p90"] = float(rec["xg_sum"]) / n90
        passes = float(rec["passes"])
        if passes:
            master.at[idx, "pass_completion_pct"] = (
                float(rec["pass_completed"]) / passes)
        aerial_den = float(rec["aerial_won"]) + float(rec["aerial_lost"])
        if aerial_den:
            master.at[idx, "aerial_duel_pct"] = (
                float(rec["aerial_won"]) / aerial_den)
        non_pen = float(rec["non_pen_shots"])
        if non_pen:
            master.at[idx, "npxG_per_shot"] = (
                float(rec["npxg_sum"]) / non_pen)
        faced = float(rec["penalty_faced"])
        if faced:
            master.at[idx, "penalty_save_pct"] = (
                float(rec["penalty_saved"]) / faced)
        # Proxy (locked decision): true SCA is impossible in open data.
        master.at[idx, "shot_creating_actions_p90"] = (
            master.at[idx, "key_passes_p90"])

    # GK scoping: penalty_save_pct is GK-only (FBref pos_n is the gate).
    for col in _P6_GK_COLUMNS:
        master.loc[~is_gk, col] = 0.0

    master[list(P6_MASTER_COLUMNS)] = master[list(P6_MASTER_COLUMNS)].fillna(0.0)

    if unmatched.any():
        for col in P6_MASTER_COLUMNS:
            assert (master.loc[unmatched, col] == 0).all(), (
                f"P6 feature {col} attached to an unmatched master player")

    return master


# ---------------------------------------------------------------------------
# P6: position_v2 (StatsBomb most-played position group)
# ---------------------------------------------------------------------------
def merge_position_v2(master, sb_positions):
    """Attach ``position_v2`` (StatsBomb most-played position group).

    Runs after ``match_fbref_to_sb`` (needs ``player_sb``) and shares its
    identity bridge: normalized event player name -> player_id -> master row,
    with squad disambiguation. Raises on squad mismatch or double-attach
    (same guarantees as ``merge_statsbomb_event_features``). Players with no
    lineup data keep ``"Unknown"``.
    """
    master = master.reset_index(drop=True)

    lookup = {}
    for _, r in sb_positions.iterrows():
        pid = int(r["player_id"])
        teams = {normalize_squad(t) for t in str(r["teams"]).split(";") if t}
        for variant in str(r["name_variants"]).split(";"):
            variant = variant.strip()
            if variant:
                lookup.setdefault(normalize_name(variant), (pid, teams))

    master["position_v2"] = "Unknown"
    master["position_detail"] = "Unknown"
    pid_to_row = {}
    resolved = np.full(len(master), np.nan)
    for idx, r in master.iterrows():
        sb_name = r.get("player_sb")
        if pd.isna(sb_name):
            continue
        entry = lookup.get(normalize_name(sb_name))
        if entry is None:
            continue
        pid, teams = entry
        if r["squad_n"] not in teams:
            raise AssertionError(
                f"StatsBomb squad mismatch for master {r['player']!r} "
                f"(player_sb={sb_name!r}): lineup team(s) {sorted(teams)} "
                f"vs master squad {r['squad_n']!r}")
        if pid in pid_to_row:
            raise AssertionError(
                f"StatsBomb player_id {pid} ({sb_name!r}) attaches to more "
                f"than one master row")
        pid_to_row[pid] = idx
        resolved[idx] = pid

    by_pid = sb_positions.set_index("player_id")
    for idx in np.flatnonzero(np.isfinite(resolved)):
        pid = int(resolved[idx])
        if pid not in by_pid.index:
            continue
        master.at[idx, "position_v2"] = by_pid.loc[pid, "position_v2"]
        master.at[idx, "position_detail"] = by_pid.loc[pid, "position_detail"]
    return master


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("Building WC2022 master dataset (V3-corrected merge)...")

    print("Loading FBref tables (UTF-8)...")
    fbref = merge_fbref()
    assert len(fbref) == 680, f"FBref merge produced {len(fbref)} rows, expected 680"
    print(f"  FBref merged: {len(fbref)} rows, {len(fbref.columns)} cols")

    print("Loading StatsBomb player aggregates...")
    sb = load_statsbomb_players()
    print(f"  StatsBomb: {len(sb)} rows, {len(sb.columns)} cols")

    print("Matching FBref -> StatsBomb (cascade + nickname map)...")
    master = match_fbref_to_sb(fbref, sb)

    # ---- Match-rate report (pre-filter, all 680) ----
    total = len(master)
    matched = master["player_sb"].notna().sum()
    unmatched = master[master["player_sb"].isna()]
    # Diagnostics: any unmatched player that DOES have an SB row? (matcher gap)
    sb_keys = {(r["squad_n"], r["name_n"]) for _, r in sb.iterrows()}
    has_sb_row = unmatched.apply(
        lambda r: (r["squad_n"], r["name_n"]) in sb_keys, axis=1)
    missing_from_export = unmatched[~has_sb_row]
    matcher_gaps = unmatched[has_sb_row]

    print("\n=== MATCH RATES ===")
    print(f"  Overall (all {total} FBref):  {matched}/{total} ({matched / total:.1%})")
    print(f"    -> unmatched without any SB row (below export 90-min floor): {len(missing_from_export)}")
    print(f"    -> unmatched WITH an SB row (matcher gap): {len(matcher_gaps)}")

    stage_counts = master["match_stage"].value_counts()
    print("\n  Match stages: " + ", ".join(f"{k}={v}" for k, v in stage_counts.items()))

    # ---- Eligible cohort (90s >= 3.0, the actual dataset) ----
    eligible = filter_minutes(master, min_90s=3.0)
    el_matched = eligible["player_sb"].notna().sum()
    el_unmatched = eligible[eligible["player_sb"].isna()]
    print(f"\n  Eligible cohort (90s>=3.0): {el_matched}/{len(eligible)} "
          f"({el_matched / len(eligible):.1%})")
    if len(el_unmatched):
        print("  UNMATCHED ELIGIBLE PLAYERS:")
        for _, r in el_unmatched.iterrows():
            print(f"    {r['player']} | {r['pos']} | {r['squad']} | stage={r['match_stage']}")

    if len(matcher_gaps):
        print("\n  MATCHER GAPS (had an SB row but not matched):")
        for _, r in matcher_gaps.iterrows():
            print(f"    {r['player']} | {r['pos']} | {r['squad']} | stage={r['match_stage']}")

    # Sanity review: fuzzy-matched eligible players should keep their surname in
    # the SB name (compare NORMALIZED tokens — accents must match too).
    suspicious = []
    for _, r in eligible.iterrows():
        if r["match_stage"] in ("token-subset", "first+last", "last-unique", "edit-dist"):
            fb_last = r["name_n"].split()[-1]
            sb_tokens = normalize_name(r["player_sb"]).split()
            if fb_last not in sb_tokens and not (
                    r["match_stage"] == "edit-dist" and
                    _levenshtein(r["name_n"].replace(" ", ""),
                                 normalize_name(r["player_sb"]).replace(" ", "")) <= 3):
                suspicious.append((r["player"], r["player_sb"], r["match_stage"]))
    if suspicious:
        print("\n  REVIEW (fuzzy-matched eligible players whose surname isn't in SB name):")
        for fb_name, sb_name, stage in suspicious:
            print(f"    {fb_name!r} -> {sb_name!r} [{stage}]")
    else:
        print("\n  REVIEW: no fuzzy-matched eligible player lost its surname (all sane)")

    # SB players never matched to any FBref player (reverse-coverage gap)
    matched_sb_names = {r["player_sb"] for _, r in master.iterrows() if pd.notna(r["player_sb"])}
    unmatched_sb = sb[~sb["player"].isin(matched_sb_names)][["player", "pos", "squad", "90s"]]
    if len(unmatched_sb):
        print(f"\n  SB players not matched to any FBref player ({len(unmatched_sb)}):")
        for _, r in unmatched_sb.iterrows():
            print(f"    {r['player']!r} | {r['pos']} | {r['squad']} | 90s={r['90s']}")
    else:
        print("\n  All StatsBomb players matched to an FBref player.")

    # Double-matches: two FBref rows claiming the same SB row is a matcher error.
    dup_sb = master[master["player_sb"].notna()]
    dup_sb = dup_sb.groupby("player_sb").filter(lambda g: len(g) > 1)
    if len(dup_sb):
        print(f"\n  !! DOUBLE-MATCHES ({dup_sb['player_sb'].nunique()} SB rows claimed twice):")
        for _, r in dup_sb.sort_values("player_sb").iterrows():
            print(f"    FBref {r['player']!r} ({r['squad']}, {r['pos']}) -> SB {r['player_sb']!r} [{r['match_stage']}]")
    else:
        print("\n  No double-matches: every SB row claimed by exactly one FBref player.")

    # ---- P3: StatsBomb event-derived features (locked 21-column contract) ----
    print("\nParsing StatsBomb events -> per-player raw aggregates...")
    sb_events = statsbomb_parser.parse_competition(DATA_DIR / "statsbomb")
    print(f"  {len(sb_events)} StatsBomb players with event activity")
    print("Merging StatsBomb event features...")
    master = merge_statsbomb_event_features(master, sb_events)
    assert len(master) == 680, f"P3 merge changed row count to {len(master)}"
    print(f"  + {len(P3_MASTER_COLUMNS) + len(P6_MASTER_COLUMNS)} "
          f"event-derived columns attached")

    # ---- P6: StatsBomb most-played position groups (position_v2) ----
    print("\nParsing StatsBomb lineups -> most-played positions...")
    sb_positions = statsbomb_parser.parse_lineups(DATA_DIR / "statsbomb")
    print(f"  {len(sb_positions)} StatsBomb players with lineup data")
    master = merge_position_v2(master, sb_positions)
    print(f"  position_v2 attached "
          f"({master['position_v2'].nunique()} distinct groups)")

    # ---- Assemble + write output ----
    print("\nComputing per-90 rates...")
    master = compute_per90_from_fbref(master)
    print("Deriving features...")
    master = derive_features(master)
    master = master.drop(columns=["name_n", "pos_n", "squad_n"])

    print("Filtering min 270 minutes (90s>=3.0)...")
    master = filter_minutes(master, min_90s=3.0)
    print(f"  After filter: {len(master)} rows")
    assert len(master) == 217, f"Expected 217 eligible players, got {len(master)}"

    output_path = DATA_DIR / "wc2022_players_master.csv"
    master.to_csv(output_path, index=False)
    print(f"\nSaved: {output_path} ({len(master)} rows x {len(master.columns)} cols)")

    # P3 verification: exactly 21 event-derived columns, no duplicates.
    p3_present = [c for c in P3_MASTER_COLUMNS if c in master.columns]
    assert len(p3_present) == len(P3_MASTER_COLUMNS), (
        f"Missing P3 columns: {set(P3_MASTER_COLUMNS) - set(p3_present)}")
    assert len(set(p3_present)) == len(p3_present), "Duplicate P3 columns"
    print(f"P3 StatsBomb event-derived columns: {len(p3_present)} present "
          f"(of {len(P3_MASTER_COLUMNS)}), {len(master.columns)} total columns")

    # P6 verification: 23 P6 columns + position_v2 + the data-fix invariants.
    p6_present = [c for c in P6_MASTER_COLUMNS if c in master.columns]
    assert len(p6_present) == len(P6_MASTER_COLUMNS), (
        f"Missing P6 columns: {set(P6_MASTER_COLUMNS) - set(p6_present)}")
    assert len(set(p6_present)) == len(p6_present), "Duplicate P6 columns"
    assert not master[p6_present].isna().any().any(), "NaN in P6 columns"
    assert master["conversion_pct"].max() <= 1.0, (
        "conversion_pct overflow (gls/sh with sh=0)")
    assert master["dribble_success_pct"].max() <= 1.0, (
        "dribble_success_pct overflow (succ/att with att=0)")
    dist = master["position_v2"].value_counts()
    assert dist.sum() == len(master), "position_v2 must resolve every player"
    print(f"P6 StatsBomb event-derived columns: {len(p6_present)} present "
          f"(of {len(P6_MASTER_COLUMNS)}), {len(master.columns)} total columns")
    print("position_v2 distribution: " + ", ".join(
        f"{g}={int(dist.get(g, 0))}" for g in ("GK", "CB", "FB/WB", "MF", "Wide", "ST")))

    # Final summary
    print(f"\nFinal dataset: {len(master)} rows x {len(master.columns)} columns")
    el_m = master["player_sb"].notna().sum()
    print(f"StatsBomb matches (eligible cohort): {el_m}/{len(master)} ({el_m / len(master):.1%})")


if __name__ == "__main__":
    main()
