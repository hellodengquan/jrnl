# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import calendar
from collections import Counter
from datetime import date
from datetime import datetime
from datetime import timedelta
from typing import TYPE_CHECKING

from rich import box
from rich.align import Align
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from jrnl.plugins.text_exporter import TextExporter
from jrnl.plugins.util import get_journal_frequency_nested

if TYPE_CHECKING:
    from jrnl.journals import Entry
    from jrnl.journals import Journal
    from jrnl.plugins.util import NestedDict


GITHUB_GREEN = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]


class CalendarHeatmapExporter(TextExporter):
    """This Exporter displays a calendar heatmap of the journaling frequency."""

    names = ["calendar", "heatmap"]
    extension = "cal"

    @classmethod
    def export_entry(cls, entry: "Entry"):
        raise NotImplementedError

    @classmethod
    def _get_color_style(cls, count: int, max_count: int) -> str:
        if count == 0:
            return f"dim on {GITHUB_GREEN[0]}"
        if max_count <= 1:
            return f"black on {GITHUB_GREEN[4]}"
        ratio = count / max_count
        if ratio <= 0.25:
            idx = 1
        elif ratio <= 0.5:
            idx = 2
        elif ratio <= 0.75:
            idx = 3
        else:
            idx = 4
        return f"black on {GITHUB_GREEN[idx]}"

    @classmethod
    def _get_month_cell_style(cls, count: int) -> str:
        if count == 0:
            return "red on black"
        elif count == 1:
            return "black on yellow"
        elif count == 2:
            return "black on green"
        else:
            return "black on white"

    @classmethod
    def _flatten_frequency(cls, journal_frequency: "NestedDict") -> Counter:
        flat = Counter()
        for year, months in journal_frequency.items():
            for month, days in months.items():
                for day, count in days.items():
                    d = date(year, month, day)
                    flat[d.strftime("%Y-%m-%d")] = count
        return flat

    @classmethod
    def _compute_statistics(cls, flat_counts: Counter) -> dict:
        total_entries = sum(flat_counts.values())
        active_days = len(flat_counts)

        if not flat_counts:
            return {
                "total_entries": 0,
                "active_days": 0,
                "total_days_span": 0,
                "longest_streak": 0,
                "current_streak": 0,
                "avg_per_active_day": 0.0,
                "avg_per_week": 0.0,
                "max_per_day": 0,
                "busiest_day": None,
                "activity_rate": 0.0,
            }

        sorted_dates = sorted(flat_counts.keys())
        first_date = datetime.strptime(sorted_dates[0], "%Y-%m-%d").date()
        last_date = datetime.strptime(sorted_dates[-1], "%Y-%m-%d").date()
        total_days_span = (last_date - first_date).days + 1

        longest_streak = 0
        current_streak_calc = 0
        prev_date = None
        for d in sorted_dates:
            curr = datetime.strptime(d, "%Y-%m-%d").date()
            if prev_date and (curr - prev_date).days == 1:
                current_streak_calc += 1
            else:
                current_streak_calc = 1
            longest_streak = max(longest_streak, current_streak_calc)
            prev_date = curr

        today = date.today()
        current_streak = 0
        check_date = today
        while True:
            date_str = check_date.strftime("%Y-%m-%d")
            if date_str in flat_counts:
                current_streak += 1
                check_date -= timedelta(days=1)
            else:
                break

        avg_per_active_day = total_entries / active_days if active_days > 0 else 0.0
        weeks_span = total_days_span / 7 if total_days_span > 0 else 1
        avg_per_week = total_entries / weeks_span if weeks_span > 0 else 0.0

        max_per_day = max(flat_counts.values())
        busiest_day = max(flat_counts, key=flat_counts.get)
        activity_rate = active_days / total_days_span * 100 if total_days_span > 0 else 0.0

        return {
            "total_entries": total_entries,
            "active_days": active_days,
            "total_days_span": total_days_span,
            "longest_streak": longest_streak,
            "current_streak": current_streak,
            "avg_per_active_day": avg_per_active_day,
            "avg_per_week": avg_per_week,
            "max_per_day": max_per_day,
            "busiest_day": busiest_day,
            "activity_rate": activity_rate,
        }

    @classmethod
    def _print_statistics(cls, console: Console, stats: dict) -> None:
        if stats["total_entries"] == 0:
            console.print(
                Panel(
                    "[yellow]No entries found in the selected range.[/yellow]",
                    border_style="yellow",
                )
            )
            return

        stats_table = Table(
            title="Journaling Activity Statistics",
            title_style="bold cyan",
            box=box.ROUNDED,
            show_header=False,
            padding=(0, 2),
        )
        stats_table.add_column("Metric", style="bold", justify="right")
        stats_table.add_column("Value", justify="left")

        stats_table.add_row("Total Entries", str(stats["total_entries"]))
        stats_table.add_row("Active Days", str(stats["active_days"]))
        stats_table.add_row("Date Span", f"{stats['total_days_span']} days")
        stats_table.add_row("Activity Rate", f"{stats['activity_rate']:.1f}%")
        stats_table.add_row("Longest Streak", f"{stats['longest_streak']} day(s)")
        stats_table.add_row("Current Streak", f"{stats['current_streak']} day(s)")
        stats_table.add_row("Avg / Active Day", f"{stats['avg_per_active_day']:.2f}")
        stats_table.add_row("Avg / Week", f"{stats['avg_per_week']:.2f}")
        stats_table.add_row(
            "Max / Day",
            f"{stats['max_per_day']} (on {stats['busiest_day']})",
        )

        console.print(Align.center(stats_table))
        console.print()

    @classmethod
    def _print_legend(cls, console: Console, max_count: int) -> None:
        colors_row = []
        for i in range(5):
            colors_row.append(Text("  ", style=f"black on {GITHUB_GREEN[i]}"))

        labels_row = ["Less"]
        for level in range(5):
            if max_count <= 1:
                if level == 0:
                    labels_row.append("0")
                elif level == 4:
                    labels_row.append("1+")
                else:
                    labels_row.append("")
            else:
                threshold = int(max_count * level / 4)
                labels_row.append(str(threshold))
        labels_row.append("More")

        legend_table = Table(
            title="Legend",
            title_style="bold dim",
            box=None,
            padding=0,
            show_header=False,
            collapse_padding=True,
        )
        for _ in range(7):
            legend_table.add_column("", justify="center", width=4)

        color_cells = [Text("")] + colors_row + [Text("")]
        label_cells = [Text(l, style="dim") for l in labels_row]
        legend_table.add_row(*color_cells)
        legend_table.add_row(*label_cells)

        console.print(Align.center(legend_table))
        console.print()

    @classmethod
    def _get_year_counts(
        cls, journal_frequency: "NestedDict", target_year: int
    ) -> Counter:
        year_counts = Counter()
        for year, months in journal_frequency.items():
            if year == target_year:
                for month, days in months.items():
                    for day, count in days.items():
                        d = date(target_year, month, day)
                        year_counts[d.strftime("%Y-%m-%d")] = count
        return year_counts

    @classmethod
    def _build_year_grid(
        cls, year: int, date_counts: Counter
    ) -> tuple[list, int]:
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)
        today = date.today()

        start_weekday = year_start.weekday()

        days_in_year = (year_end - year_start).days + 1
        total_weeks = (days_in_year + start_weekday + 6) // 7

        grid = []
        for week_idx in range(total_weeks):
            week = []
            for day_idx in range(7):
                day_offset = week_idx * 7 + day_idx - start_weekday
                if 0 <= day_offset < days_in_year:
                    current_date = year_start + timedelta(days=day_offset)
                    if current_date > today:
                        week.append(None)
                    else:
                        date_str = current_date.strftime("%Y-%m-%d")
                        count = date_counts.get(date_str, 0)
                        week.append((count, current_date, date_str))
                else:
                    week.append(None)
            grid.append(week)

        return grid, total_weeks

    @classmethod
    def _print_month_labels(
        cls, console: Console, grid: list, total_weeks: int
    ) -> None:
        month_labels = [""] * total_weeks
        last_month = 0
        for week_idx in range(total_weeks):
            for day_idx in range(7):
                cell = grid[week_idx][day_idx]
                if cell is not None:
                    _, current_date, _ = cell
                    if current_date.month != last_month:
                        if week_idx == 0 or day_idx == 0:
                            month_labels[week_idx] = calendar.month_abbr[
                                current_date.month
                            ]
                        last_month = current_date.month
                        break

        labels_table = Table(
            box=None,
            padding=0,
            show_header=False,
            collapse_padding=True,
        )
        labels_table.add_column("", justify="left", width=4)
        for week_idx in range(total_weeks):
            labels_table.add_column("", justify="center", width=2)
        labels_table.add_row(Text("", style="dim"), *[Text(l, style="dim") for l in month_labels])
        console.print(Align.center(labels_table))

    @classmethod
    def _print_year_contribution_map(
        cls, console: Console, year: int, date_counts: Counter, max_count: int
    ) -> None:
        grid, total_weeks = cls._build_year_grid(year, date_counts)

        cls._print_month_labels(console, grid, total_weeks)

        day_names = ["Mon", "", "Wed", "", "Fri", "", "Sun"]

        heatmap_table = Table(
            title=f"[bold green]{year}[/bold green]",
            title_style="",
            box=None,
            padding=0,
            show_header=False,
            collapse_padding=True,
        )
        heatmap_table.add_column("", justify="right", width=4, style="dim")
        for week_idx in range(total_weeks):
            heatmap_table.add_column("", justify="center", width=2)

        for day_idx in range(7):
            row = [Text(day_names[day_idx], style="dim")]
            for week_idx in range(total_weeks):
                cell = grid[week_idx][day_idx]
                if cell is None:
                    row.append(Text("  "))
                else:
                    count, current_date, date_str = cell
                    style = cls._get_color_style(count, max_count)
                    display = f"{count:2d}" if count > 0 else "  "
                    cell_text = Text(display, style=style)
                    row.append(cell_text)
            heatmap_table.add_row(*row)

        console.print(Align.center(heatmap_table))

    @classmethod
    def _print_monthly_calendar(cls, journal_frequency: "NestedDict") -> str:
        console = Console()
        cal = calendar.Calendar()
        curr_year = datetime.now().year
        curr_month = datetime.now().month
        curr_day = datetime.now().day
        hit_first_entry = False
        with console.capture() as capture:
            for year, month_journaling_freq in sorted(journal_frequency.items()):
                year_calendar = []
                for month in range(1, 13):
                    if month > curr_month and year == curr_year:
                        break

                    entries_this_month = sum(month_journaling_freq[month].values())
                    if not hit_first_entry and entries_this_month > 0:
                        hit_first_entry = True

                    if entries_this_month == 0 and not hit_first_entry:
                        continue
                    elif entries_this_month == 0:
                        entry_msg = "No entries"
                    elif entries_this_month == 1:
                        entry_msg = "1 entry"
                    else:
                        entry_msg = f"{entries_this_month} entries"
                    table = Table(
                        title=f"{calendar.month_name[month]} {year} ({entry_msg})",
                        title_style="bold green",
                        box=box.SIMPLE_HEAVY,
                        padding=0,
                    )

                    for week_day in cal.iterweekdays():
                        table.add_column(
                            "{:.3}".format(calendar.day_name[week_day]),
                            justify="right",
                        )

                    month_days = cal.monthdayscalendar(year, month)
                    for weekdays in month_days:
                        days = []
                        stop_early = False
                        for _, day in enumerate(weekdays):
                            if day == 0:
                                day_label = Text(str(day or ""), style="white")
                            elif (
                                day > curr_day
                                and month == curr_month
                                and year == curr_year
                            ):
                                stop_early = True
                                break
                            else:
                                journal_frequency_for_day = (
                                    month_journaling_freq[month][day] or 0
                                )
                                day = str(day)
                                day_label = Text(
                                    day,
                                    style=cls._get_month_cell_style(
                                        journal_frequency_for_day
                                    ),
                                )

                            days.append(day_label)
                        if days:
                            table.add_row(*days)
                        if stop_early:
                            break

                    year_calendar.append(Align.center(table))

                if year_calendar:
                    console.rule(str(year))
                    console.print()
                    console.print(Columns(year_calendar, padding=1, expand=True))
        return capture.get()

    @classmethod
    def print_calendar_heatmap(cls, journal_frequency: "NestedDict") -> str:
        """Returns a string representation of the calendar heatmap."""
        console = Console()

        all_counts = []
        for year, months in journal_frequency.items():
            for month, days in months.items():
                for day, count in days.items():
                    all_counts.append(count)

        max_count = max(all_counts) if all_counts else 0
        flat_counts = cls._flatten_frequency(journal_frequency)
        stats = cls._compute_statistics(flat_counts)

        with console.capture() as capture:
            cls._print_statistics(console, stats)

            if stats["total_entries"] > 0:
                years = sorted(journal_frequency.keys())
                for year in years:
                    year_counts = cls._get_year_counts(journal_frequency, year)
                    year_max = max(year_counts.values()) if year_counts else 1
                    cls._print_year_contribution_map(
                        console, year, year_counts, max(year_max, 1)
                    )
                    console.print()

                cls._print_legend(console, max_count)

            monthly_output = cls._print_monthly_calendar(journal_frequency)
            if monthly_output.strip():
                console.rule("Monthly Detail View")
                console.print()
                console.print(monthly_output)

        return capture.get()

    @classmethod
    def export_journal(cls, journal: "Journal"):
        """Returns dates and their frequencies for an entire journal."""
        journal_entry_date_frequency = get_journal_frequency_nested(journal)
        return cls.print_calendar_heatmap(journal_entry_date_frequency)
