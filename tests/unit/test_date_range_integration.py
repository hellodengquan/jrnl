# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import datetime
from unittest.mock import patch

import pytest

import jrnl.time as jrnl_time_module
from jrnl import time
from jrnl.journals import Journal


@pytest.fixture
def populated_journal(tmp_path):
    """创建一个包含已知日期条目的测试 journal。"""
    journal_path = tmp_path / "test.journal"
    journal = Journal("test", journal=str(journal_path))

    entries_data = [
        (datetime.datetime(2019, 7, 1, 14, 23), "2019 Canada Day entry"),
        (datetime.datetime(2020, 8, 29, 10, 0), "August 29 morning entry"),
        (datetime.datetime(2020, 8, 31, 15, 30), "August 31 afternoon entry"),
        (datetime.datetime(2020, 9, 24, 9, 0), "September work entry"),
        (datetime.datetime(2021, 1, 1, 0, 1), "New Year 2021"),
    ]

    for d, title in entries_data:
        journal.new_entry(title, date=d)

    assert len(journal) == 5
    return journal


class TestDateRangeFilterIntegration:
    """端到端集成测试：通过 parse_date_range -> DateRange -> Journal.filter
    验证完整的日期范围过滤链路。"""

    def test_scenario_no_constraints_empty_range(self, populated_journal):
        """场景 8: 无约束 — 应返回全部 5 条。"""
        date_range = time.parse_date_range()
        populated_journal.filter(date_range=date_range)
        assert len(populated_journal) == 5

    def test_scenario_on_specific_date(self, populated_journal):
        """场景 1: -on 2020-08-31 — 应只返回 8 月 31 日的 1 条。"""
        date_range = time.parse_date_range(on_date="2020-08-31")
        populated_journal.filter(date_range=date_range)
        assert len(populated_journal) == 1
        assert populated_journal.entries[0].date == datetime.datetime(
            2020, 8, 31, 15, 30
        )
        assert "August 31" in populated_journal.entries[0].title

    def test_scenario_from_to_range(self, populated_journal):
        """场景 2: -from 2020-08-01 -to 2020-08-31 — 应返回 8 月的 2 条。"""
        date_range = time.parse_date_range(
            start_date="2020-08-01", end_date="2020-08-31"
        )
        populated_journal.filter(date_range=date_range)
        assert len(populated_journal) == 2
        titles = {e.title for e in populated_journal.entries}
        assert "August 29 morning entry" in titles
        assert "August 31 afternoon entry" in titles

    def test_scenario_month_numeric(self, populated_journal):
        """场景 3: -month 8 (数字) — 应返回所有年份 8 月的 2 条。"""
        date_range = time.parse_date_range(month="8")
        populated_journal.filter(date_range=date_range)
        assert len(populated_journal) == 2
        for e in populated_journal.entries:
            assert e.date.month == 8

    def test_scenario_year(self, populated_journal):
        """场景 4: -year 2020 — 应返回 2020 年的 3 条。"""
        date_range = time.parse_date_range(year="2020")
        populated_journal.filter(date_range=date_range)
        assert len(populated_journal) == 3
        for e in populated_journal.entries:
            assert e.date.year == 2020

    def test_scenario_today_in_history_parse_flag(self, monkeypatch):
        """场景 5a: today-in-history 标志应让 parse_date_range 读取当前日期的月/日。"""
        fake_now = datetime.datetime(2025, 7, 1, 12, 0, 0)

        with patch.object(jrnl_time_module, "parse") as mock_parse:
            mock_parse.side_effect = lambda s, **kw: (
                fake_now if s == "now" else datetime.datetime(1, 1, 1)
            )
            date_range = time.parse_date_range(today_in_history=True)

        assert date_range.month == 7
        assert date_range.day == 1

    def test_scenario_today_in_history_filter(self, populated_journal):
        """场景 5b: today-in-history 等价于 -month 7 -day 1，应返回加拿大日那条。"""
        date_range = time.parse_date_range(month="7", day="1")
        populated_journal.filter(date_range=date_range)
        assert len(populated_journal) == 1
        assert populated_journal.entries[0].date.month == 7
        assert populated_journal.entries[0].date.day == 1
        assert "Canada Day" in populated_journal.entries[0].title

    def test_scenario_month_full_name(self, populated_journal):
        """场景 6: -month September (月份全名) — 应返回 9 月的 1 条。"""
        date_range = time.parse_date_range(month="September")
        populated_journal.filter(date_range=date_range)
        assert len(populated_journal) == 1
        assert populated_journal.entries[0].date.month == 9
        assert "September" in populated_journal.entries[0].title

    def test_scenario_month_short_name(self, populated_journal):
        """场景 6 补充: -month Jan (月份缩写) — 应返回 1 月的 1 条。"""
        date_range = time.parse_date_range(month="Jan")
        populated_journal.filter(date_range=date_range)
        assert len(populated_journal) == 1
        assert populated_journal.entries[0].date.month == 1
        assert "New Year" in populated_journal.entries[0].title

    def test_scenario_combined_month_day_year(self, populated_journal):
        """场景 7 补充: -month 8 -day 29 -year 2020 组合使用。"""
        date_range = time.parse_date_range(month="8", day="29", year="2020")
        populated_journal.filter(date_range=date_range)
        assert len(populated_journal) == 1
        entry = populated_journal.entries[0]
        assert entry.date.year == 2020
        assert entry.date.month == 8
        assert entry.date.day == 29
        assert "August 29" in entry.title

    def test_scenario_from_only(self, populated_journal):
        """边界: 只指定 -from，无 -to。"""
        date_range = time.parse_date_range(start_date="2020-09-01")
        populated_journal.filter(date_range=date_range)
        assert len(populated_journal) == 2
        for e in populated_journal.entries:
            assert e.date >= datetime.datetime(2020, 9, 1)

    def test_scenario_to_only(self, populated_journal):
        """边界: 只指定 -to，无 -from。"""
        date_range = time.parse_date_range(end_date="2019-12-31")
        populated_journal.filter(date_range=date_range)
        assert len(populated_journal) == 1
        assert populated_journal.entries[0].date.year == 2019

    def test_scenario_on_with_tags_and_strict(self, populated_journal):
        """确保 filter 其他参数（tags、strict）在新签名下仍正常工作。"""
        populated_journal.entries[1].tags = {"@vacation"}
        populated_journal.entries[2].tags = {"@vacation", "@beach"}

        date_range = time.parse_date_range(year="2020")
        populated_journal.filter(
            tags=["@vacation"], date_range=date_range, strict=True
        )
        assert len(populated_journal) == 2
        for e in populated_journal.entries:
            assert "@vacation" in {t.lower() for t in e.tags}

    def test_scenario_none_filter_argument(self, populated_journal):
        """边界: 显式传 None 作为 date_range 应等价于无约束。"""
        populated_journal.filter(date_range=None)
        assert len(populated_journal) == 5

    def test_scenario_out_of_order_start_end_auto_swapped(self, populated_journal):
        """边界: start > end 时 DateRange 应自动交换。"""
        date_range = time.parse_date_range(
            start_date="2020-12-31", end_date="2020-01-01"
        )
        populated_journal.filter(date_range=date_range)
        assert len(populated_journal) == 3
        for e in populated_journal.entries:
            assert e.date.year == 2020
