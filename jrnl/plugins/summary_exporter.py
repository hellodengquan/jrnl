# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import datetime
import json
import os
import re
import sys
from collections import Counter
from typing import TYPE_CHECKING

from jrnl.plugins.text_exporter import TextExporter

if TYPE_CHECKING:
    from jrnl.journals import Entry
    from jrnl.journals import Journal


_SUMMARY_I18N = {
    "en": {
        "review_title": "Periodic Review Summary",
        "overview": "Overview Statistics",
        "total_entries": "Total entries: {count}",
        "starred_entries": "Starred entries: {count}",
        "tags_used": "Tags used: {count}",
        "todo_items": "Todo items: {count}",
        "tag_activity": "Tag Activity Ranking",
        "times": "times",
        "todo_summary": "Outstanding Todo Items",
        "featured_entries": "Featured Entries",
        "daily_distribution": "Daily Entry Distribution",
        "entries_label": "entries",
        "no_entries_found": "No entries found in the selected time range.",
        "year_month": "{year} {month}",
        "year_week": "{year} Week {week} ({start} - {end})",
        "month_jan": "January",
        "month_feb": "February",
        "month_mar": "March",
        "month_apr": "April",
        "month_may": "May",
        "month_jun": "June",
        "month_jul": "July",
        "month_aug": "August",
        "month_sep": "September",
        "month_oct": "October",
        "month_nov": "November",
        "month_dec": "December",
    },
    "zh": {
        "review_title": "回顾摘要",
        "overview": "总体统计",
        "total_entries": "日记条目总数: {count} 条",
        "starred_entries": "重要条目 (星标): {count} 条",
        "tags_used": "使用标签数: {count} 个",
        "todo_items": "待办事项: {count} 项",
        "tag_activity": "标签活跃度排行",
        "times": "次",
        "todo_summary": "未完成事项汇总",
        "featured_entries": "精选条目",
        "daily_distribution": "每日条目分布",
        "entries_label": "条",
        "no_entries_found": "选定时间范围内未找到条目。",
        "year_month": "{year}年 {month}",
        "year_week": "{year}年 第{week}周 ({start} - {end})",
        "month_jan": "1月",
        "month_feb": "2月",
        "month_mar": "3月",
        "month_apr": "4月",
        "month_may": "5月",
        "month_jun": "6月",
        "month_jul": "7月",
        "month_aug": "8月",
        "month_sep": "9月",
        "month_oct": "10月",
        "month_nov": "11月",
        "month_dec": "12月",
    },
}

_MONTH_KEYS = [
    "month_jan",
    "month_feb",
    "month_mar",
    "month_apr",
    "month_may",
    "month_jun",
    "month_jul",
    "month_aug",
    "month_sep",
    "month_oct",
    "month_nov",
    "month_dec",
]

_MONTH_NAMES_ZH = [
    "1月",
    "2月",
    "3月",
    "4月",
    "5月",
    "6月",
    "7月",
    "8月",
    "9月",
    "10月",
    "11月",
    "12月",
]

_MONTH_NAMES_EN = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


def _detect_language() -> str:
    """Detect display language from environment.

    Checks (in order): JRNL_LANG env var, LANG env var, system locale.
    Returns 'zh' for Chinese locales, 'en' otherwise (default).
    """
    lang_env = os.environ.get("JRNL_LANG", "").strip().lower()
    if lang_env.startswith("zh"):
        return "zh"
    if lang_env.startswith("en"):
        return "en"

    sys_lang = os.environ.get("LANG", "").strip().lower()
    if sys_lang.startswith("zh"):
        return "zh"

    if sys.platform.startswith("darwin") or sys.platform.startswith("linux"):
        try:
            import locale

            loc, _ = locale.getdefaultlocale()
            if loc and loc.lower().startswith("zh"):
                return "zh"
        except Exception:
            pass

    return "en"


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
    def _t(cls, key: str, lang: str | None = None, **kwargs) -> str:
        """Lookup i18n string with optional formatting."""
        if lang is None:
            lang = _detect_language()
        table = _SUMMARY_I18N.get(lang, _SUMMARY_I18N["en"])
        template = table.get(key, _SUMMARY_I18N["en"].get(key, key))
        return template.format(**kwargs) if kwargs else template

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
    def export_journal_json(cls, journal: "Journal", period: str = "month") -> str:
        """Generates a periodic review summary as JSON.

        Args:
            journal: The journal to summarize
            period: 'week' or 'month'

        Returns:
            JSON string with structured summary data
        """
        if not journal.entries:
            return json.dumps({"periods": [], "total_entries": 0}, indent=2)

        periods = cls._group_by_period(journal.entries, period)
        sorted_keys = sorted(periods.keys(), reverse=True)

        output_periods = []

        for idx, period_key in enumerate(sorted_keys):
            prev_tag_stats = None
            if idx + 1 < len(sorted_keys):
                prev_key = sorted_keys[idx + 1]
                prev_tag_stats = cls._get_tag_stats(periods[prev_key])

            period_data = cls._build_period_data(
                period_key, periods[period_key], period, prev_tag_stats
            )
            output_periods.append(period_data)

        result = {
            "period": period,
            "total_entries": len(journal.entries),
            "periods": output_periods,
        }
        return json.dumps(result, indent=2, ensure_ascii=False)

    @classmethod
    def _build_period_data(
        cls,
        period_key: str,
        entries: list["Entry"],
        period: str,
        prev_tag_stats: list[tuple[str, int]] | None = None,
    ) -> dict:
        """Build structured dict of data for a single period (for JSON export)."""
        tag_stats = cls._get_tag_stats(entries)
        prev_tag_dict = dict(prev_tag_stats) if prev_tag_stats else {}
        has_prev = prev_tag_stats is not None

        tags = []
        for tag, count in tag_stats:
            prev_count = prev_tag_dict.get(tag, 0)
            trend = count - prev_count if has_prev else None
            tags.append(
                {
                    "tag": tag,
                    "count": count,
                    "previous_count": prev_count if has_prev else None,
                    "trend": trend,
                }
            )

        todo_items = cls._find_todo_items(entries)
        todos = [
            {
                "date": item["date"].strftime("%Y-%m-%d"),
                "time": item["date"].strftime("%H:%M"),
                "title": item["title"],
                "text": item["text"],
            }
            for item in todo_items
        ]

        daily = [
            {"date": ds, "count": c} for ds, c in cls._get_daily_stats(entries)
        ]

        featured = [
            {
                "date": e.date.strftime("%Y-%m-%d"),
                "time": e.date.strftime("%H:%M"),
                "title": e.title.strip(),
                "starred": e.starred,
                "tags": list(e.tags),
            }
            for e in cls._get_top_entries(entries)
        ]

        return {
            "period_key": period_key,
            "label": cls._format_period_label(period_key, period),
            "label_en": cls._format_period_label(period_key, period, lang="en"),
            "stats": {
                "entries": len(entries),
                "starred": sum(1 for e in entries if e.starred),
                "tags": len(tag_stats),
                "todos": len(todo_items),
            },
            "tags": tags,
            "todos": todos,
            "featured_entries": featured,
            "daily_distribution": daily,
        }

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
            return cls._t("no_entries_found") + "\n"

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
        lines.append(f"  {period_label} {cls._t('review_title')}")
        lines.append(f"{'=' * 60}")
        lines.append("")

        lines.append(cls._t("overview"))
        lines.append(f"  • {cls._t('total_entries', count=entry_count)}")
        lines.append(f"  • {cls._t('starred_entries', count=starred_count)}")
        lines.append(f"  • {cls._t('tags_used', count=len(tag_stats))}")
        lines.append(f"  • {cls._t('todo_items', count=len(todo_items))}")
        lines.append("")

        if tag_stats:
            lines.append(cls._t("tag_activity"))
            has_prev = prev_tag_stats is not None
            prev_tag_dict = dict(prev_tag_stats) if prev_tag_stats else {}
            times_label = cls._t("times")
            for i, (tag, count) in enumerate(tag_stats[:10], 1):
                bar = "█" * min(count, 20)
                trend = cls._format_tag_trend(
                    count, prev_tag_dict.get(tag, 0), has_previous_period=has_prev
                )
                lines.append(
                    f"  {i:2d}. {tag:<20} {count:3d} {times_label} {bar}{trend}"
                )
            lines.append("")

        if todo_items:
            lines.append(cls._t("todo_summary"))
            for i, item in enumerate(todo_items, 1):
                date_str = item["date"].strftime("%m-%d")
                lines.append(f"  {i}. [{date_str}] {item['title']}")
            lines.append("")

        if top_entries:
            lines.append(cls._t("featured_entries"))
            for entry in top_entries:
                lines.append(f"  • {cls.export_entry(entry)}")
            lines.append("")

        daily_stats = cls._get_daily_stats(entries)
        if daily_stats:
            lines.append(cls._t("daily_distribution"))
            entries_label = cls._t("entries_label")
            for date_str, count in daily_stats:
                bar = "█" * min(count, 20)
                lines.append(f"  {date_str}: {count:2d} {entries_label} {bar}")
            lines.append("")

        return "\n".join(lines)

    @classmethod
    def _format_period_label(
        cls, period_key: str, period: str, lang: str | None = None
    ) -> str:
        """Format period key into human-readable label.

        Args:
            period_key: Period identifier (e.g., '2024-01' or '2024-W01')
            period: 'week' or 'month'
            lang: Optional language override ('en' or 'zh')

        Returns:
            Human-readable period label
        """
        if lang is None:
            lang = _detect_language()

        if period == "week":
            year_str, week_str = period_key.split("-W")
            year = int(year_str)
            week = int(week_str)

            monday = datetime.datetime.fromisocalendar(year, week, 1)
            sunday = datetime.datetime.fromisocalendar(year, week, 7)

            if lang == "zh":
                return cls._t(
                    "year_week",
                    lang=lang,
                    year=year,
                    week=week,
                    start=monday.strftime("%m月%d日"),
                    end=sunday.strftime("%m月%d日"),
                )
            else:
                return cls._t(
                    "year_week",
                    lang=lang,
                    year=year,
                    week=week,
                    start=monday.strftime("%b %d"),
                    end=sunday.strftime("%b %d"),
                )
        else:
            year, month = period_key.split("-")
            month_int = int(month)
            month_key = _MONTH_KEYS[month_int - 1]
            month_label = cls._t(month_key, lang=lang)
            return cls._t("year_month", lang=lang, year=year, month=month_label)

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
            Formatted trend string (e.g. ' (+2)', ' (-1)', or '')
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


class SummaryJSONExporter(TextExporter):
    """This Exporter generates periodic review summaries in JSON format."""

    names = ["summary_json"]
    extension = "json"

    @classmethod
    def export_entry(cls, entry: "Entry") -> str:
        """Returns a JSON representation of a single entry (delegates to JSONExporter)."""
        from jrnl.plugins.json_exporter import JSONExporter

        return JSONExporter.export_entry(entry)

    @classmethod
    def export_journal(cls, journal: "Journal") -> str:
        """Generates a periodic review summary for the entire journal as JSON."""
        return SummaryExporter.export_journal_json(journal, period="month")
