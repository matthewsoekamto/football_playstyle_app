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
