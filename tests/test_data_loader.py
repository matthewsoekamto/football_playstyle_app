"""Tests for data_loader.py — CSV ingestion, cleaning, and per-90 derivation."""
import pandas as pd

from data_loader import _add_per90_rates, load_and_clean_data


class TestLoadAndCleanData:
    """Structural properties of the data-loading pipeline."""

    def test_minutes_filter(self, fixture_csv_path):
        """Rows below Min=270 are excluded; rows at/above 270 are kept."""
        df = load_and_clean_data(fixture_csv_path)
        assert df["min"].min() >= 270, "Found rows below Min >= 270 filter"
        # The fixture has Frank Fodder at Min=100 and Grace Boundary at Min=270
        assert "Frank Fodder" not in df["player"].values, (
            "Frank Fodder (Min=100) should have been filtered out"
        )
        assert "Grace Boundary" in df["player"].values, (
            "Grace Boundary (Min=270) should be included"
        )

    def test_column_normalization(self, fixture_csv_path):
        """Column names are stripped, lowercased, and spaces/dashes replaced."""
        df = load_and_clean_data(fixture_csv_path)
        raw_cols = set(df.columns)
        # Should NOT contain raw FBref-style names
        assert "Rk" not in raw_cols, "Raw column 'Rk' survived normalization"
        assert "Player" not in raw_cols, "Raw column 'Player' survived normalization"
        # Should contain normalized names
        assert "player" in raw_cols, "Normalized 'player' column missing"
        assert "rk" in raw_cols, "Normalized 'rk' column present"
        assert "90s" in raw_cols, "'90s' column missing"

    def test_primary_position_derivation(self, fixture_csv_path):
        """primary_position takes the first token of a comma-separated Pos."""
        df = load_and_clean_data(fixture_csv_path)
        eve = df[df["player"] == "Eve Winger"].iloc[0]
        assert eve["primary_position"] == "MF", (
            f"Eve Winger (Pos='MF,FW') should get primary_position='MF', "
            f"got '{eve['primary_position']}'"
        )

    def test_gk_position_preserved(self, fixture_csv_path):
        """Goalkeepers get primary_position='GK'."""
        df = load_and_clean_data(fixture_csv_path)
        alice = df[df["player"] == "Alice Keeper"].iloc[0]
        assert alice["primary_position"] == "GK"

    def test_row_count_after_filter(self, fixture_csv_path):
        """Only fixture rows with Min >= 270 survive."""
        df = load_and_clean_data(fixture_csv_path)
        # Fixture: 12 rows total, 1 below threshold (Frank, Min=100)
        assert len(df) == 11, (
            f"Expected 11 rows after Min>=270 filter, got {len(df)}"
        )


class TestAddPer90Rates:
    """Unit behaviour of the per-90 rate computation."""

    def test_basic_computation(self):
        """A player with Gls=9 and 90s=27.2 gets gls_p90 ≈ 0.331."""
        df = pd.DataFrame({"gls": [9, 0], "90s": [27.2, 10.0]})
        result = _add_per90_rates(df, ["gls"])
        expected = 9 / 27.2
        assert abs(result["gls_p90"].iloc[0] - expected) < 0.001, (
            f"Expected gls_p90 ≈ {expected:.3f}, "
            f"got {result['gls_p90'].iloc[0]:.3f}"
        )

    def test_zero_90s_guard(self):
        """A player with 90s=0 gets gls_p90=0, not inf or NaN."""
        df = pd.DataFrame({"gls": [5], "90s": [0]})
        result = _add_per90_rates(df, ["gls"])
        assert result["gls_p90"].iloc[0] == 0.0, (
            f"Expected gls_p90=0 for 90s=0, got {result['gls_p90'].iloc[0]}"
        )

    def test_missing_source_column(self):
        """_add_per90_rates silently skips a stat not in df.columns."""
        df = pd.DataFrame({"gls": [5], "90s": [10.0]})
        result = _add_per90_rates(df, ["gls", "nonexistent_stat"])
        assert "gls_p90" in result.columns, "Existing stat should produce _p90"
        assert "nonexistent_stat_p90" not in result.columns, (
            "Missing stat should not create a _p90 column"
        )

    def test_missing_90s_column(self):
        """_add_per90_rates returns df unchanged if '90s' column is absent."""
        df = pd.DataFrame({"gls": [5]})
        result = _add_per90_rates(df, ["gls"])
        assert "gls_p90" not in result.columns
        assert len(result) == 1
