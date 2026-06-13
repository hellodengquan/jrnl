# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from jrnl.journals.Entry import Entry
from jrnl.journals.Journal import Journal
from jrnl.plugins.summary_exporter import SummaryExporter
from jrnl.plugins.summary_exporter import SummaryJSONExporter
from jrnl.plugins.summary_exporter import _detect_language


@pytest.fixture(autouse=True)
def force_zh_lang(monkeypatch):
    monkeypatch.setenv("JRNL_LANG", "zh_CN.UTF-8")


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
    def test_month_label_zh(self, monkeypatch):
        monkeypatch.setenv("JRNL_LANG", "zh")
        result = SummaryExporter._format_period_label("2024-03", "month")
        assert result == "2024年 3月"

    def test_month_label_en(self, monkeypatch):
        monkeypatch.setenv("JRNL_LANG", "en")
        result = SummaryExporter._format_period_label("2024-03", "month")
        assert result == "2024 March"

    def test_week_label_zh(self, monkeypatch):
        monkeypatch.setenv("JRNL_LANG", "zh")
        result = SummaryExporter._format_period_label("2024-W02", "week")
        assert "2024年" in result
        assert "第2周" in result

    def test_week_label_en(self, monkeypatch):
        monkeypatch.setenv("JRNL_LANG", "en")
        result = SummaryExporter._format_period_label("2024-W02", "week")
        assert "Week 2" in result

    def test_month_label_december_zh(self, monkeypatch):
        monkeypatch.setenv("JRNL_LANG", "zh")
        result = SummaryExporter._format_period_label("2024-12", "month")
        assert result == "2024年 12月"

    def test_month_label_december_en(self, monkeypatch):
        monkeypatch.setenv("JRNL_LANG", "en")
        result = SummaryExporter._format_period_label("2024-12", "month")
        assert result == "2024 December"


class TestI18n:
    def test_detect_language_zh_env(self, monkeypatch):
        monkeypatch.delenv("JRNL_LANG", raising=False)
        monkeypatch.delenv("LANG", raising=False)
        monkeypatch.setenv("JRNL_LANG", "zh_CN")
        assert _detect_language() == "zh"

    def test_detect_language_en_env(self, monkeypatch):
        monkeypatch.delenv("JRNL_LANG", raising=False)
        monkeypatch.delenv("LANG", raising=False)
        monkeypatch.setenv("JRNL_LANG", "en_US")
        assert _detect_language() == "en"

    def test_detect_language_from_lang_env(self, monkeypatch):
        monkeypatch.delenv("JRNL_LANG", raising=False)
        monkeypatch.delenv("LANG", raising=False)
        monkeypatch.setenv("LANG", "zh_TW.UTF-8")
        assert _detect_language() == "zh"

    def test_detect_language_default_en(self, monkeypatch):
        monkeypatch.delenv("JRNL_LANG", raising=False)
        monkeypatch.delenv("LANG", raising=False)
        assert _detect_language() == "en"

    def test_detect_language_fr_env(self, monkeypatch):
        monkeypatch.delenv("JRNL_LANG", raising=False)
        monkeypatch.delenv("LANG", raising=False)
        monkeypatch.setenv("JRNL_LANG", "fr_FR")
        assert _detect_language() == "fr"

    def test_detect_language_es_env(self, monkeypatch):
        monkeypatch.delenv("JRNL_LANG", raising=False)
        monkeypatch.delenv("LANG", raising=False)
        monkeypatch.setenv("JRNL_LANG", "es_ES")
        assert _detect_language() == "es"

    def test_detect_language_fr_from_lang_env(self, monkeypatch):
        monkeypatch.delenv("JRNL_LANG", raising=False)
        monkeypatch.delenv("LANG", raising=False)
        monkeypatch.setenv("LANG", "fr_CA.UTF-8")
        assert _detect_language() == "fr"

    def test_detect_language_es_from_lang_env(self, monkeypatch):
        monkeypatch.delenv("JRNL_LANG", raising=False)
        monkeypatch.delenv("LANG", raising=False)
        monkeypatch.setenv("LANG", "es_MX.UTF-8")
        assert _detect_language() == "es"

    def test_t_output_fr(self, monkeypatch):
        monkeypatch.setenv("JRNL_LANG", "fr")
        assert SummaryExporter._t("review_title") == "Résumé Périodique"
        assert SummaryExporter._t("overview") == "Statistiques Générales"

    def test_t_output_es(self, monkeypatch):
        monkeypatch.setenv("JRNL_LANG", "es")
        assert SummaryExporter._t("review_title") == "Resumen Periódico"
        assert SummaryExporter._t("overview") == "Estadísticas Generales"

    def test_t_no_entries_found_fr(self, monkeypatch):
        monkeypatch.setenv("JRNL_LANG", "fr")
        result = SummaryExporter._t("no_entries_found")
        assert "Aucune entrée trouvée" in result

    def test_t_no_entries_found_es(self, monkeypatch):
        monkeypatch.setenv("JRNL_LANG", "es")
        result = SummaryExporter._t("no_entries_found")
        assert "No se encontraron entradas" in result

    def test_summary_output_fr(self, journal, monkeypatch):
        monkeypatch.setenv("JRNL_LANG", "fr")
        journal.entries = [_make_entry(journal, "2024-01-05 09:00", "entry @work")]
        result = SummaryExporter._generate_summary(journal, period="month")
        assert "Résumé Périodique" in result
        assert "Statistiques Générales" in result

    def test_summary_output_es(self, journal, monkeypatch):
        monkeypatch.setenv("JRNL_LANG", "es")
        journal.entries = [_make_entry(journal, "2024-01-05 09:00", "entry @work")]
        result = SummaryExporter._generate_summary(journal, period="month")
        assert "Resumen Periódico" in result
        assert "Estadísticas Generales" in result

    def test_t_output_zh(self, monkeypatch):
        monkeypatch.setenv("JRNL_LANG", "zh")
        assert SummaryExporter._t("review_title") == "回顾摘要"
        assert SummaryExporter._t("overview") == "总体统计"

    def test_t_output_en(self, monkeypatch):
        monkeypatch.setenv("JRNL_LANG", "en")
        assert SummaryExporter._t("review_title") == "Periodic Review Summary"
        assert SummaryExporter._t("overview") == "Overview Statistics"

    def test_t_no_entries_found_zh(self, monkeypatch):
        monkeypatch.setenv("JRNL_LANG", "zh")
        result = SummaryExporter._t("no_entries_found")
        assert "未找到条目" in result

    def test_t_no_entries_found_en(self, monkeypatch):
        monkeypatch.setenv("JRNL_LANG", "en")
        result = SummaryExporter._t("no_entries_found")
        assert "No entries found" in result

    def test_summary_output_zh(self, journal, monkeypatch):
        monkeypatch.setenv("JRNL_LANG", "zh")
        journal.entries = [_make_entry(journal, "2024-01-05 09:00", "entry @work")]
        result = SummaryExporter._generate_summary(journal, period="month")
        assert "回顾摘要" in result
        assert "总体统计" in result

    def test_summary_output_en(self, journal, monkeypatch):
        monkeypatch.setenv("JRNL_LANG", "en")
        journal.entries = [_make_entry(journal, "2024-01-05 09:00", "entry @work")]
        result = SummaryExporter._generate_summary(journal, period="month")
        assert "Periodic Review Summary" in result
        assert "Overview Statistics" in result
        assert "Tag Activity Ranking" in result


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
    def test_empty_journal(self, journal, monkeypatch):
        monkeypatch.setenv("JRNL_LANG", "en")
        journal.entries = []
        result = SummaryExporter._generate_summary(journal, period="month")
        assert "No entries found" in result

    def test_summary_contains_sections_zh(self, journal, monkeypatch):
        monkeypatch.setenv("JRNL_LANG", "zh")
        e1 = _make_entry(journal, "2024-01-05 09:00", "TODO: work @work")
        e2 = _make_entry(journal, "2024-01-06 14:30", "read @personal", starred=True)
        journal.entries = [e1, e2]

        result = SummaryExporter._generate_summary(journal, period="month")

        assert "回顾摘要" in result
        assert "总体统计" in result
        assert "标签活跃度排行" in result
        assert "未完成事项汇总" in result

    def test_summary_contains_sections_en(self, journal, monkeypatch):
        monkeypatch.setenv("JRNL_LANG", "en")
        e1 = _make_entry(journal, "2024-01-05 09:00", "TODO: work @work")
        e2 = _make_entry(journal, "2024-01-06 14:30", "read @personal", starred=True)
        journal.entries = [e1, e2]

        result = SummaryExporter._generate_summary(journal, period="month")

        assert "Periodic Review Summary" in result
        assert "Overview Statistics" in result
        assert "Tag Activity Ranking" in result
        assert "Outstanding Todo Items" in result

    def test_summary_month_period_key_zh(self, journal, monkeypatch):
        monkeypatch.setenv("JRNL_LANG", "zh")
        e1 = _make_entry(journal, "2024-01-05 09:00", "entry @work")
        e2 = _make_entry(journal, "2024-02-10 09:00", "entry @personal")
        journal.entries = [e1, e2]

        result = SummaryExporter._generate_summary(journal, period="month")

        assert "2024年 1月" in result
        assert "2024年 2月" in result

    def test_summary_week_period_key_zh(self, journal, monkeypatch):
        monkeypatch.setenv("JRNL_LANG", "zh")
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


class TestSummaryJSON:
    def test_export_journal_json_empty(self, journal):
        journal.entries = []
        result = SummaryExporter.export_journal_json(journal, period="month")
        data = json.loads(result)
        assert data["version"] == "1.0.0"
        assert "schema" in data
        assert data["schema"]["version"] == "1.0.0"
        assert data["total_entries"] == 0
        assert data["periods"] == []
        assert data["sort"] is None

    def test_export_journal_json_structure(self, journal):
        e1 = _make_entry(journal, "2024-01-05 09:00", "TODO: task @work")
        journal.entries = [e1]

        result = SummaryExporter.export_journal_json(journal, period="month")
        data = json.loads(result)

        assert data["version"] == "1.0.0"
        assert "schema" in data
        assert data["schema"]["version"] == "1.0.0"
        assert "description" in data["schema"]
        assert "fields" in data["schema"]
        assert data["period"] == "month"
        assert data["total_entries"] == 1
        assert data["sort"] is None
        assert len(data["periods"]) == 1

        period = data["periods"][0]
        assert "period_key" in period
        assert "label" in period
        assert "label_en" in period
        assert "stats" in period
        assert period["stats"]["entries"] == 1
        assert period["stats"]["todos"] == 1
        assert "tags" in period
        assert "todos" in period
        assert "featured_entries" in period
        assert "daily_distribution" in period

    def test_export_journal_json_version_field(self, journal):
        from jrnl.plugins.summary_exporter import _SUMMARY_JSON_VERSION

        e1 = _make_entry(journal, "2024-01-05 09:00", "entry @work")
        journal.entries = [e1]

        result = SummaryExporter.export_journal_json(journal, period="month")
        data = json.loads(result)

        assert data["version"] == _SUMMARY_JSON_VERSION
        assert data["schema"]["version"] == _SUMMARY_JSON_VERSION

    def test_export_journal_json_schema_fields(self, journal):
        from jrnl.plugins.summary_exporter import _SUMMARY_JSON_SCHEMA

        e1 = _make_entry(journal, "2024-01-05 09:00", "entry @work")
        journal.entries = [e1]

        result = SummaryExporter.export_journal_json(journal, period="month")
        data = json.loads(result)

        assert data["schema"] == _SUMMARY_JSON_SCHEMA
        assert "version" in data["schema"]["fields"]
        assert "periods[].todos[].tags" in data["schema"]["fields"]
        assert "sort" in data["schema"]["fields"]

    def test_export_journal_json_sort_date(self, journal):
        e1 = _make_entry(journal, "2024-01-05 09:00", "TODO: older task @personal")
        e2 = _make_entry(journal, "2024-01-10 09:00", "TODO: newer task @work")
        journal.entries = [e1, e2]

        result = SummaryExporter.export_journal_json(journal, period="month", todo_sort="date")
        data = json.loads(result)

        assert data["sort"] == "date"
        todos = data["periods"][0]["todos"]
        assert len(todos) == 2
        assert todos[0]["date"] == "2024-01-10"
        assert todos[1]["date"] == "2024-01-05"

    def test_export_journal_json_sort_tag(self, journal):
        e1 = _make_entry(journal, "2024-01-05 09:00", "TODO: beta task @beta")
        e2 = _make_entry(journal, "2024-01-10 09:00", "TODO: alpha task @alpha")
        journal.entries = [e1, e2]

        result = SummaryExporter.export_journal_json(journal, period="month", todo_sort="tag")
        data = json.loads(result)

        assert data["sort"] == "tag"
        todos = data["periods"][0]["todos"]
        assert len(todos) == 2
        assert "@alpha" in str(todos[0]["tags"])
        assert "@beta" in str(todos[1]["tags"])
        assert todos[0]["tags"] is not None

    def test_export_journal_json_tag_trend(self, journal):
        e1 = _make_entry(journal, "2024-01-05 09:00", "entry @work")
        e2 = _make_entry(journal, "2024-02-05 09:00", "entry @work @hobby")
        journal.entries = [e1, e2]

        result = SummaryExporter.export_journal_json(journal, period="month")
        data = json.loads(result)

        assert len(data["periods"]) == 2
        latest = data["periods"][0]
        latest_tags = {t["tag"]: t for t in latest["tags"]}
        assert "@hobby" in latest_tags
        assert latest_tags["@hobby"]["trend"] == 1
        assert latest_tags["@hobby"]["previous_count"] == 0

    def test_export_journal_json_no_prev_period_trend_is_null(self, journal):
        e1 = _make_entry(journal, "2024-01-05 09:00", "entry @work")
        journal.entries = [e1]

        result = SummaryExporter.export_journal_json(journal, period="month")
        data = json.loads(result)
        period = data["periods"][0]

        for tag in period["tags"]:
            assert tag["previous_count"] is None
            assert tag["trend"] is None

    def test_summary_json_exporter_names(self):
        assert "summary_json" in SummaryJSONExporter.names
        assert SummaryJSONExporter.extension == "json"

    def test_summary_json_exporter_export_journal(self, journal):
        e1 = _make_entry(journal, "2024-01-05 09:00", "entry @work")
        journal.entries = [e1]

        result = SummaryJSONExporter.export_journal(journal)
        data = json.loads(result)
        assert data["version"] == "1.0.0"
        assert data["period"] == "month"
        assert data["total_entries"] == 1


class TestTodoSorting:
    def test_find_todo_items_sort_date_newest_first(self, journal):
        e1 = _make_entry(journal, "2024-01-05 09:00", "TODO: older @work")
        e2 = _make_entry(journal, "2024-01-15 09:00", "TODO: newer @personal")
        e3 = _make_entry(journal, "2024-01-10 09:00", "TODO: middle @work")
        entries = [e1, e2, e3]

        result = SummaryExporter._find_todo_items(entries, sort="date")

        assert result[0]["date"] > result[1]["date"]
        assert result[1]["date"] > result[2]["date"]
        assert result[0]["title"] == "TODO: newer @personal"

    def test_find_todo_items_sort_tag_alphabetical(self, journal):
        e1 = _make_entry(journal, "2024-01-05 09:00", "TODO: charlie @charlie")
        e2 = _make_entry(journal, "2024-01-05 09:00", "TODO: alpha @alpha")
        e3 = _make_entry(journal, "2024-01-05 09:00", "TODO: beta @beta")
        entries = [e1, e2, e3]

        result = SummaryExporter._find_todo_items(entries, sort="tag")

        assert "tags" in result[0]
        assert result[0]["tags"][0] == "@alpha"
        assert result[1]["tags"][0] == "@beta"
        assert result[2]["tags"][0] == "@charlie"

    def test_find_todo_items_sort_tag_with_multiple_tags(self, journal):
        e1 = _make_entry(journal, "2024-01-05 09:00", "TODO: zulu @zulu @alpha")
        e2 = _make_entry(journal, "2024-01-05 09:00", "TODO: beta @beta @gamma")
        entries = [e1, e2]

        result = SummaryExporter._find_todo_items(entries, sort="tag")

        assert result[0]["tags"][0] == "@alpha"
        assert result[1]["tags"][0] == "@beta"
        assert len(result[0]["tags"]) == 2
        assert "@zulu" in result[0]["tags"]
        assert "@gamma" in result[1]["tags"]

    def test_find_todo_items_sort_tag_no_tags(self, journal):
        e1 = _make_entry(journal, "2024-01-05 09:00", "TODO: no tags")
        e2 = _make_entry(journal, "2024-01-05 09:00", "TODO: alpha @alpha")
        entries = [e1, e2]

        result = SummaryExporter._find_todo_items(entries, sort="tag")

        assert result[0]["tags"] == []
        assert result[1]["tags"][0] == "@alpha"

    def test_generate_summary_todo_sort_date(self, journal, monkeypatch):
        monkeypatch.setenv("JRNL_LANG", "en")
        e1 = _make_entry(journal, "2024-01-05 09:00", "TODO: older @work")
        e2 = _make_entry(journal, "2024-01-15 09:00", "TODO: newer @personal")
        journal.entries = [e1, e2]

        result = SummaryExporter._generate_summary(journal, period="month", todo_sort="date")

        assert "Outstanding Todo Items" in result
        lines = result.split("\n")
        todo_lines = [l for l in lines if l.strip().startswith("1.") or l.strip().startswith("2.")]
        todo_lines = [l for l in todo_lines if "TODO" in l]
        assert len(todo_lines) == 2
        assert "01-15" in todo_lines[0]
        assert "01-05" in todo_lines[1]

    def test_generate_summary_todo_sort_tag(self, journal, monkeypatch):
        monkeypatch.setenv("JRNL_LANG", "en")
        e1 = _make_entry(journal, "2024-01-05 09:00", "TODO: beta @beta")
        e2 = _make_entry(journal, "2024-01-10 09:00", "TODO: alpha @alpha")
        journal.entries = [e1, e2]

        result = SummaryExporter._generate_summary(journal, period="month", todo_sort="tag")

        assert "Outstanding Todo Items" in result
        lines = result.split("\n")
        todo_lines = [l for l in lines if l.strip().startswith("1.") or l.strip().startswith("2.")]
        todo_lines = [l for l in todo_lines if "TODO" in l]
        assert len(todo_lines) == 2
        assert "alpha" in todo_lines[0]
        assert "beta" in todo_lines[1]


class TestSummaryControllerIntegration:
    @pytest.fixture
    def default_config(self):
        return {"display_format": None}

    def test_controller_summary_with_parse_args(
        self, journal, capsys, default_config, monkeypatch
    ):
        from jrnl.args import parse_args
        from jrnl.controller import _display_search_results

        monkeypatch.setenv("JRNL_LANG", "zh")
        journal.new_entry("TODO: first task @work")
        journal.new_entry("second entry @personal")

        mock_args = parse_args(["--summary"])
        _display_search_results(mock_args, journal, config=default_config)

        captured = capsys.readouterr()
        assert "回顾摘要" in captured.out
        assert "@work" in captured.out
        assert "@personal" in captured.out
        assert "总体统计" in captured.out

    def test_controller_summary_week_period(
        self, journal, capsys, default_config, monkeypatch
    ):
        from jrnl.args import parse_args
        from jrnl.controller import _display_search_results

        monkeypatch.setenv("JRNL_LANG", "zh")
        journal.new_entry("TODO: task @work")

        mock_args = parse_args(["--summary", "--summary-period", "week"])
        _display_search_results(mock_args, journal, config=default_config)

        captured = capsys.readouterr()
        assert "第" in captured.out
        assert "周" in captured.out

    def test_controller_summary_alias_format_summary(
        self, journal, capsys, default_config, monkeypatch
    ):
        from jrnl.args import parse_args
        from jrnl.controller import _display_search_results

        monkeypatch.setenv("JRNL_LANG", "zh")
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

    def test_controller_summary_json_format(
        self, journal, capsys, default_config
    ):
        from jrnl.args import parse_args
        from jrnl.controller import _display_search_results

        e1 = _make_entry(journal, "2024-01-05 09:00", "TODO: task @work")
        journal.entries = [e1]

        mock_args = parse_args(["--format", "summary_json"])
        _display_search_results(mock_args, journal, config=default_config)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["version"] == "1.0.0"
        assert data["period"] == "month"
        assert data["total_entries"] == 1

    def test_controller_summary_todo_sort_date(
        self, journal, capsys, default_config, monkeypatch
    ):
        from jrnl.args import parse_args
        from jrnl.controller import _display_search_results

        monkeypatch.setenv("JRNL_LANG", "en")
        e1 = _make_entry(journal, "2024-01-05 09:00", "TODO: older @work")
        e2 = _make_entry(journal, "2024-01-15 09:00", "TODO: newer @personal")
        journal.entries = [e1, e2]

        mock_args = parse_args(["--summary", "--summary-todo-sort", "date"])
        _display_search_results(mock_args, journal, config=default_config)

        captured = capsys.readouterr()
        assert "Outstanding Todo Items" in captured.out
        lines = captured.out.split("\n")
        todo_lines = [l for l in lines if l.strip().startswith("1.") or l.strip().startswith("2.")]
        todo_lines = [l for l in todo_lines if "TODO" in l]
        assert len(todo_lines) == 2
        assert "01-15" in todo_lines[0]
        assert "01-05" in todo_lines[1]

    def test_controller_summary_json_todo_sort_tag(
        self, journal, capsys, default_config
    ):
        from jrnl.args import parse_args
        from jrnl.controller import _display_search_results

        e1 = _make_entry(journal, "2024-01-05 09:00", "TODO: beta @beta")
        e2 = _make_entry(journal, "2024-01-10 09:00", "TODO: alpha @alpha")
        journal.entries = [e1, e2]

        mock_args = parse_args(["--format", "summary_json", "--summary-todo-sort", "tag"])
        _display_search_results(mock_args, journal, config=default_config)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["sort"] == "tag"
        todos = data["periods"][0]["todos"]
        assert len(todos) == 2
        assert "@alpha" in str(todos[0]["tags"])
        assert "@beta" in str(todos[1]["tags"])


class TestSubprocessSmoke:
    @pytest.fixture
    def test_env(self):
        tmpdir = tempfile.mkdtemp()
        journal_path = os.path.join(tmpdir, "test.journal")
        config_path = os.path.join(tmpdir, "jrnl.yaml")

        config_content = (
            "journals:\n"
            "  default:\n"
            f"    journal: {journal_path}\n"
            "    encrypt: false\n"
            "    tagsymbols: '@'\n"
            "    timeformat: '%Y-%m-%d %H:%M'\n"
            "    highlight: false\n"
            "    linewrap: false\n"
        )
        with open(config_path, "w") as f:
            f.write(config_content)

        journal_content = (
            "[2024-01-05 09:00] TODO: code review @work\n\n"
            "[2024-01-06 14:30] Read book @personal @reading *\n\n"
            "[2024-02-05 10:00] * [ ] Plan Q2 goals @work @project\n"
        )
        with open(journal_path, "w") as f:
            f.write(journal_content)

        yield {
            "tmpdir": tmpdir,
            "config_path": config_path,
            "journal_path": journal_path,
        }

        import shutil

        shutil.rmtree(tmpdir)

    def test_subprocess_summary_month(self, test_env):
        env = os.environ.copy()
        env["JRNL_LANG"] = "en"
        env["PYTHONPATH"] = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "jrnl",
                "--config-file",
                test_env["config_path"],
                "--summary",
            ],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "Periodic Review Summary" in result.stdout
        assert "@work" in result.stdout

    def test_subprocess_summary_week(self, test_env):
        env = os.environ.copy()
        env["JRNL_LANG"] = "en"
        env["PYTHONPATH"] = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "jrnl",
                "--config-file",
                test_env["config_path"],
                "--summary",
                "--summary-period",
                "week",
            ],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "Week" in result.stdout

    def test_subprocess_summary_json(self, test_env):
        env = os.environ.copy()
        env["JRNL_LANG"] = "en"
        env["PYTHONPATH"] = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "jrnl",
                "--config-file",
                test_env["config_path"],
                "--format",
                "summary_json",
            ],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        data = json.loads(result.stdout)
        assert "period" in data
        assert "periods" in data
        assert data["total_entries"] == 3

    def test_subprocess_summary_zh_output(self, test_env):
        env = os.environ.copy()
        env["JRNL_LANG"] = "zh_CN.UTF-8"
        env["PYTHONPATH"] = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "jrnl",
                "--config-file",
                test_env["config_path"],
                "--summary",
            ],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "回顾摘要" in result.stdout
        assert "总体统计" in result.stdout
        assert "@work" in result.stdout

    def test_subprocess_summary_format_alias(self, test_env):
        env = os.environ.copy()
        env["JRNL_LANG"] = "en"
        env["PYTHONPATH"] = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "jrnl",
                "--config-file",
                test_env["config_path"],
                "--format",
                "summary",
            ],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "Periodic Review Summary" in result.stdout
        assert "@work" in result.stdout

    def test_subprocess_summary_json_empty_journal(self):
        tmpdir = tempfile.mkdtemp()
        journal_path = os.path.join(tmpdir, "empty.journal")
        config_path = os.path.join(tmpdir, "jrnl.yaml")

        config_content = (
            "journals:\n"
            "  default:\n"
            f"    journal: {journal_path}\n"
            "    encrypt: false\n"
            "    tagsymbols: '@'\n"
            "    timeformat: '%Y-%m-%d %H:%M'\n"
            "    highlight: false\n"
            "    linewrap: false\n"
        )
        with open(config_path, "w") as f:
            f.write(config_content)

        with open(journal_path, "w") as f:
            f.write("")

        env = os.environ.copy()
        env["JRNL_LANG"] = "en"
        env["PYTHONPATH"] = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )

        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "jrnl",
                    "--config-file",
                    config_path,
                    "--format",
                    "summary_json",
                ],
                capture_output=True,
                text=True,
                env=env,
            )

            assert result.returncode == 0, f"stderr: {result.stderr}"
        finally:
            import shutil

            shutil.rmtree(tmpdir)

    def test_subprocess_summary_json_period_week(self, test_env):
        env = os.environ.copy()
        env["JRNL_LANG"] = "en"
        env["PYTHONPATH"] = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "jrnl",
                "--config-file",
                test_env["config_path"],
                "--format",
                "summary_json",
                "--summary-period",
                "week",
            ],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        data = json.loads(result.stdout)
        assert data["period"] == "week"
        assert data["total_entries"] == 3
        assert len(data["periods"]) >= 1
