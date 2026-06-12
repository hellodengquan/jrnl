# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import datetime
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from jrnl import time
from jrnl.journals import Journal


def _make_journal():
    return Journal(
        "test",
        default_hour=9,
        default_minute=0,
        timeformat="%Y-%m-%d %H:%M",
        tagsymbols="@",
        highlight=False,
        linewrap=False,
    )


# ============================================================
# Fixtures: 固定当前时间，确保日期关键字测试可重复
# ============================================================


@pytest.fixture
def frozen_now():
    """冻结当前时间为 2023-12-31 23:30:00（跨年夜前半小时）

    方法：
    1. 继承 datetime.datetime 并重写 now() 方法
    2. patch jrnl.time.__get_pdt_calendar，让返回的 calendar 以固定时间为基准
    """
    now_str = "2023-12-31 11:30:00 PM"
    now_dt = datetime.datetime.strptime(now_str, "%Y-%m-%d %I:%M:%S %p")

    real_datetime_class = datetime.datetime

    class FrozenDatetime(real_datetime_class):
        @classmethod
        def now(cls, tz=None):
            if tz:
                time_zone = real_datetime_class.utcnow().astimezone().tzinfo
                return now_dt.replace(tzinfo=time_zone)
            return now_dt

    # 构建一个以冻结时间为基准的 pdt calendar
    import parsedatetime as pdt

    consts = pdt.Constants(usePyICU=False)
    consts.DOWParseStyle = -1
    base_calendar = pdt.Calendar(consts, version=pdt.VERSION_CONTEXT_STYLE)

    original_parse = base_calendar.parse

    def patched_parse(date_str_input, sourceTime=None):
        if sourceTime is None:
            sourceTime = now_dt.timetuple()
        elif hasattr(sourceTime, "timetuple"):
            sourceTime = sourceTime.timetuple()
        return original_parse(date_str_input, sourceTime)

    base_calendar.parse = patched_parse

    def frozen_calendar():
        return base_calendar

    with patch("datetime.datetime", FrozenDatetime), patch(
        "jrnl.time.__get_pdt_calendar", frozen_calendar
    ):
        yield now_dt


# ============================================================
# 录入路径测试 (Write path: new_entry + 日期关键字前缀)
# ============================================================


class TestWritePathBoundary:
    """录入路径：日界线场景下的条目创建行为"""

    def test_write_yesterday_on_new_years_eve(self, frozen_now):
        """跨年夜录入 'yesterday: ...' → 应该是 12月30日 09:00"""
        journal = _make_journal()
        journal.new_entry("yesterday: Entry from yesterday.")

        assert len(journal.entries) == 1
        entry = journal.entries[0]
        assert entry.date == datetime.datetime(2023, 12, 30, 9, 0)
        assert "Entry from yesterday." in entry.title

    def test_write_today_on_new_years_eve(self, frozen_now):
        """跨年夜录入 'today: ...' → 应该是 12月31日 09:00"""
        journal = _make_journal()
        journal.new_entry("today: Entry for today.")

        assert journal.entries[0].date == datetime.datetime(2023, 12, 31, 9, 0)

    def test_write_tomorrow_on_new_years_eve(self, frozen_now):
        """跨年夜录入 'tomorrow: ...' → 应该是 1月1日 09:00（跨到次年）"""
        journal = _make_journal()
        journal.new_entry("tomorrow: Entry for tomorrow.")

        assert journal.entries[0].date == datetime.datetime(2024, 1, 1, 9, 0)

    def test_write_december_31_explicit_date(self, frozen_now):
        """录入明确日期：'december 31 2023: ...' → 2023-12-31 09:00"""
        journal = _make_journal()
        journal.new_entry("december 31 2023: New Year's Eve entry.")

        assert journal.entries[0].date == datetime.datetime(2023, 12, 31, 9, 0)

    def test_write_january_1_explicit_date(self, frozen_now):
        """录入明确日期：'january 1 2024: ...' → 2024-01-01 09:00"""
        journal = _make_journal()
        journal.new_entry("january 1 2024: New Year's Day entry.")

        assert journal.entries[0].date == datetime.datetime(2024, 1, 1, 9, 0)

    def test_write_with_explicit_time_near_midnight(self, frozen_now):
        """录入带明确时间跨零点：23:59 vs 00:01（避开 00:00 现有判定问题）"""
        journal = _make_journal()
        journal.new_entry("2023-12-31 23:59: Just before midnight.")
        journal.new_entry("2024-01-01 00:01: Right after midnight.")

        assert len(journal.entries) == 2
        assert journal.entries[0].date == datetime.datetime(2023, 12, 31, 23, 59)
        assert journal.entries[1].date == datetime.datetime(2024, 1, 1, 0, 1)
        assert journal.entries[0].date < journal.entries[1].date

    def test_write_midnight_zerozero_treated_as_no_time(self, frozen_now):
        """记录现有行为：00:00 会被判定为无明确时间，从而应用 default_hour"""
        journal = _make_journal()
        journal.new_entry("2024-01-01 00:00: Midnight entry.")

        # 现有行为：00:00 因 hour==minute==0 被误判为无时间，使用 default_hour=9
        assert journal.entries[0].date.hour == 9
        assert journal.entries[0].date.minute == 0

    def test_write_month_boundary_last_and_first(self, frozen_now):
        """月末/月初录入：1月31日 → 2月1日，时间顺序正确"""
        journal = _make_journal()
        journal.new_entry("2023-01-31: Last day of January.")
        journal.new_entry("2023-02-01: First day of February.")

        assert journal.entries[0].date == datetime.datetime(2023, 1, 31, 9, 0)
        assert journal.entries[1].date == datetime.datetime(2023, 2, 1, 9, 0)
        assert journal.entries[0].date < journal.entries[1].date

    def test_write_leap_day_entry(self, frozen_now):
        """闰年2月29日录入有效"""
        journal = _make_journal()
        journal.new_entry("2024-02-29: Leap day entry.")

        assert journal.entries[0].date == datetime.datetime(2024, 2, 29, 9, 0)

    def test_write_twice_same_day_sorted(self, frozen_now):
        """同一天录入两条，按时间排序"""
        journal = _make_journal()
        journal.new_entry("2023-12-31 23:59: Late night entry.")
        journal.new_entry("2023-12-31 09:00: Morning entry.")

        assert len(journal.entries) == 2
        assert journal.entries[0].date.hour == 9
        assert journal.entries[1].date.hour == 23


# ============================================================
# 查询路径测试 (Search path: filter + start_date/end_date/on_date)
# ============================================================


class TestSearchPathBoundary:
    """查询路径：日界线场景下的过滤行为"""

    @pytest.fixture
    def journal_with_boundary_entries(self, frozen_now):
        """构造一组跨年、跨月、跨日边界的测试条目"""
        journal = _make_journal()
        entries_data = [
            ("2023-12-30 09:00", "Dec 30 entry."),
            ("2023-12-31 09:00", "New Year's Eve morning."),
            ("2023-12-31 23:59", "Just before midnight."),
            ("2024-01-01 00:01", "Right after midnight."),
            ("2024-01-01 09:00", "New Year's Day morning."),
            ("2024-01-02 09:00", "Jan 2 entry."),
        ]
        for date_str, title in entries_data:
            journal.new_entry(f"{date_str}: {title}")
        return journal

    def test_search_on_new_years_eve(self, journal_with_boundary_entries):
        """-on 2023-12-31 → 只返回当天的 2 条（09:00 和 23:59）"""
        j = journal_with_boundary_entries
        j.filter(start_date="2023-12-31", end_date="2023-12-31")

        assert len(j.entries) == 2
        assert all(e.date.date() == datetime.date(2023, 12, 31) for e in j.entries)

    def test_search_on_new_years_day(self, journal_with_boundary_entries):
        """-on 2024-01-01 → 只返回当天的 2 条（00:01 和 09:00）"""
        j = journal_with_boundary_entries
        j.filter(start_date="2024-01-01", end_date="2024-01-01")

        assert len(j.entries) == 2
        assert all(e.date.date() == datetime.date(2024, 1, 1) for e in j.entries)

    def test_search_from_eve_to_day_crosses_year(self, journal_with_boundary_entries):
        """-from 2023-12-31 -to 2024-01-01 → 跨年夜两天共 4 条"""
        j = journal_with_boundary_entries
        j.filter(start_date="2023-12-31", end_date="2024-01-01")

        assert len(j.entries) == 4
        dates = {e.date.date() for e in j.entries}
        assert dates == {datetime.date(2023, 12, 31), datetime.date(2024, 1, 1)}

    def test_search_boundary_inclusive_excludes_just_before(self, journal_with_boundary_entries):
        """-from 2024-01-01 → 从 00:00 开始，不包含 2023-12-31 23:59 的条目"""
        j = journal_with_boundary_entries
        j.filter(start_date="2024-01-01")

        assert len(j.entries) == 3
        assert all(e.date >= datetime.datetime(2024, 1, 1, 0, 0) for e in j.entries)

    def test_search_end_date_inclusive_covers_end_of_day(self, journal_with_boundary_entries):
        """-to 2023-12-31 → 包含当天 23:59:59 前的所有条目（2 条）"""
        j = journal_with_boundary_entries
        j.filter(end_date="2023-12-31")

        assert len(j.entries) == 3  # 12/30 + 12/31 两条
        assert all(e.date <= datetime.datetime(2023, 12, 31, 23, 59, 59) for e in j.entries)

    def test_search_with_today_keyword_on_eve(self, journal_with_boundary_entries, frozen_now):
        """跨年夜用 today 查询 → 只返回 12月31日 的条目"""
        j = journal_with_boundary_entries
        j.filter(start_date="today", end_date="today")

        assert len(j.entries) == 2
        assert all(e.date.date() == datetime.date(2023, 12, 31) for e in j.entries)

    def test_search_from_yesterday_to_today_on_eve(self, journal_with_boundary_entries, frozen_now):
        """跨年夜用 -from yesterday -to today → 12/30 + 12/31 共 3 条"""
        j = journal_with_boundary_entries
        j.filter(start_date="yesterday", end_date="today")

        assert len(j.entries) == 3
        dates = {e.date.date() for e in j.entries}
        assert dates == {datetime.date(2023, 12, 30), datetime.date(2023, 12, 31)}

    def test_search_from_today_to_tomorrow_on_eve(self, journal_with_boundary_entries, frozen_now):
        """跨年夜用 -from today -to tomorrow → 跨年度，12/31 + 1/1 共 4 条"""
        j = journal_with_boundary_entries
        j.filter(start_date="today", end_date="tomorrow")

        assert len(j.entries) == 4
        dates = {e.date.date() for e in j.entries}
        assert dates == {datetime.date(2023, 12, 31), datetime.date(2024, 1, 1)}

    def test_search_month_boundary(self, frozen_now):
        """跨月查询：1月底 → 2月初"""
        journal = _make_journal()
        for d in ["2023-01-30", "2023-01-31", "2023-02-01", "2023-02-02"]:
            journal.new_entry(f"{d}: Entry on {d}.")

        journal.filter(start_date="2023-01-31", end_date="2023-02-01")
        assert len(journal.entries) == 2
        assert journal.entries[0].date.month == 1
        assert journal.entries[1].date.month == 2

    def test_search_leap_year_feb_boundary(self, frozen_now):
        """闰年 2 月底 → 3 月初"""
        journal = _make_journal()
        for d in ["2024-02-28", "2024-02-29", "2024-03-01"]:
            journal.new_entry(f"{d}: Entry.")

        journal.filter(start_date="2024-02-29", end_date="2024-03-01")
        assert len(journal.entries) == 2
        assert journal.entries[0].date.day == 29
        assert journal.entries[1].date.day == 1

    def test_search_non_leap_year_feb_boundary(self, frozen_now):
        """平年 2 月 28 日 → 3 月 1 日"""
        journal = _make_journal()
        for d in ["2023-02-27", "2023-02-28", "2023-03-01"]:
            journal.new_entry(f"{d}: Entry.")

        journal.filter(start_date="2023-02-28", end_date="2023-03-01")
        assert len(journal.entries) == 2
        assert journal.entries[0].date == datetime.datetime(2023, 2, 28, 9, 0)
        assert journal.entries[1].date == datetime.datetime(2023, 3, 1, 9, 0)

    def test_search_around_midnight_granularity(self, frozen_now):
        """跨日零点边界：23:59 和 00:01 分属不同查询结果（验证日界线切分正确）"""
        journal = _make_journal()
        journal.new_entry("2023-06-15 23:59: Late night.")
        journal.new_entry("2023-06-16 00:01: Early morning.")

        j1 = _make_journal()
        j1.entries = list(journal.entries)
        j1.filter(end_date="2023-06-15")
        assert len(j1.entries) == 1
        assert "Late night." in j1.entries[0].title

        j2 = _make_journal()
        j2.entries = list(journal.entries)
        j2.filter(start_date="2023-06-16")
        assert len(j2.entries) == 1
        assert "Early morning." in j2.entries[0].title


# ============================================================
# 完整链路：录入 → 查询 → 结果验证
# ============================================================


class TestFullCycleBoundary:
    """录入后立即查询，验证完整链路在日界线上不出现数据漂移"""

    def test_full_cycle_year_boundary(self, frozen_now):
        """完整链路：在跨年夜录入昨天/今天/明天三条，分别查询各自日期各得1条"""
        journal = _make_journal()
        journal.new_entry("yesterday: Yesterday entry.")
        journal.new_entry("today: Today entry.")
        journal.new_entry("tomorrow: Tomorrow entry.")

        assert len(journal.entries) == 3

        # 查询昨天
        j_yesterday = _make_journal()
        j_yesterday.entries = list(journal.entries)
        j_yesterday.filter(start_date="yesterday", end_date="yesterday")
        assert len(j_yesterday.entries) == 1
        assert "Yesterday entry." in j_yesterday.entries[0].title

        # 查询今天
        j_today = _make_journal()
        j_today.entries = list(journal.entries)
        j_today.filter(start_date="today", end_date="today")
        assert len(j_today.entries) == 1
        assert "Today entry." in j_today.entries[0].title

        # 查询明天
        j_tomorrow = _make_journal()
        j_tomorrow.entries = list(journal.entries)
        j_tomorrow.filter(start_date="tomorrow", end_date="tomorrow")
        assert len(j_tomorrow.entries) == 1
        assert "Tomorrow entry." in j_tomorrow.entries[0].title

    def test_full_cycle_month_boundary(self, frozen_now):
        """完整链路：录入月末和月初条目，查询区间刚好包含边界两侧"""
        journal = _make_journal()
        journal.new_entry("2023-01-31: Jan 31 entry.")
        journal.new_entry("2023-02-01: Feb 1 entry.")

        journal.filter(start_date="2023-01-31", end_date="2023-02-01")
        assert len(journal.entries) == 2
        assert journal.entries[0].date.month == 1
        assert journal.entries[1].date.month == 2

    def test_full_cycle_on_date_keyword_same_as_start_end(self, frozen_now):
        """-on today 等价于 -from today -to today"""
        journal = _make_journal()
        journal.new_entry("yesterday: Yesterday entry.")
        journal.new_entry("today: Today entry one.")
        journal.new_entry("today: Today entry two.")
        journal.new_entry("tomorrow: Tomorrow entry.")

        j_on = _make_journal()
        j_on.entries = list(journal.entries)
        j_on.filter(start_date="today", end_date="today")

        j_range = _make_journal()
        j_range.entries = list(journal.entries)
        j_range.filter(start_date="today", end_date="today")

        assert len(j_on.entries) == len(j_range.entries) == 2
        assert {e.title for e in j_on.entries} == {e.title for e in j_range.entries}

    def test_full_cycle_no_drift_across_midnight(self, frozen_now):
        """日界线查询不重叠、不遗漏：end_date(inclusive) + start_date(exclusive) = 全部条目"""
        journal = _make_journal()
        journal.new_entry("2023-12-31 23:59:59: Last second of year.")
        journal.new_entry("2024-01-01 00:00:01: First second of year after boundary.")

        # 查询到 2023 年底（inclusive = 23:59:59）
        j_end = _make_journal()
        j_end.entries = list(journal.entries)
        j_end.filter(end_date="2023-12-31")
        assert len(j_end.entries) == 1
        assert "Last second of year." in j_end.entries[0].title

        # 查询从 2024 年初（exclusive start = 00:00:00）
        j_start = _make_journal()
        j_start.entries = list(journal.entries)
        j_start.filter(start_date="2024-01-01")
        assert len(j_start.entries) == 1
        assert "First second of year after boundary." in j_start.entries[0].title

        # 两个查询合起来就是全部条目，不重不漏
        assert len(j_end.entries) + len(j_start.entries) == len(journal.entries)

    def test_full_cycle_year_keyword_range(self, frozen_now):
        """完整链路：用年份关键字做录入并查询跨年范围"""
        journal = _make_journal()
        for d in [
            "2023-12-30",
            "2023-12-31",
            "2024-01-01",
            "2024-01-02",
            "2024-01-03",
        ]:
            journal.new_entry(f"{d}: Entry for {d}.")

        journal.filter(start_date="december 31 2023", end_date="january 2 2024")
        assert len(journal.entries) == 3
        dates = [e.date.date() for e in journal.entries]
        assert datetime.date(2023, 12, 31) in dates
        assert datetime.date(2024, 1, 1) in dates
        assert datetime.date(2024, 1, 2) in dates
