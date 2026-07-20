"""Tests for features.py — filtering, percentiles, display formatting."""
import pandas as pd
from features import (
    filter_dataframe,
    format_display_table,
    friendly_label,
    get_compare_stats_for_position,
)


class TestFilterDataframe:
    """Each filter dimension produces the expected subset."""

    def test_no_filters_returns_all(self, cleaned_fixture_df):
        """Passing no filters returns the full DataFrame unchanged."""
        result = filter_dataframe(cleaned_fixture_df)
        assert len(result) == len(cleaned_fixture_df)

    def test_filter_by_league(self, cleaned_fixture_df):
        """Filtering by league returns only rows for that league."""
        result = filter_dataframe(
            cleaned_fixture_df, leagues=["eng Premier League"],
        )
        non_matching = result[result["comp"] != "eng Premier League"]
        assert len(non_matching) == 0

    def test_filter_by_position(self, cleaned_fixture_df):
        """Filtering by position returns only rows with that primary_position."""
        result = filter_dataframe(cleaned_fixture_df, positions=["GK"])
        non_matching = result[result["primary_position"] != "GK"]
        assert len(non_matching) == 0
        assert len(result) > 0, "Expected at least 1 GK row"

    def test_filter_by_playstyle(self, cleaned_fixture_df):
        """Filtering by playstyle returns only rows with that label."""
        playstyles = cleaned_fixture_df["Playstyle"].unique().tolist()
        if playstyles:
            target = playstyles[0]
            result = filter_dataframe(
                cleaned_fixture_df, playstyles=[target],
            )
            non_matching = result[result["Playstyle"] != target]
            assert len(non_matching) == 0


class TestFormatDisplayTable:
    """Display-table formatting conventions."""

    def test_hash_column_present(self):
        """format_display_table adds a '#' column starting at 1."""
        df = pd.DataFrame({"player": ["A", "B"], "squad": ["X", "Y"]})
        result = format_display_table(df, ["player", "squad"])
        assert "#" in result.columns, "Missing '#' column"
        assert result["#"].tolist() == [1, 2], (
            f"Expected [#1, #2], got {result['#'].tolist()}"
        )

    def test_column_renaming(self):
        """Raw column names are replaced with DISPLAY_COLUMN_LABELS entries."""
        df = pd.DataFrame({"player": ["A"], "squad": ["X"]})
        result = format_display_table(df, ["player", "squad"])
        assert "Player" in result.columns, "Column should be renamed 'Player'"
        assert "Squad" in result.columns, "Column should be renamed 'Squad'"


class TestFriendlyLabel:
    """Label lookup for user-facing stat names."""

    def test_known_stat(self):
        assert friendly_label("gls_p90") == "Goals per 90"

    def test_unknown_stat_fallback(self):
        """Unknown keys fall back to the key itself."""
        assert friendly_label("some_unknown_stat") == "some_unknown_stat"


class TestGetCompareStatsForPosition:
    """Position-scoped stat sets."""

    def test_known_position(self):
        stats, names = get_compare_stats_for_position("FW")
        assert "gls" in stats
        assert "Goals" in names

    def test_unknown_position_fallback(self):
        """Unrecognized positions fall back to MF stat set."""
        stats, _ = get_compare_stats_for_position("UNKNOWN")
        assert "gls" in stats
        assert "tklw" in stats
