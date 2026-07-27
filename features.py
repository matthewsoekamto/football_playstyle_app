
FRIENDLY_NAMES = {
    "gls": "Goals",
    "ast": "Assists",
    "sh": "Shots",
    "sot": "Shots on Target",
    "crs": "Crosses",
    "tklw": "Tackles Won",
    "int": "Interceptions",
    "fls": "Fouls Committed",
    "saves": "Saves",
    "save%": "Save Percentage",
    "cs": "Clean Sheets",
    "ga90": "Goals Against per 90",
    "gls_p90": "Goals per 90",
    "ast_p90": "Assists per 90",
    "sh_p90": "Shots per 90",
    "crs_p90": "Crosses per 90",
    "tklw_p90": "Tackles Won per 90",
    "int_p90": "Interceptions per 90",
}

DISPLAY_COLUMN_LABELS = {
    "player": "Player",
    "squad": "Squad",
    "comp": "League",
    "primary_position": "Position",
    "Playstyle": "Playstyle",
    **FRIENDLY_NAMES,
}

POSITION_COMPARE_STATS = {
    "GK": (
        ["saves", "save%", "cs", "ga90", "int"],
        ["Saves", "Save %", "Clean Sheets", "Goals Against/90", "Interceptions"],
    ),
    "FW": (
        ["gls", "ast", "sh", "sot", "crs"],
        ["Goals", "Assists", "Shots", "Shots on Target", "Crosses"],
    ),
    "MF": (
        ["gls", "ast", "sh", "crs", "tklw", "int"],
        ["Goals", "Assists", "Shots", "Crosses", "Tackles Won", "Interceptions"],
    ),
    "DF": (
        ["tklw", "int", "crs", "ast", "sh"],
        ["Tackles Won", "Interceptions", "Crosses", "Assists", "Shots"],
    ),
}

EXPLORER_OUTFIELD_FEATURES = [
    "gls_p90",
    "ast_p90",
    "sh_p90",
    "crs_p90",
    "tklw_p90",
    "int_p90",
]
EXPLORER_GK_FEATURES = ["saves_p90", "save%", "cs_p90", "int_p90"]


def add_position_percentiles(df, stats):
    df = df.copy()
    available_stats = [stat for stat in stats if stat in df.columns]

    for stat in available_stats:
        percentile_col = f"{stat}_percentile"
        df[percentile_col] = 0.0
        for position in df["primary_position"].dropna().unique():
            position_mask = df["primary_position"] == position
            df.loc[position_mask, percentile_col] = (
                df.loc[position_mask, stat].fillna(0).rank(pct=True) * 100
            )

    return df


def get_compare_stats_for_position(position):
    if position in POSITION_COMPARE_STATS:
        return POSITION_COMPARE_STATS[position]
    return POSITION_COMPARE_STATS["MF"]


def get_all_compare_stats():
    stats = set()
    for compare_stats, _ in POSITION_COMPARE_STATS.values():
        stats.update(compare_stats)
    return sorted(stats)


def filter_dataframe(df, leagues=None, positions=None, squads=None, playstyles=None, search_query=None):
    filtered = df.copy()

    if leagues:
        filtered = filtered[filtered["comp"].isin(leagues)]
    if positions:
        filtered = filtered[filtered["primary_position"].isin(positions)]
    if squads:
        filtered = filtered[filtered["squad"].isin(squads)]
    if playstyles:
        filtered = filtered[filtered["Playstyle"].isin(playstyles)]

    return filtered


def friendly_label(stat_key):
    return FRIENDLY_NAMES.get(stat_key, stat_key)


def format_display_table(df, columns):
    display_df = df[columns].copy().reset_index(drop=True)
    display_df.insert(0, "#", range(1, len(display_df) + 1))
    rename_map = {
        column: DISPLAY_COLUMN_LABELS.get(column, column.replace("_", " ").title())
        for column in columns
    }
    return display_df.rename(columns=rename_map)
