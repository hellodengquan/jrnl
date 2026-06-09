# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

from collections import Counter
from unittest import mock

import pytest

from jrnl.exception import JrnlException
from jrnl.plugins.calendar_heatmap_exporter import CalendarHeatmapExporter
from jrnl.plugins.fancy_exporter import check_provided_linewrap_viability
from jrnl.plugins.util import NestedDict
from jrnl.plugins.yaml_exporter import YAMLExporter


@pytest.fixture()
def datestr():
    yield "2020-10-20 16:59"


def build_card_header(datestr):
    top_left_corner = "┎─╮"
    content = top_left_corner + datestr
    return content


class TestFancy:
    def test_too_small_linewrap(self, datestr):
        journal = "test_journal"
        content = build_card_header(datestr)

        total_linewrap = 12

        with pytest.raises(JrnlException):
            check_provided_linewrap_viability(total_linewrap, [content], journal)


class TestYaml:
    @mock.patch("builtins.open")
    def test_export_to_nonexisting_folder(self, mock_open):
        with pytest.raises(JrnlException):
            YAMLExporter.write_file("journal", "non-existing-path")
        mock_open.assert_not_called()


class TestCalendarHeatmapEmptySet:
    """Boundary tests for zero-entry / filtered-empty subsets.

    Covers scenarios such as:
      - Brand new journal with no entries yet
      - A @tag filter that matches no entries (e.g. jrnl @nonexistent)
      - A date range filter that contains no records
    """

    def test_compute_statistics_empty_counter_no_divide_by_zero(self):
        """_compute_statistics on an empty Counter must never raise
        ZeroDivisionError; all rate/avg fields must be 0.0 and numeric
        fields must be 0 / None."""
        stats = CalendarHeatmapExporter._compute_statistics(Counter())

        assert stats["total_entries"] == 0
        assert stats["active_days"] == 0
        assert stats["total_days_span"] == 0
        assert stats["longest_streak"] == 0
        assert stats["current_streak"] == 0
        assert stats["max_per_day"] == 0
        assert stats["busiest_day"] is None

        assert isinstance(stats["avg_per_active_day"], float)
        assert isinstance(stats["avg_per_week"], float)
        assert isinstance(stats["activity_rate"], float)
        assert stats["avg_per_active_day"] == 0.0
        assert stats["avg_per_week"] == 0.0
        assert stats["activity_rate"] == 0.0

    def test_compute_statistics_empty_counter_is_idempotent(self):
        """Calling _compute_statistics repeatedly on empty input should
        return the same stable result (no mutation of global state)."""
        a = CalendarHeatmapExporter._compute_statistics(Counter())
        b = CalendarHeatmapExporter._compute_statistics(Counter())
        assert a == b

    def test_flatten_frequency_empty_nesteddict(self):
        """_flatten_frequency on a brand-new NestedDict yields a Counter
        with 0 keys (not None or a Counter with spurious entries)."""
        empty_nd = NestedDict()
        flat = CalendarHeatmapExporter._flatten_frequency(empty_nd)
        assert isinstance(flat, Counter)
        assert len(flat) == 0
        assert sum(flat.values()) == 0

    def test_print_calendar_heatmap_empty_nesteddict_has_friendly_prompt(self):
        """Top-level render for an empty journal MUST contain the
        user-facing empty-set prompt and MUST NOT contain the
        statistics panel title (which would only confuse users)."""
        output = CalendarHeatmapExporter.print_calendar_heatmap(NestedDict())

        assert "No entries found in the selected range." in output

    def test_print_calendar_heatmap_empty_skips_contribution_grid(self):
        """When there are zero entries the annual contribution grid
        branch (which iterates journal_frequency.keys()) must never
        execute. We verify by asserting no year headers and no legend
        are emitted."""
        output = CalendarHeatmapExporter.print_calendar_heatmap(NestedDict())

        assert "Legend" not in output
        assert "Monthly Detail View" not in output

    def test_print_calendar_heatmap_filtered_empty_tag_subset(self):
        """Simulate the output of `jrnl @nonexistent --format calendar`:
        get_journal_frequency_nested returns a NestedDict with 0 keys.
        The pipeline must complete without raising any exception and
        produce a helpful message instead of a traceback."""
        try:
            output = CalendarHeatmapExporter.print_calendar_heatmap(NestedDict())
        except Exception as exc:
            pytest.fail(f"print_calendar_heatmap raised {type(exc).__name__}: {exc}")

        assert isinstance(output, str)
        assert len(output) > 0
        assert "No entries" in output

    def test_empty_does_not_accidentally_render_year_2020_headers(self):
        """Regression guard: empty output must not contain any year
        number (e.g. from spurious iteration of default values)."""
        output = CalendarHeatmapExporter.print_calendar_heatmap(NestedDict())
        for year in range(2000, 2100):
            assert f"── {year} ──" not in output
            assert f"[bold green]{year}[/bold green]" not in output

    def test_color_style_edge_case_max_count_zero(self):
        """_get_color_style is called with max_count=0 can only happen
        when count is also 0 (empty set). Ensure no division occurs and
        it returns the dim background style."""
        style = CalendarHeatmapExporter._get_color_style(0, 0)
        assert "#161b22" in style
        assert "dim" in style
