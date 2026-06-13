# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import datetime
import re
from collections import Counter
from typing import TYPE_CHECKING

from jrnl.plugins.text_exporter import TextExporter

if TYPE_CHECKING:
    from jrnl.journals import Entry
    from jrnl.journals import Journal


class SummaryExporter(TextExporter):
    """This Exporter generates periodic review summaries of journal entries."""

    names = ["summary"]
    extension = "txt"

    TODO_PATTERNS = [
        re.compile(r"\bTODO\b:?", re.IGNORECASE),
        re.compile(r"待办"),
        re.compile(r"未完成"),
        re.compile(r"\bTBD\b:?", re.IGNORECASE),
        re.compile(r"待完成"),
        re.compile(r"^\s*[-*] \[[ x]\]\s", re.MULTILINE),
    ]

    @classmethod
    def export_entry(cls, entry: "Entry") -> str:
        """Returns a summary line for a single entry."""
        date_str = entry.date.strftime("%Y-%m-%d")
        title = entry.title.strip()
        starred = "*" if entry.starred else " "
        return f"[{date_str}] {starred}{title}"

    @classmethod
    def export_journal(cls, journal: "Journal") -> str:
        """Generates a periodic review summary for the entire journal."""
        return cls._generate_summary(journal, period="month")

    @classmethod
    def _generate_summary(cls, journal: "Journal", period: str = "month") -> str:
        """Generate a periodic review summary.

        Args:
            journal: The journal to summarize
            period: 'week' or 'month'

        Returns:
            Formatted summary text
        """
        if not journal.entries:
            return "No entries found in the selected time range.\n"

        entries = journal.entries
        periods = cls._group_by_period(entries, period)

        sorted_keys = sorted(periods.keys(), reverse=True)

        result_parts = []

        for idx, period_key in enumerate(sorted_keys):
            prev_tag_stats = None
            if idx + 1 < len(sorted_keys):
                prev_key = sorted_keys[idx + 1]
                prev_tag_stats = cls._get_tag_stats(periods[prev_key])

            period_summary = cls._generate_period_summary(
                period_key, periods[period_key], period, prev_tag_stats=prev_tag_stats
            )
            result_parts.append(period_summary)

        return "\n\n".join(result_parts) + "\n"

    @classmethod
    def _group_by_period(
        cls, entries: list["Entry"], period: str
    ) -> dict[str, list["Entry"]]:
        """Group entries by time period.

        Args:
            entries: List of journal entries
            period: 'week' or 'month'

        Returns:
            Dictionary mapping period keys to lists of entries
        """
        periods = {}

        for entry in entries:
            if period == "week":
                year, week_num, _ = entry.date.isocalendar()
                key = f"{year}-W{week_num:02d}"
            else:
                key = entry.date.strftime("%Y-%m")

            if key not in periods:
                periods[key] = []
            periods[key].append(entry)

        return periods

    @classmethod
    def _generate_period_summary(
        cls,
        period_key: str,
        entries: list["Entry"],
        period: str,
        prev_tag_stats: list[tuple[str, int]] | None = None,
    ) -> str:
        """Generate summary for a single time period.

        Args:
            period_key: Identifier for the time period
            entries: List of entries in this period
            period: 'week' or 'month'
            prev_tag_stats: Tag stats from previous period for trend comparison

        Returns:
            Formatted summary for the period
        """
        entry_count = len(entries)
        starred_count = sum(1 for e in entries if e.starred)
        tag_stats = cls._get_tag_stats(entries)
        todo_items = cls._find_todo_items(entries)
        top_entries = cls._get_top_entries(entries)

        period_label = cls._format_period_label(period_key, period)

        lines = []
        lines.append(f"{'=' * 60}")
        lines.append(f"  {period_label} 回顾摘要")
        lines.append(f"{'=' * 60}")
        lines.append("")

        lines.append("📊 总体统计")
        lines.append(f"  • 日记条目总数: {entry_count} 条")
        lines.append(f"  • 重要条目 (星标): {starred_count} 条")
        lines.append(f"  • 使用标签数: {len(tag_stats)} 个")
        lines.append(f"  • 待办事项: {len(todo_items)} 项")
        lines.append("")

        if tag_stats:
            lines.append("🏷️  标签活跃度排行")
            has_prev = prev_tag_stats is not None
            prev_tag_dict = dict(prev_tag_stats) if prev_tag_stats else {}
            for i, (tag, count) in enumerate(tag_stats[:10], 1):
                bar = "█" * min(count, 20)
                trend = cls._format_tag_trend(
                    count, prev_tag_dict.get(tag, 0), has_previous_period=has_prev
                )
                lines.append(f"  {i:2d}. {tag:<20} {count:3d}次 {bar}{trend}")
            lines.append("")

        if todo_items:
            lines.append("✅ 未完成事项汇总")
            for i, item in enumerate(todo_items, 1):
                date_str = item["date"].strftime("%m-%d")
                lines.append(f"  {i}. [{date_str}] {item['title']}")
            lines.append("")

        if top_entries:
            lines.append("📝 精选条目")
            for entry in top_entries:
                lines.append(f"  • {cls.export_entry(entry)}")
            lines.append("")

        daily_stats = cls._get_daily_stats(entries)
        if daily_stats:
            lines.append("📅 每日条目分布")
            for date_str, count in daily_stats:
                bar = "█" * min(count, 20)
                lines.append(f"  {date_str}: {count:2d}条 {bar}")
            lines.append("")

        return "\n".join(lines)

    @classmethod
    def _format_period_label(cls, period_key: str, period: str) -> str:
        """Format period key into human-readable label.

        Args:
            period_key: Period identifier (e.g., '2024-01' or '2024-W01')
            period: 'week' or 'month'

        Returns:
            Human-readable period label
        """
        if period == "week":
            year_str, week_str = period_key.split("-W")
            year = int(year_str)
            week = int(week_str)

            monday = datetime.datetime.fromisocalendar(year, week, 1)
            sunday = datetime.datetime.fromisocalendar(year, week, 7)

            return (
                f"{year}年 第{week}周 "
                f"({monday.strftime('%m月%d日')} - {sunday.strftime('%m月%d日')})"
            )
        else:
            year, month = period_key.split("-")
            return f"{year}年 {int(month)}月"

    @classmethod
    def _get_tag_stats(cls, entries: list["Entry"]) -> list[tuple[str, int]]:
        """Get tag statistics sorted by frequency.

        Args:
            entries: List of journal entries

        Returns:
            List of (tag_name, count) tuples, sorted by count descending
        """
        tag_counter = Counter()
        for entry in entries:
            for tag in entry.tags:
                tag_counter[tag] += 1

        return tag_counter.most_common()

    @classmethod
    def _format_tag_trend(
        cls, current: int, previous: int, has_previous_period: bool = True
    ) -> str:
        """Format a trend indicator comparing current count to previous period.

        Args:
            current: Current period tag count
            previous: Previous period tag count
            has_previous_period: Whether there is a previous period to compare against

        Returns:
            Formatted trend string (e.g. ' (+2)', ' (-1)', ' (new)', or '')
            Returns empty string when there is no previous period.
        """
        if not has_previous_period:
            return ""
        diff = current - previous
        if diff > 0:
            return f" (+{diff})"
        elif diff < 0:
            return f" ({diff})"
        return ""

    @classmethod
    def _find_todo_items(cls, entries: list["Entry"]) -> list[dict]:
        """Find entries that contain TODO/task items.

        Args:
            entries: List of journal entries

        Returns:
            List of dicts with 'date', 'title', and 'text' keys
        """
        todo_items = []

        for entry in entries:
            full_text = entry.title + " " + entry.body
            if any(pattern.search(full_text) for pattern in cls.TODO_PATTERNS):
                todo_items.append(
                    {
                        "date": entry.date,
                        "title": entry.title.strip(),
                        "text": entry.body.strip(),
                    }
                )

        todo_items.sort(key=lambda x: x["date"], reverse=True)
        return todo_items

    @classmethod
    def _get_top_entries(cls, entries: list["Entry"]) -> list["Entry"]:
        """Get top entries to highlight in the summary.

        Prioritizes starred entries, then entries with tags.

        Args:
            entries: List of journal entries

        Returns:
            List of top entries (up to 5)
        """
        sorted_entries = sorted(
            entries,
            key=lambda e: (e.starred, len(e.tags), e.date),
            reverse=True,
        )
        return sorted_entries[:5]

    @classmethod
    def _get_daily_stats(cls, entries: list["Entry"]) -> list[tuple[str, int]]:
        """Get daily entry counts.

        Args:
            entries: List of journal entries

        Returns:
            List of (date_string, count) tuples
        """
        daily_counts = Counter()
        for entry in entries:
            date_str = entry.date.strftime("%m-%d")
            daily_counts[date_str] += 1

        return sorted(daily_counts.items())
