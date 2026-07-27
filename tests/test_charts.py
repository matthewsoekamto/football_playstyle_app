"""Smoke tests for charts.py — each build_* function returns a Figure."""
import pandas as pd
import plotly.graph_objects as go
import pytest

from charts import (
    build_h2h_radar,
    build_playstyle_distribution_chart,
    build_playstyle_radar_chart,
    build_scatter_chart,
)


class TestChartReturnTypes:
    """Every chart builder returns a Plotly Figure instance.

    These are smoke tests — they verify the function runs without raising
    and returns the correct type, not the visual correctness of the output.
    """

    def test_scatter_chart_returns_figure(self, cleaned_fixture_df):
        """build_scatter_chart returns a Figure with valid data."""
        available = [c for c in ["gls_p90", "ast_p90", "sh_p90"]
                     if c in cleaned_fixture_df.columns]
        if len(available) < 2:
            pytest.skip("Not enough numeric columns for scatter chart")
        fig = build_scatter_chart(
            cleaned_fixture_df,
            available[0], available[1],
            "Goals per 90", "Assists per 90",
        )
        assert isinstance(fig, go.Figure)

    def test_h2h_radar_returns_figure(self):
        """build_h2h_radar returns a Figure with correct structure."""
        fig = build_h2h_radar(
            player1="Player A",
            player2="Player B",
            valid_stats=["gls", "ast", "sh"],
            valid_names=["Goals", "Assists", "Shots"],
            p1_values=[80, 60, 90],
            p2_values=[70, 75, 50],
        )
        assert isinstance(fig, go.Figure)
        # Should have 2 traces (one per player)
        assert len(fig.data) == 2

    def test_playstyle_distribution_returns_figure(self):
        """build_playstyle_distribution_chart returns a Figure."""
        profile_df = pd.DataFrame({
            "playstyle": ["Type A", "Type B"],
            "player_count": [10, 20],
        })
        fig = build_playstyle_distribution_chart(profile_df)
        assert isinstance(fig, go.Figure)

    def test_playstyle_radar_returns_figure(self):
        """build_playstyle_radar_chart returns a Figure with closed radar."""
        profile_row = pd.Series({
            "playstyle": "Test Style",
            "gls_p90": 0.5,
            "ast_p90": 0.3,
        })
        fig = build_playstyle_radar_chart(
            profile_row, ["gls_p90", "ast_p90"],
        )
        assert isinstance(fig, go.Figure)
        # Radar trace should have closed circle: first category repeated at end
        trace = fig.data[0]
        assert len(trace.theta) == 3, (
            f"Expected 3 theta values (2 categories + closing), "
            f"got {len(trace.theta)}"
        )
        assert trace.theta[0] == trace.theta[-1], (
            "Radar categories not closed (first != last)"
        )
