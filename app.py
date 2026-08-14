import unicodedata

import pandas as pd
import streamlit as st

from charts import (
    build_h2h_radar,
    build_playstyle_distribution_chart,
    build_playstyle_radar_chart,
    build_scatter_chart,
    build_v2_archetype_fit_chart,
    build_v2_archetype_radar_chart,
    build_v2_distribution_chart,
)
from features import (
    EXPLORER_GK_FEATURES,
    EXPLORER_OUTFIELD_FEATURES,
    FRIENDLY_NAMES,
    add_position_percentiles,
    filter_dataframe,
    format_display_table,
    get_all_compare_stats,
    get_compare_stats_for_position,
)
from model_engine import get_cluster_profiles, get_clustered_data
from v2_features import (
    all_archetypes,
    archetype_traits,
    build_distribution_dataframe,
    build_player_radar_data,
    filter_v2_dataframe,
    format_v2_display_table,
    get_compare_stats_for_group,
    get_unrepresented_archetypes,
    load_v2_clustered_data,
    nearest_players_to_archetype,
)


def remove_accents(input_str):
    if not isinstance(input_str, str):
        return input_str
    nfkd_form = unicodedata.normalize("NFKD", input_str)
    return "".join([char for char in nfkd_form if not unicodedata.combining(char)])


def add_unique_player_labels(df):
    """Build a display/selection key that's unique per row.

    Some players appear twice (mid-season transfers between squads), so the
    raw 'player' name alone is not a safe lookup key. Only duplicated names
    get the squad suffix, so the common case still reads as a plain name.
    """
    df = df.copy()
    name_counts = df["player"].value_counts()
    duplicated_names = set(name_counts[name_counts > 1].index)

    df["player_label"] = df["player"]
    dup_mask = df["player"].isin(duplicated_names)
    df.loc[dup_mask, "player_label"] = (
        df.loc[dup_mask, "player"] + " (" + df.loc[dup_mask, "squad"].astype(str) + ")"
    )
    return df


@st.cache_data
def load_app_data(filepath):
    clustered_data = get_clustered_data(filepath)
    clustered_data = clustered_data.rename(columns={"playstyle_cluster": "Playstyle"})
    clustered_data = add_position_percentiles(clustered_data, get_all_compare_stats())
    return add_unique_player_labels(clustered_data)


def apply_search_filter(df, search_query):
    if not search_query:
        return df

    clean_query = remove_accents(search_query).lower()
    accent_free_names = df["player"].apply(remove_accents).str.lower()
    return df[accent_free_names.str.contains(clean_query, na=False)]


def render_v1_filters(clustered_data):
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        leagues = st.multiselect(
            "League", sorted(clustered_data["comp"].dropna().unique()), key="v1_league"
        )
    with c2:
        positions = st.multiselect(
            "Position", sorted(clustered_data["primary_position"].dropna().unique()), key="v1_pos"
        )
    with c3:
        squads = st.multiselect(
            "Squad", sorted(clustered_data["squad"].dropna().unique()), key="v1_squad"
        )
    with c4:
        playstyles = st.multiselect(
            "Playstyle", sorted(clustered_data["Playstyle"].dropna().unique()), key="v1_style"
        )

    return leagues, positions, squads, playstyles


def render_playstyle_explorer(filtered_df, outfield_features, gk_features):
    st.subheader("Playstyle Explorer")

    st.info(
        "ℹ️ Playstyles are clustered from goals, assists, shots, crosses, "
        "tackles, and interceptions per 90. Dribbling and progressive carrying "
        "data is not available in this dataset, which limits separation between "
        "wide attackers who cut inside and shoot vs. those who cross or carry. "
        "This will be improved when possession data is sourced."
    )

    outfield_profiles = get_cluster_profiles(
        filtered_df[filtered_df["primary_position"] != "GK"],
        outfield_features,
        playstyle_col="Playstyle",
    )
    gk_profiles = get_cluster_profiles(
        filtered_df[filtered_df["primary_position"] == "GK"],
        gk_features,
        playstyle_col="Playstyle",
    )
    profile_df = (
        pd.concat([outfield_profiles, gk_profiles], ignore_index=True)
        if not outfield_profiles.empty or not gk_profiles.empty
        else pd.DataFrame()
    )

    if profile_df.empty:
        st.info("No playstyle profiles available for the current filters.")
        return

    st.plotly_chart(
        build_playstyle_distribution_chart(profile_df),
        width="stretch",
    )

    selected_playstyle = st.selectbox(
        "Inspect a playstyle profile:",
        profile_df["playstyle"].tolist(),
    )
    selected_profile = profile_df[profile_df["playstyle"] == selected_playstyle].iloc[0]
    feature_cols = (
        gk_features
        if selected_playstyle in {"Shot-Stoppers", "Sweeper-Keepers"}
        else outfield_features
    )

    profile_col1, profile_col2 = st.columns([1, 1])
    with profile_col1:
        st.plotly_chart(
            build_playstyle_radar_chart(selected_profile, feature_cols),
            width="stretch",
        )
    with profile_col2:
        st.markdown(f"**{selected_playstyle}** — {int(selected_profile['player_count'])} players")
        st.markdown("**Representative players**")
        for player_name in selected_profile["top_players"]:
            st.markdown(f"- {player_name}")


def render_h2h_section(filtered_df):
    st.subheader("Head-to-Head Player Comparison")

    player_options = sorted(filtered_df["player_label"].dropna().unique())
    if len(player_options) < 2:
        st.info("Select a broader filter set to compare at least two players.")
        return

    default_player1 = player_options[0]
    default_player2 = player_options[1] if player_options[1] != default_player1 else player_options[min(2, len(player_options) - 1)]

    comp_col1, comp_col2 = st.columns(2)
    with comp_col1:
        player1_label = st.selectbox(
            "Select Player 1:",
            player_options,
            index=player_options.index(default_player1),
        )
    with comp_col2:
        player2_label = st.selectbox(
            "Select Player 2:",
            player_options,
            index=player_options.index(default_player2),
        )

    if not player1_label or not player2_label:
        return

    p1_data = filtered_df[filtered_df["player_label"] == player1_label].iloc[0]
    p2_data = filtered_df[filtered_df["player_label"] == player2_label].iloc[0]
    player1 = player1_label
    player2 = player2_label

    if p1_data["primary_position"] == "GK" and p2_data["primary_position"] != "GK":
        st.warning("Comparing a goalkeeper to an outfield player — percentiles use different position pools.")
    elif p2_data["primary_position"] == "GK" and p1_data["primary_position"] != "GK":
        st.warning("Comparing an outfield player to a goalkeeper — percentiles use different position pools.")

    st.markdown(
        f"#### **{player1}** ({p1_data['Playstyle']}) vs **{player2}** ({p2_data['Playstyle']})"
    )

    if p1_data["primary_position"] == p2_data["primary_position"]:
        compare_stats, stat_names = get_compare_stats_for_position(p1_data["primary_position"])
    else:
        compare_stats, stat_names = get_compare_stats_for_position("MF")

    valid_stats = [stat for stat in compare_stats if stat in p1_data.index and stat in p2_data.index]
    valid_names = [stat_names[compare_stats.index(stat)] for stat in valid_stats]

    if not valid_stats:
        st.info("Performance stats are not available for these players.")
        return

    metric_cols = st.columns(len(valid_stats))
    for index, stat in enumerate(valid_stats):
        val1 = float(p1_data[stat])
        val2 = float(p2_data[stat])
        diff = val1 - val2

        with metric_cols[index]:
            st.metric(label=valid_names[index], value=val1, delta=round(diff, 2))
            st.metric(label=f"{player2} {valid_names[index]}", value=val2, delta=round(-diff, 2))

    st.markdown("---")
    st.markdown("#### Visual Profile Breakdown (Position-Scoped Percentiles)")

    p1_values = [float(p1_data[f"{stat}_percentile"]) for stat in valid_stats]
    p2_values = [float(p2_data[f"{stat}_percentile"]) for stat in valid_stats]

    st.plotly_chart(
        build_h2h_radar(player1, player2, valid_stats, valid_names, p1_values, p2_values),
        width="stretch",
    )


def render_v2_distribution(v2_data):
    st.subheader("Archetype Distribution")

    unrepresented = get_unrepresented_archetypes(v2_data)
    dist_df = build_distribution_dataframe(v2_data)
    st.plotly_chart(build_v2_distribution_chart(dist_df), width="stretch")

    if unrepresented:
        names = ", ".join(sorted(unrepresented))
        st.info(
            "These archetypes are defined in the taxonomy but have no matching "
            f"player in the World Cup 2022 dataset: {names}."
        )


def render_v2_search(v2_data):
    st.markdown("## Find a player")
    st.caption(
        "Search any World Cup 2022 player to see their playstyle — position, "
        "archetype, and percentile profile against their position group."
    )

    query = st.text_input(
        "Search for a player",
        placeholder="e.g. Messi, Mbappé, De Bruyne…",
        label_visibility="collapsed",
        key="v2_search_player",
    )

    if query:
        matches = apply_search_filter(v2_data, query)
        if matches.empty:
            st.warning(f"No players match “{query}”.")
            return
        options = sorted(matches["player_label"].unique())
    else:
        featured = ["Lionel Messi", "Kylian Mbappé", "Kevin De Bruyne", "Jude Bellingham", "Vinícius Júnior"]
        available = [p for p in featured if p in set(v2_data["player_label"])]
        options = available or sorted(v2_data["player_label"].unique())[:5]

    selected = st.selectbox(
        "Player", options, label_visibility="collapsed", key="v2_search_select"
    )
    player_row = v2_data[v2_data["player_label"] == selected].iloc[0]
    group = player_row["position_v2"]
    radar = build_player_radar_data(v2_data, player_row, group)

    st.markdown(f"## {player_row['player_display']}")
    st.markdown(
        f"**{player_row['position_detail']}** · {player_row['squad_display']} · "
        f"*{player_row['playstyle_cluster_v2']}*"
    )

    col1, col2 = st.columns([1, 1])
    with col1:
        st.plotly_chart(
            build_v2_archetype_radar_chart(
                radar["player_name"],
                radar["reference"],
                radar["group"],
                radar["axis_labels"],
                radar["player_values"],
            ),
            width="stretch",
        )
    with col2:
        if radar["is_fallback"]:
            st.warning(
                f"Assigned label '{radar['assigned']}' is a fallback — this cluster "
                "matched no archetype within the labelling threshold. Nearest "
                f"archetype: **{radar['nearest']}**."
            )
        else:
            st.markdown(f"**Assigned archetype:** {radar['assigned']}")
        traits = archetype_traits(group, radar["reference"])
        if traits:
            summary = ", ".join(label for label, _ in traits[:6])
            st.markdown(f"*{radar['reference']}* — {summary}.")
        st.plotly_chart(
            build_v2_archetype_fit_chart(
                radar["player_name"], radar["distances"], radar["nearest"]
            ),
            width="stretch",
        )


def render_v2_players(v2_data):
    col_pos, col_squad, col_style = st.columns(3)
    with col_pos:
        positions = st.multiselect(
            "Position", sorted(v2_data["position_detail"].dropna().unique()),
            key="v2_f_pos",
        )
    with col_squad:
        squads = st.multiselect(
            "Squad", sorted(v2_data["squad_display"].dropna().unique()),
            key="v2_f_squad",
        )
    with col_style:
        playstyles = st.multiselect(
            "Playstyle", sorted(v2_data["playstyle_cluster_v2"].dropna().unique()),
            key="v2_f_style",
        )

    query = st.text_input(
        "Filter by name",
        placeholder="Search players…",
        label_visibility="collapsed",
        key="v2_players_search",
    )

    table_df = filter_v2_dataframe(
        v2_data,
        positions=positions or None,
        squads=squads or None,
        playstyles=playstyles or None,
    )
    table_df = apply_search_filter(table_df, query) if query else table_df
    table_df = table_df.sort_values("player", kind="stable").copy()
    for col in ("gls_p90", "Ast_p90"):
        if col in table_df.columns:
            table_df[col] = table_df[col].round(2)
    display_columns = [
        "player_display", "squad_display", "position_detail", "playstyle_cluster_v2",
        "gls_p90", "Ast_p90",
    ]
    st.dataframe(
        format_v2_display_table(table_df, display_columns),
        width="stretch",
        hide_index=True,
    )


def render_v2_h2h(v2_data):
    st.subheader("Head-to-Head Player Comparison")

    player_options = sorted(v2_data["player_label"].dropna().unique())
    if len(player_options) < 2:
        st.info("Select a broader filter set to compare at least two players.")
        return

    col1, col2 = st.columns(2)
    with col1:
        player1_label = st.selectbox(
            "Select Player 1:", player_options, index=0, key="v2_h2h_p1"
        )
    with col2:
        player2_label = st.selectbox(
            "Select Player 2:",
            player_options,
            index=min(1, len(player_options) - 1),
            key="v2_h2h_p2",
        )

    if not player1_label or not player2_label:
        return

    p1 = v2_data[v2_data["player_label"] == player1_label].iloc[0]
    p2 = v2_data[v2_data["player_label"] == player2_label].iloc[0]

    same_group = p1["position_v2"] == p2["position_v2"]
    if not same_group:
        st.warning(
            "These players are in different position groups — percentiles use "
            "different pools, so the raw values below are not directly comparable."
        )

    group = p1["position_v2"]
    compare_stats, stat_names = get_compare_stats_for_group(group)
    valid_stats = [stat for stat in compare_stats if stat in p1.index and stat in p2.index]
    valid_names = [stat_names[compare_stats.index(stat)] for stat in valid_stats]

    if not valid_stats:
        st.info("Performance stats are not available for these players.")
        return

    st.markdown(
        f"#### **{player1_label}** ({p1['playstyle_cluster_v2']}) vs "
        f"**{player2_label}** ({p2['playstyle_cluster_v2']})"
    )

    metric_cols = st.columns(len(valid_stats))
    for index, stat in enumerate(valid_stats):
        val1 = float(p1[stat])
        val2 = float(p2[stat])
        diff = val1 - val2
        with metric_cols[index]:
            st.metric(label=valid_names[index], value=round(val1, 2), delta=round(diff, 2))
            st.metric(
                label=f"{player2_label} {valid_names[index]}",
                value=round(val2, 2),
                delta=round(-diff, 2),
            )

    if not same_group:
        return

    st.markdown("---")
    st.markdown("#### Visual Profile Breakdown (Position-Scoped Percentiles)")

    p1_values = [float(p1[f"{stat}_percentile"]) for stat in valid_stats]
    p2_values = [float(p2[f"{stat}_percentile"]) for stat in valid_stats]

    st.plotly_chart(
        build_h2h_radar(player1_label, player2_label, valid_stats, valid_names, p1_values, p2_values),
        width="stretch",
    )


def render_v2_archetype_browser(v2_data):
    st.subheader("Archetype Reference")
    st.caption("What each of the 20 archetypes means, and who plays most like it.")

    choices = all_archetypes()
    labels = [f"{group} · {name}" for group, name in choices]
    selected = st.selectbox("Browse an archetype:", labels, key="v2_browser")
    group, name = choices[labels.index(selected)]

    traits = archetype_traits(group, name)
    if traits:
        summary = ", ".join(label for label, _ in traits)
        st.markdown(f"**{name}** — {summary}.")

    nearest = nearest_players_to_archetype(v2_data, group, name, top_n=5)
    st.markdown("**Players closest to this archetype:**")
    for row in nearest:
        st.markdown(
            f"- {row['player']} ({row['squad_display']}) — {row['playstyle_cluster_v2']}"
        )


def render_v2_view():
    try:
        with st.spinner("Loading World Cup 2022 dataset and calculating playstyles..."):
            v2_data = load_v2_clustered_data("data/wc2022_players_master.csv")
    except (FileNotFoundError, ValueError) as e:
        st.error(str(e))
        st.stop()

    tab_search, tab_players, tab_dist, tab_compare, tab_ref = st.tabs([
        "🔍 Search", "👥 Players", "📊 Distribution", "⚔️ Compare", "📚 Reference",
    ])

    with tab_search:
        render_v2_search(v2_data)
    with tab_players:
        render_v2_players(v2_data)
    with tab_dist:
        render_v2_distribution(v2_data)
    with tab_compare:
        render_v2_h2h(v2_data)
    with tab_ref:
        render_v2_archetype_browser(v2_data)


def _inject_theme_css():
    """Graphite theme polish: modern font stack + card-style metrics/dataframes."""
    st.markdown(
        """
        <style>
        .stApp {
            font-family: "Inter", "Segoe UI", -apple-system, Roboto, Helvetica, Arial, sans-serif;
        }
        [data-testid="stMetric"] {
            background-color: #1c1c1c;
            border: 1px solid #2b2b2b;
            border-radius: 10px;
            padding: 14px 16px;
        }
        [data-testid="stMetricLabel"] { color: #a3a3a3; }
        [data-testid="stDataFrame"] {
            border: 1px solid #2b2b2b;
            border-radius: 10px;
            overflow: hidden;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


st.set_page_config(page_title="Football Playstyle Explorer", layout="wide")
_inject_theme_css()

top_left, top_right = st.columns([8, 1], vertical_alignment="center")
with top_left:
    st.title("Football Playstyle Explorer")
with top_right:
    with st.popover("⚙️ Settings", use_container_width=True):
        dataset = st.radio(
            "Dataset",
            ["v2 — World Cup 2022", "v1 — Big-5 Leagues 2025/26"],
            index=0,
            key="dataset",
        )

if dataset.startswith("v2"):
    render_v2_view()
    st.stop()

try:
    with st.spinner("Loading dataset and calculating playstyles..."):
        clustered_data = load_app_data("data/players_data_light-2025_2026.csv")
except FileNotFoundError as e:
    st.error(str(e))
    st.stop()
except ValueError as e:
    st.error(str(e))
    st.stop()

leagues, positions, squads, playstyles = render_v1_filters(clustered_data)

filtered_df = filter_dataframe(
    clustered_data,
    leagues=leagues or None,
    positions=positions or None,
    squads=squads or None,
    playstyles=playstyles or None,
)

st.subheader("Search and Filter Players")
search_query = st.text_input("Type a player's name to filter the table:", "")
filtered_df = apply_search_filter(filtered_df, search_query)

display_columns = ["player", "squad", "comp", "primary_position", "Playstyle"]
for optional_stat in ["gls", "ast", "sh", "tklw", "saves", "cs"]:
    if optional_stat in filtered_df.columns:
        display_columns.append(optional_stat)

st.dataframe(
    format_display_table(
        filtered_df.sort_values("player", kind="stable"),
        display_columns,
    ),
    width="stretch",
    hide_index=True,
)

st.divider()
render_playstyle_explorer(
    filtered_df,
    EXPLORER_OUTFIELD_FEATURES,
    EXPLORER_GK_FEATURES,
)

st.divider()
st.subheader("Elite Player Scatter Plot Comparison")

available_stats = [col for col in FRIENDLY_NAMES if col in filtered_df.columns]
if len(available_stats) >= 2 and not filtered_df.empty:
    col1, col2 = st.columns(2)
    with col1:
        x_display = st.selectbox(
            "Select X-Axis Metric:",
            [FRIENDLY_NAMES[stat] for stat in available_stats],
            index=0,
        )
        x_axis = [key for key, value in FRIENDLY_NAMES.items() if value == x_display][0]
    with col2:
        y_display = st.selectbox(
            "Select Y-Axis Metric:",
            [FRIENDLY_NAMES[stat] for stat in available_stats],
            index=1,
        )
        y_axis = [key for key, value in FRIENDLY_NAMES.items() if value == y_display][0]

    st.plotly_chart(
        build_scatter_chart(filtered_df, x_axis, y_axis, x_display, y_display),
        width="stretch",
    )
else:
    st.info("Not enough performance stats available to generate a scatter plot.")

st.divider()
render_h2h_section(filtered_df)