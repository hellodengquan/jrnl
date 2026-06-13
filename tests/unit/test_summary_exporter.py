# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import datetime
import re

import pytest

from jrnl.journals.Entry import Entry
from jrnl.journals.Journal import Journal
from jrnl.plugins.summary_exporter import SummaryExporter


@pytest.fixture
def journal():
    j = Journal("test")
    return j


def _make_entry(journal, date_str, text, starred=False):
    date = datetime.datetime.strptime(date_str, "%Y-%m-%d %H:%M")
    return Entry(journal, date=date, text=text, starred=starred)


class TestGroupByPeriod:
    def test_group_by_month(self, journal):
        e1 = _make_entry(journal, "2024-01-05 09:00", "entry a @work")
        e2 = _make_entry(journal, "2024-01-20 10:00", "entry b @personal")
        e3 = _make_entry(journal, "2024-02-01 14:00", "entry c @work")
        entries = [e1, e2, e3]

        result = SummaryExporter._group_by_period(entries, "month")

        assert "2024-01" in result
        assert "2024-02" in result
        assert len(result["2024-01"]) == 2
        assert len(result["2024-02"]) == 1

    def test_group_by_week(self, journal):
        e1 = _make_entry(journal, "2024-01-01 09:00", "entry a")
        e2 = _make_entry(journal, "2024-01-08 09:00", "entry b")
        e3 = _make_entry(journal, "2024-01-15 09:00", "entry c")
        entries = [e1, e2, e3]

        result = SummaryExporter._group_by_period(entries, "week")

        assert len(result) == 3
        for key in result:
            assert key.startswith("2024-W")
            assert len(result[key]) == 1

    def test_group_by_month_empty(self, journal):
        result = SummaryExporter._group_by_period([], "month")
        assert result == {}

    def test_group_by_week_same_week(self, journal):
        e1 = _make_entry(journal, "2024-01-01 09:00", "monday")
        e2 = _make_entry(journal, "2024-01-02 09:00", "tuesday")
        e3 = _make_entry(journal, "2024-01-03 09:00", "wednesday")
        entries = [e1, e2, e3]

        result = SummaryExporter._group_by_period(entries, "week")

        assert len(result) == 1
        single_key = list(result.keys())[0]
        assert len(result[single_key]) == 3

    def test_group_by_month_spanning_years(self, journal):
        e1 = _make_entry(journal, "2023-12-25 09:00", "dec entry")
        e2 = _make_entry(journal, "2024-01-05 09:00", "jan entry")
        entries = [e1, e2]

        result = SummaryExporter._group_by_period(entries, "month")

        assert "2023-12" in result
        assert "2024-01" in result
        assert len(result["2023-12"]) == 1
        assert len(result["2024-01"]) == 1


class TestTodoPatterns:
    @pytest.mark.parametrize(
        "text,should_match",
        [
            ("TODO: finish the report", True),
            ("todo: buy groceries", True),
            ("TODO fix this bug", True),
            ("Some regular text", False),
            ("待办: 完成任务", True),
            ("这是一个待办事项", True),
            ("未完成的工作", True),
            ("TBD: confirm with team", True),
            ("tbd: need to decide", True),
            ("待完成: 回复邮件", True),
            ("- [ ] Write unit tests", True),
            ("- [x] Completed task", True),
            ("- [ ]  Buy milk", True),
            ("* [ ] Use star bullet", True),
            ("* [x] Star bullet done", True),
            ("  - [ ] Indented checkbox", True),
            ("    * [ ] Heavily indented", True),
            ("* [ ]  Buy milk", True),
            (" - [ ] space then dash", True),
            ("Check the [ ] box", False),
            ("Just brackets [ ] in text", False),
            ("- [] missing space", False),
        ],
    )
    def test_todo_patterns_match(self, text, should_match):
        matched = any(p.search(text) for p in SummaryExporter.TODO_PATTERNS)
        assert matched == should_match

    def test_find_todo_items_basic(self, journal):
        e1 = _make_entry(journal, "2024-01-10 09:00", "TODO: finish code review @work")
        e2 = _make_entry(journal, "2024-01-11 10:00", "Regular entry @personal")
        e3 = _make_entry(journal, "2024-01-12 11:00", "待办: buy groceries")
        e4 = _make_entry(journal, "2024-01-13 12:00", "- [ ] Write docs @work")

        result = SummaryExporter._find_todo_items([e1, e2, e3, e4])

        assert len(result) == 3
        titles = [item["title"] for item in result]
        assert any("TODO" in t for t in titles)
        assert any("待办" in t for t in titles)

    def test_find_todo_items_markdown_checkbox(self, journal):
        e1 = _make_entry(
            journal,
            "2024-01-10 09:00",
            "Task list\n- [ ] Write unit tests\n- [x] Setup project\n- [ ] Deploy",
        )

        result = SummaryExporter._find_todo_items([e1])

        assert len(result) == 1

    def test_find_todo_items_star_bullet_checkbox(self, journal):
        e1 = _make_entry(
            journal,
            "2024-01-10 09:00",
            "Star list\n* [ ] Task one\n* [x] Task two\n* [ ] Task three",
        )

        result = SummaryExporter._find_todo_items([e1])

        assert len(result) == 1

    def test_find_todo_items_indented_checkbox(self, journal):
        e1 = _make_entry(
            journal,
            "2024-01-10 09:00",
            "Nested list\n  - [ ] Indented task\n    * [ ] Deep task",
        )

        result = SummaryExporter._find_todo_items([e1])

        assert len(result) == 1

    def test_find_todo_items_mixed_bullets(self, journal):
        e1 = _make_entry(
            journal,
            "2024-01-10 09:00",
            "Mixed\n- [ ] dash task\n* [ ] star task\n  - [ ] indented",
        )

        result = SummaryExporter._find_todo_items([e1])

        assert len(result) == 1

    def test_find_todo_items_todo_colon(self, journal):
        e1 = _make_entry(journal, "2024-01-10 09:00", "TODO: review PR")
        e2 = _make_entry(journal, "2024-01-11 09:00", "Just a TODO in a sentence")

        result = SummaryExporter._find_todo_items([e1, e2])

        assert len(result) == 2

    def test_find_todo_items_no_todos(self, journal):
        e1 = _make_entry(journal, "2024-01-10 09:00", "Regular entry @work")
        e2 = _make_entry(journal, "2024-01-11 10:00", "Another normal day @personal")

        result = SummaryExporter._find_todo_items([e1, e2])

        assert len(result) == 0

    def test_find_todo_items_sorted_by_date_desc(self, journal):
        e1 = _make_entry(journal, "2024-01-01 09:00", "TODO: first task")
        e2 = _make_entry(journal, "2024-01-15 09:00", "TODO: second task")
        e3 = _make_entry(journal, "2024-01-10 09:00", "TODO: third task")

        result = SummaryExporter._find_todo_items([e1, e2, e3])

        assert result[0]["date"] > result[1]["date"]
        assert result[1]["date"] > result[2]["date"]


class TestTagStats:
    def test_get_tag_stats_sorted_by_count(self, journal):
        e1 = _make_entry(journal, "2024-01-01 09:00", "Entry @work @project")
        e2 = _make_entry(journal, "2024-01-02 09:00", "Entry @work")
        e3 = _make_entry(journal, "2024-01-03 09:00", "Entry @personal @work @hobby")
        e4 = _make_entry(journal, "2024-01-04 09:00", "Entry @personal @work")

        result = SummaryExporter._get_tag_stats([e1, e2, e3, e4])

        tag_names = [tag for tag, _ in result]
        tag_counts = {tag: count for tag, count in result}

        assert tag_names[0] == "@work"
        assert tag_counts["@work"] == 4
        assert tag_counts["@personal"] == 2
        assert tag_counts["@project"] == 1
        assert tag_counts["@hobby"] == 1

    def test_get_tag_stats_empty_entries(self, journal):
        result = SummaryExporter._get_tag_stats([])
        assert result == []

    def test_get_tag_stats_no_tags(self, journal):
        e1 = _make_entry(journal, "2024-01-01 09:00", "No tags here")

        result = SummaryExporter._get_tag_stats([e1])

        assert result == []

    def test_get_tag_stats_tie_breaking(self, journal):
        e1 = _make_entry(journal, "2024-01-01 09:00", "Entry @alpha")
        e2 = _make_entry(journal, "2024-01-02 09:00", "Entry @beta")

        result = SummaryExporter._get_tag_stats([e1, e2])

        assert len(result) == 2
        counts = [c for _, c in result]
        assert counts[0] == counts[1] == 1


class TestFormatTagTrend:
    def test_increase(self):
        assert SummaryExporter._format_tag_trend(5, 3) == " (+2)"

    def test_decrease(self):
        assert SummaryExporter._format_tag_trend(2, 5) == " (-3)"

    def test_no_change(self):
        assert SummaryExporter._format_tag_trend(3, 3) == ""

    def test_new_tag(self):
        assert SummaryExporter._format_tag_trend(1, 0) == " (+1)"

    def test_zero_vs_zero(self):
        assert SummaryExporter._format_tag_trend(0, 0) == ""

    def test_no_previous_period_increase_returns_empty(self):
        assert SummaryExporter._format_tag_trend(5, 0, has_previous_period=False) == ""

    def test_no_previous_period_zero_returns_empty(self):
        assert SummaryExporter._format_tag_trend(0, 0, has_previous_period=False) == ""

    def test_no_previous_period_any_value_returns_empty(self):
        assert (
            SummaryExporter._format_tag_trend(100, 0, has_previous_period=False) == ""
        )


class TestFormatPeriodLabel:
    def test_month_label(self):
        result = SummaryExporter._format_period_label("2024-03", "month")
        assert result == "2024年 3月"

    def test_week_label(self):
        result = SummaryExporter._format_period_label("2024-W02", "week")
        assert "2024年" in result
        assert "第2周" in result

    def test_month_label_december(self):
        result = SummaryExporter._format_period_label("2024-12", "month")
        assert result == "2024年 12月"


class TestGetDailyStats:
    def test_daily_stats(self, journal):
        e1 = _make_entry(journal, "2024-01-05 09:00", "morning")
        e2 = _make_entry(journal, "2024-01-05 14:00", "afternoon")
        e3 = _make_entry(journal, "2024-01-06 10:00", "next day")

        result = SummaryExporter._get_daily_stats([e1, e2, e3])

        assert len(result) == 2
        date_counts = dict(result)
        assert date_counts["01-05"] == 2
        assert date_counts["01-06"] == 1

    def test_daily_stats_empty(self, journal):
        result = SummaryExporter._get_daily_stats([])
        assert result == []


class TestGetTopEntries:
    def test_top_entries_starred_first(self, journal):
        e1 = _make_entry(journal, "2024-01-01 09:00", "normal @work")
        e2 = _make_entry(journal, "2024-01-02 09:00", "starred @work", starred=True)

        result = SummaryExporter._get_top_entries([e1, e2])

        assert result[0].starred is True

    def test_top_entries_limit_five(self, journal):
        entries = [
            _make_entry(journal, f"2024-01-{i+1:02d} 09:00", f"entry {i}")
            for i in range(1, 11)
        ]

        result = SummaryExporter._get_top_entries(entries)

        assert len(result) == 5

    def test_top_entries_empty(self, journal):
        result = SummaryExporter._get_top_entries([])
        assert result == []


class TestGenerateSummary:
    def test_empty_journal(self, journal):
        journal.entries = []
        result = SummaryExporter._generate_summary(journal, period="month")
        assert "No entries found" in result

    def test_summary_contains_sections(self, journal):
        e1 = _make_entry(journal, "2024-01-05 09:00", "TODO: work @work")
        e2 = _make_entry(journal, "2024-01-06 14:30", "read @personal", starred=True)
        journal.entries = [e1, e2]

        result = SummaryExporter._generate_summary(journal, period="month")

        assert "回顾摘要" in result
        assert "总体统计" in result
        assert "标签活跃度排行" in result
        assert "未完成事项汇总" in result

    def test_summary_month_period_key(self, journal):
        e1 = _make_entry(journal, "2024-01-05 09:00", "entry @work")
        e2 = _make_entry(journal, "2024-02-10 09:00", "entry @personal")
        journal.entries = [e1, e2]

        result = SummaryExporter._generate_summary(journal, period="month")

        assert "2024年 1月" in result
        assert "2024年 2月" in result

    def test_summary_week_period_key(self, journal):
        e1 = _make_entry(journal, "2024-01-01 09:00", "entry @work")
        journal.entries = [e1]

        result = SummaryExporter._generate_summary(journal, period="week")

        assert "第" in result
        assert "周" in result

    def test_summary_tag_trend_with_prev_period(self, journal):
        e1 = _make_entry(journal, "2024-01-05 09:00", "entry @work")
        e2 = _make_entry(journal, "2024-01-06 09:00", "entry @work @personal")
        e3 = _make_entry(journal, "2024-02-05 09:00", "entry @work @project @hobby")
        e4 = _make_entry(journal, "2024-02-06 09:00", "entry @work @project")
        journal.entries = [e1, e2, e3, e4]

        result = SummaryExporter._generate_summary(journal, period="month")

        assert "(+" in result or "(-" in result

    def test_summary_first_period_no_trend_parentheses(self, journal):
        e1 = _make_entry(journal, "2024-01-05 09:00", "entry @work @personal @hobby")
        journal.entries = [e1]

        result = SummaryExporter._generate_summary(journal, period="month")

        assert "(+" not in result
        assert "(-" not in result
        assert "@work" in result
        assert "@personal" in result


class TestSummaryControllerIntegration:
    @pytest.fixture
    def default_config(self):
        return {"display_format": None}

    def test_controller_summary_with_parse_args(self, journal, capsys, default_config):
        from jrnl.args import parse_args
        from jrnl.controller import _display_search_results

        journal.new_entry("TODO: first task @work")
        journal.new_entry("second entry @personal")

        mock_args = parse_args(["--summary"])
        _display_search_results(mock_args, journal, config=default_config)

        captured = capsys.readouterr()
        assert "回顾摘要" in captured.out
        assert "@work" in captured.out
        assert "@personal" in captured.out
        assert "总体统计" in captured.out

    def test_controller_summary_week_period(self, journal, capsys, default_config):
        from jrnl.args import parse_args
        from jrnl.controller import _display_search_results

        journal.new_entry("TODO: task @work")

        mock_args = parse_args(["--summary", "--summary-period", "week"])
        _display_search_results(mock_args, journal, config=default_config)

        captured = capsys.readouterr()
        assert "第" in captured.out
        assert "周" in captured.out

    def test_controller_summary_alias_format_summary(
        self, journal, capsys, default_config
    ):
        from jrnl.args import parse_args
        from jrnl.controller import _display_search_results

        journal.new_entry("entry @work")

        mock_args = parse_args(["--format", "summary"])
        _display_search_results(mock_args, journal, config=default_config)

        captured = capsys.readouterr()
        assert "回顾摘要" in captured.out
        assert "@work" in captured.out

    def test_controller_summary_trend_between_periods(
        self, journal, capsys, default_config
    ):
        from jrnl.args import parse_args
        from jrnl.controller import _display_search_results

        e1 = _make_entry(journal, "2024-01-05 09:00", "entry @work")
        e2 = _make_entry(
            journal, "2024-02-05 09:00", "entry @work @project @hobby"
        )
        journal.entries = [e1, e2]

        mock_args = parse_args(["--summary", "--summary-period", "month"])
        _display_search_results(mock_args, journal, config=default_config)

        captured = capsys.readouterr()
        assert "(+" in captured.out or "(-" in captured.out
