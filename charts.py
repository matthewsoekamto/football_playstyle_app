import plotly.express as px
import plotly.graph_objects as go

from features import friendly_label


def build_scatter_chart(plot_df, x_axis, y_axis, x_display, y_display):
    x_mean = plot_df[x_axis].mean()
    y_mean = plot_df[y_axis].mean()
    x_std = plot_df[x_axis].std()
    y_std = plot_df[y_axis].std()

    x_z = (plot_df[x_axis] - x_mean) / (x_std if x_std > 0 else 1)
    y_z = (plot_df[y_axis] - y_mean) / (y_std if y_std > 0 else 1)
    plot_df = plot_df.copy()
    plot_df["outlier_score"] = (x_z**2 + y_z**2) ** 0.5

    clean_df = plot_df.nlargest(100, "outlier_score").copy()
    top_15_players = clean_df.nlargest(15, "outlier_score")["player"].tolist()
    clean_df["chart_label"] = clean_df["player"].where(
        clean_df["player"].isin(top_15_players),
        "",
    )

    fig = px.scatter(
        clean_df,
        x=x_axis,
        y=y_axis,
        color="Playstyle",
        text="chart_label",
        hover_data=["player", "squad", "primary_position", "Playstyle"],
        template="plotly_dark",
        labels={x_axis: x_display, y_axis: y_display},
        title=f"Elite Outlier Analysis: {x_display} vs {y_display}",
    )

    fig.add_scatter(
        x=[x_mean],
        y=[y_mean],
        mode="markers+text",
        marker=dict(size=14, color="white", symbol="star"),
        text=["Average Player"],
        textposition="bottom center",
        name="League Average",
        hoverinfo="none",
    )

    fig.update_traces(
        textposition="top center",
        textfont=dict(size=11, color="white"),
        marker=dict(size=8, opacity=0.75, line=dict(width=0)),
        selector=dict(mode="markers+text"),
    )

    return fig


def build_h2h_radar(player1, player2, valid_stats, valid_names, p1_values, p2_values):
    radar_categories = valid_names + [valid_names[0]]
    p1_closed = p1_values + [p1_values[0]]
    p2_closed = p2_values + [p2_values[0]]

    fig = go.Figure()
    fig.add_trace(
        go.Scatterpolar(
            r=p1_closed,
            theta=radar_categories,
            fill="toself",
            name=player1,
            line_color="#00d2ff",
            opacity=0.8,
        )
    )
    fig.add_trace(
        go.Scatterpolar(
            r=p2_closed,
            theta=radar_categories,
            fill="toself",
            name=player2,
            line_color="#ff007f",
            opacity=0.8,
        )
    )
    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 100],
                showticklabels=False,
                gridcolor="#444444",
            ),
            angularaxis=dict(gridcolor="#444444"),
            bgcolor="rgba(0,0,0,0)",
        ),
        template="plotly_dark",
        title=f"Percentile Footprint: {player1} vs {player2}",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.1, xanchor="center", x=0.5),
    )
    return fig


def build_playstyle_distribution_chart(profile_df):
    fig = px.bar(
        profile_df.sort_values("player_count", ascending=True),
        x="player_count",
        y="playstyle",
        orientation="h",
        text="player_count",
        template="plotly_dark",
        title="Players per Playstyle",
        labels={"player_count": "Players", "playstyle": "Playstyle"},
    )
    fig.update_traces(textposition="outside")
    return fig


def build_playstyle_radar_chart(profile_row, feature_cols):
    categories = [friendly_label(feature) for feature in feature_cols]
    values = [float(profile_row[feature]) for feature in feature_cols]
    closed_categories = categories + [categories[0]]
    closed_values = values + [values[0]]

    fig = go.Figure()
    fig.add_trace(
        go.Scatterpolar(
            r=closed_values,
            theta=closed_categories,
            fill="toself",
            name=profile_row["playstyle"],
            line_color="#00d2ff",
            opacity=0.8,
        )
    )
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, gridcolor="#444444"),
            angularaxis=dict(gridcolor="#444444"),
            bgcolor="rgba(0,0,0,0)",
        ),
        template="plotly_dark",
        title=f"Centroid Profile: {profile_row['playstyle']}",
        showlegend=False,
    )
    return fig


def build_v2_distribution_chart(dist_df):
    """Faceted horizontal bar of players per archetype, one facet per position group.

    ``dist_df`` comes from ``v2_features.build_distribution_dataframe``: one row
    per archetype (``count`` may be 0) plus a row per non-empty fallback label.
    Count-0 archetypes render as empty bars so the full taxonomy is visible; the
    caller also lists them via ``get_unrepresented_archetypes``.
    """
    fig = px.bar(
        dist_df.sort_values("count"),
        x="count",
        y="label",
        orientation="h",
        color="kind",
        facet_row="position_v2",
        facet_row_spacing=0.06,
        text="count",
        template="plotly_dark",
        title="Players per Archetype (World Cup 2022)",
        labels={"count": "Players", "label": "", "position_v2": "", "kind": ""},
        color_discrete_map={"archetype": "#00d2ff", "fallback": "#ffa15c"},
        category_orders={"position_v2": ["GK", "CB", "FB/WB", "MF", "Wide", "ST"]},
    )
    fig.update_traces(textposition="outside", cliponaxis=False)
    # Strip the "position_v2=" prefix from the facet sub-labels.
    fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
    fig.update_yaxes(matches=None)
    fig.update_layout(height=130 * dist_df["position_v2"].nunique() + 120, legend_title_text="")
    return fig


def build_v2_archetype_radar_chart(player_name, archetype_name, group, axis_labels, player_values):
    """Percentile radar: a player's position-scoped percentiles vs a 50-median ring.

    ``axis_labels`` / ``player_values`` (0-100) are precomputed by
    ``v2_features.build_player_radar_data`` so this stays a pure Plotly builder
    (no Streamlit / no v2_features import).
    """
    closed_categories = axis_labels + [axis_labels[0]]
    player_closed = player_values + [player_values[0]]
    median_closed = [50.0] * len(closed_categories)

    fig = go.Figure()
    fig.add_trace(
        go.Scatterpolar(
            r=median_closed,
            theta=closed_categories,
            fill="none",
            name="Position median (50)",
            line_color="#888888",
            line_dash="dot",
            opacity=0.7,
        )
    )
    fig.add_trace(
        go.Scatterpolar(
            r=player_closed,
            theta=closed_categories,
            fill="toself",
            name=player_name,
            line_color="#00d2ff",
            opacity=0.8,
        )
    )
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], gridcolor="#444444", showticklabels=False),
            angularaxis=dict(gridcolor="#444444"),
            bgcolor="rgba(0,0,0,0)",
        ),
        template="plotly_dark",
        title=f"{player_name} — {archetype_name} (percentile vs {group} group)",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.1, xanchor="center", x=0.5),
    )
    return fig


def build_v2_archetype_fit_chart(player_name, distances, nearest):
    """Horizontal bars of archetype fit (higher = closer) for a player's group.

    ``distances`` maps archetype name → σ-distance; the nearest is highlighted.
    """
    names = list(distances.keys())
    dists = [distances[name] for name in names]
    dmin, dmax = min(dists), max(dists)
    fits = [round(1.0 - (d - dmin) / (dmax - dmin), 3) if dmax > dmin else 1.0 for d in dists]
    colors = ["#00d2ff" if name == nearest else "#5b6472" for name in names]
    order = sorted(range(len(names)), key=lambda i: -fits[i])

    fig = go.Figure(
        go.Bar(
            x=[fits[i] for i in order],
            y=[names[i] for i in order],
            orientation="h",
            marker_color=[colors[i] for i in order],
            text=[f"{dists[i]:.1f}σ" for i in order],
            textposition="outside",
            cliponaxis=False,
        )
    )
    fig.update_layout(
        template="plotly_dark",
        title=f"Archetype fit — {player_name}",
        xaxis=dict(title="Fit (higher = closer)", range=[0, 1], showticklabels=False),
        margin=dict(l=0),
    )
    return fig
