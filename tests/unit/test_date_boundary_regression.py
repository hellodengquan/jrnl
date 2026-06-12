# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import datetime

import pytest

from jrnl.controller import _filter_journal_entries
from jrnl.journals import Journal


@pytest.fixture
def journal():
    j = Journal(name="test", default_hour=9, default_minute=0, timeformat="%Y-%m-%d %H:%M")
    return j


def _make_entries(journal, *date_strs):
    for ds in date_strs:
        journal.new_entry(f"entry at {ds}", date=datetime.datetime.strptime(ds, "%Y-%m-%d %H:%M"))
    return journal


def _entry_dates(journal):
    return [e.date for e in journal.entries]


class TestQueryYearBoundary:
    """查询入口：-from/-to/-on 跨年过滤"""

    def test_from_dec31_to_jan1_returns_both(self, journal):
        _make_entries(journal, "2023-12-31 10:00", "2024-01-01 10:00", "2024-01-02 10:00")
        journal.filter(start_date="2023-12-31", end_date="2024-01-01")
        assert len(journal.entries) == 2
        dates = _entry_dates(journal)
        assert dates[0].year == 2023
        assert dates[1].year == 2024

    def test_from_jan1_excludes_previous_year(self, journal):
        _make_entries(journal, "2023-12-31 23:59", "2024-01-01 00:00")
        journal.filter(start_date="2024-01-01")
        assert len(journal.entries) == 1
        assert journal.entries[0].date.year == 2024

    def test_to_dec31_includes_last_moment_of_year(self, journal):
        _make_entries(journal, "2023-12-31 23:59", "2024-01-01 00:00")
        journal.filter(end_date="2023-12-31")
        assert len(journal.entries) == 1
        assert journal.entries[0].date.year == 2023

    def test_on_dec31_includes_only_that_day(self, journal):
        _make_entries(journal, "2023-12-30 10:00", "2023-12-31 10:00", "2024-01-01 10:00")
        journal.filter(start_date="2023-12-31", end_date="2023-12-31")
        assert len(journal.entries) == 1
        assert journal.entries[0].date.day == 31
        assert journal.entries[0].date.month == 12

    def test_cross_year_range_from_keyword(self, journal):
        _make_entries(journal, "2023-12-31 10:00", "2024-01-01 10:00")
        journal.filter(start_date="2023-12-31", end_date="today")
        assert len(journal.entries) == 2

    def test_year_boundary_entry_at_midnight(self, journal):
        _make_entries(journal, "2023-12-31 23:59", "2024-01-01 00:00", "2024-01-01 00:01")
        journal.filter(start_date="2024-01-01", end_date="2024-01-01")
        assert len(journal.entries) == 2
        for e in journal.entries:
            assert e.date.year == 2024


class TestQueryMonthBoundary:
    """查询入口：-from/-to/-on 跨月过滤"""

    @pytest.mark.parametrize(
        "end_of_month,start_of_next",
        [
            ("2023-01-31", "2023-02-01"),
            ("2023-02-28", "2023-03-01"),
            ("2024-02-29", "2024-03-01"),
            ("2023-04-30", "2023-05-01"),
            ("2023-06-30", "2023-07-01"),
            ("2023-09-30", "2023-10-01"),
            ("2023-11-30", "2023-12-01"),
        ],
    )
    def test_end_of_month_to_start_of_next_returns_both(self, journal, end_of_month, start_of_next):
        _make_entries(journal, end_of_month + " 10:00", start_of_next + " 10:00")
        journal.filter(start_date=end_of_month, end_date=start_of_next)
        assert len(journal.entries) == 2

    @pytest.mark.parametrize(
        "end_of_month,start_of_next",
        [
            ("2023-01-31", "2023-02-01"),
            ("2024-02-29", "2024-03-01"),
        ],
    )
    def test_end_of_month_boundary_no_overspill(self, journal, end_of_month, start_of_next):
        _make_entries(journal, end_of_month + " 23:59", start_of_next + " 00:00")
        journal.filter(end_date=end_of_month)
        assert len(journal.entries) == 1
        assert journal.entries[0].date.month == int(end_of_month.split("-")[1])

    def test_leap_year_feb_29_included_in_range(self, journal):
        _make_entries(journal, "2024-02-28 10:00", "2024-02-29 10:00", "2024-03-01 10:00")
        journal.filter(start_date="2024-02-29", end_date="2024-02-29")
        assert len(journal.entries) == 1
        assert journal.entries[0].date.day == 29

    def test_non_leap_year_feb_28_range(self, journal):
        _make_entries(journal, "2023-02-27 10:00", "2023-02-28 10:00", "2023-03-01 10:00")
        journal.filter(end_date="2023-02-28")
        assert len(journal.entries) == 2
        for e in journal.entries:
            assert e.date.month == 2

    def test_month_boundary_from_keyword(self, journal):
        _make_entries(journal, "2023-01-31 10:00", "2023-02-01 10:00")
        journal.filter(start_date="2023-01-31", end_date="today")
        assert len(journal.entries) == 2


class TestQueryDayBoundary:
    """查询入口：-from/-to/-on 跨日过滤（午夜边界）"""

    def test_from_today_excludes_yesterday_late_entry(self, journal):
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        yesterday_late = datetime.datetime.combine(yesterday, datetime.time(23, 59, 59))
        today_early = datetime.datetime.combine(datetime.date.today(), datetime.time(0, 0, 0))

        journal.new_entry("late yesterday", date=yesterday_late)
        journal.new_entry("early today", date=today_early)

        journal.filter(start_date="today")
        assert len(journal.entries) == 1
        assert journal.entries[0].date.date() == datetime.date.today()

    def test_to_yesterday_includes_yesterday_late_entry(self, journal):
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        yesterday_late = datetime.datetime.combine(yesterday, datetime.time(23, 59, 59))
        today_early = datetime.datetime.combine(datetime.date.today(), datetime.time(0, 0, 0))

        journal.new_entry("late yesterday", date=yesterday_late)
        journal.new_entry("early today", date=today_early)

        journal.filter(end_date="yesterday")
        assert len(journal.entries) == 1
        assert journal.entries[0].date.date() == yesterday

    def test_on_today_includes_entire_today(self, journal):
        today = datetime.date.today()
        early = datetime.datetime.combine(today, datetime.time(0, 0, 0))
        late = datetime.datetime.combine(today, datetime.time(23, 59, 59))
        yesterday = datetime.datetime.combine(
            today - datetime.timedelta(days=1), datetime.time(12, 0)
        )

        journal.new_entry("yesterday", date=yesterday)
        journal.new_entry("early today", date=early)
        journal.new_entry("late today", date=late)

        journal.filter(start_date="today", end_date="today")
        assert len(journal.entries) == 2
        for e in journal.entries:
            assert e.date.date() == today

    def test_midnight_boundaries_across_adjacent_days(self, journal):
        _make_entries(journal, "2023-06-15 23:59", "2023-06-16 00:00", "2023-06-16 00:01")
        journal.filter(start_date="2023-06-16", end_date="2023-06-16")
        assert len(journal.entries) == 2
        for e in journal.entries:
            assert e.date.day == 16

    def test_range_spanning_midnight(self, journal):
        _make_entries(journal, "2023-06-15 22:00", "2023-06-15 23:59", "2023-06-16 00:00", "2023-06-16 01:00")
        journal.filter(start_date="2023-06-15 22:00", end_date="2023-06-16 01:00")
        assert len(journal.entries) == 4


class TestQueryKeywordWithConcreteDate:
    """查询入口：日期关键字与具体日期的组合"""

    def test_from_yesterday_to_concrete_date(self, journal):
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        journal.new_entry("y", date=datetime.datetime.combine(yesterday, datetime.time(12, 0)))
        journal.new_entry("t", date=datetime.datetime.combine(datetime.date.today(), datetime.time(12, 0)))

        journal.filter(start_date="yesterday", end_date="2099-12-31")
        assert len(journal.entries) == 2

    def test_from_concrete_date_to_today(self, journal):
        journal.new_entry("old", date=datetime.datetime(2020, 1, 1, 12, 0))
        journal.new_entry("now", date=datetime.datetime.combine(datetime.date.today(), datetime.time(12, 0)))

        journal.filter(start_date="2020-01-01", end_date="today")
        assert len(journal.entries) == 2


class TestQueryFilterViaController:
    """通过 controller._filter_journal_entries 验证完整查询路径"""

    def test_on_date_sets_start_and_end(self, journal):
        _make_entries(journal, "2023-12-30 10:00", "2023-12-31 10:00", "2024-01-01 10:00")

        from argparse import Namespace
        args = Namespace(
            on_date="2023-12-31",
            start_date=None,
            end_date=None,
            text=[],
            today_in_history=False,
            month=None,
            day=None,
            year=None,
            strict=False,
            starred=False,
            tagged=False,
            excluded=[],
            exclude_starred=False,
            exclude_tagged=False,
            contains=[],
            limit=None,
        )
        _filter_journal_entries(args, journal)
        assert len(journal.entries) == 1
        assert journal.entries[0].date.day == 31

    def test_from_to_date_range_via_controller(self, journal):
        _make_entries(journal, "2023-12-31 23:59", "2024-01-01 00:00", "2024-01-02 10:00")

        from argparse import Namespace
        args = Namespace(
            on_date=None,
            start_date="2023-12-31",
            end_date="2024-01-01",
            text=[],
            today_in_history=False,
            month=None,
            day=None,
            year=None,
            strict=False,
            starred=False,
            tagged=False,
            excluded=[],
            exclude_starred=False,
            exclude_tagged=False,
            contains=[],
            limit=None,
        )
        _filter_journal_entries(args, journal)
        assert len(journal.entries) == 2


class TestWriteYearBoundary:
    """录入入口：日期关键字前缀跨年录入"""

    def test_new_entry_dec31_has_correct_date(self, journal):
        entry = journal.new_entry("2023-12-31: New Year Eve entry")
        assert entry.date.year == 2023
        assert entry.date.month == 12
        assert entry.date.day == 31
        assert entry.date.hour == 9
        assert entry.date.minute == 0

    def test_new_entry_jan1_has_correct_date(self, journal):
        entry = journal.new_entry("2024-01-01: Happy New Year entry")
        assert entry.date.year == 2024
        assert entry.date.month == 1
        assert entry.date.day == 1
        assert entry.date.hour == 9

    def test_new_entry_with_time_on_year_boundary(self, journal):
        entry = journal.new_entry("2023-12-31 23:59: Last minute entry")
        assert entry.date.year == 2023
        assert entry.date.month == 12
        assert entry.date.day == 31
        assert entry.date.hour == 23
        assert entry.date.minute == 59

    def test_new_year_midnight_entry_via_date_param(self, journal):
        entry = journal.new_entry("Midnight entry", date=datetime.datetime(2024, 1, 1, 0, 0))
        assert entry.date.year == 2024
        assert entry.date.hour == 0

    def test_new_year_midnight_text_prefix_uses_default_hour(self, journal):
        entry = journal.new_entry("2024-01-01 00:00: Midnight entry")
        assert entry.date.year == 2024
        assert entry.date.hour == 9

    def test_consecutive_entries_across_year_sorted(self, journal):
        journal.new_entry("2024-01-01: First of the year")
        journal.new_entry("2023-12-31: Last of the old year")
        dates = _entry_dates(journal)
        assert dates[0].year == 2023
        assert dates[1].year == 2024
        assert dates[0] < dates[1]


class TestWriteMonthBoundary:
    """录入入口：跨月录入"""

    def test_last_day_of_month_entry(self, journal):
        entry = journal.new_entry("2023-01-31: End of January")
        assert entry.date.month == 1
        assert entry.date.day == 31

    def test_first_day_of_month_entry(self, journal):
        entry = journal.new_entry("2023-02-01: Start of February")
        assert entry.date.month == 2
        assert entry.date.day == 1

    def test_leap_year_feb29_entry(self, journal):
        entry = journal.new_entry("2024-02-29: Leap day entry")
        assert entry.date.month == 2
        assert entry.date.day == 29

    @pytest.mark.parametrize(
        "date_str,expected_month,expected_day",
        [
            ("2023-01-31", 1, 31),
            ("2023-04-30", 4, 30),
            ("2023-06-30", 6, 30),
            ("2023-09-30", 9, 30),
            ("2023-11-30", 11, 30),
        ],
    )
    def test_various_month_end_entries(self, journal, date_str, expected_month, expected_day):
        entry = journal.new_entry(f"{date_str}: Month end entry")
        assert entry.date.month == expected_month
        assert entry.date.day == expected_day

    def test_entries_across_month_boundary_sorted(self, journal):
        journal.new_entry("2023-03-01: March entry")
        journal.new_entry("2023-02-28: February entry")
        dates = _entry_dates(journal)
        assert dates[0].month == 2
        assert dates[1].month == 3
        assert dates[0] < dates[1]


class TestWriteDayBoundary:
    """录入入口：跨日录入（午夜边界）"""

    def test_late_night_entry_uses_specified_date(self, journal):
        entry = journal.new_entry("2023-06-15 23:59: Late night thought")
        assert entry.date.day == 15
        assert entry.date.hour == 23

    def test_early_morning_entry_uses_specified_date(self, journal):
        entry = journal.new_entry("Early morning thought", date=datetime.datetime(2023, 6, 16, 0, 0))
        assert entry.date.day == 16
        assert entry.date.hour == 0

    def test_early_morning_text_prefix_uses_default_hour(self, journal):
        entry = journal.new_entry("2023-06-16 00:00: Early morning thought")
        assert entry.date.day == 16
        assert entry.date.hour == 9

    def test_entries_across_midnight_sorted_correctly(self, journal):
        journal.new_entry("2023-06-16 00:00: Early morning")
        journal.new_entry("2023-06-15 23:59: Late night")
        dates = _entry_dates(journal)
        assert dates[0].day == 15
        assert dates[1].day == 16
        assert dates[0] < dates[1]

    def test_default_hour_on_date_only_prefix(self, journal):
        entry = journal.new_entry("2023-06-15: Afternoon work")
        assert entry.date.hour == 9
        assert entry.date.minute == 0

    def test_explicit_time_overrides_default_hour(self, journal):
        entry = journal.new_entry("2023-06-15 22:30: Late work session")
        assert entry.date.hour == 22
        assert entry.date.minute == 30


class TestWriteKeywordDatePrefix:
    """录入入口：日期关键字前缀（yesterday:/today:/tomorrow:）"""

    def test_yesterday_prefix_date_is_yesterday(self, journal):
        entry = journal.new_entry("yesterday: I did something")
        expected_date = datetime.date.today() - datetime.timedelta(days=1)
        assert entry.date.date() == expected_date
        assert entry.date.hour == 9

    def test_today_prefix_date_is_today(self, journal):
        entry = journal.new_entry("today: Current events")
        assert entry.date.date() == datetime.date.today()
        assert entry.date.hour == 9

    def test_tomorrow_prefix_date_is_tomorrow(self, journal):
        entry = journal.new_entry("tomorrow: Future plans")
        expected_date = datetime.date.today() + datetime.timedelta(days=1)
        assert entry.date.date() == expected_date
        assert entry.date.hour == 9

    def test_yesterday_entry_not_filtered_by_today_on(self, journal):
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        journal.new_entry("yesterday: Past event")
        journal.filter(start_date="today", end_date="today")
        assert len(journal.entries) == 0

    def test_today_entry_found_by_today_filter(self, journal):
        journal.new_entry("today: Current event")
        journal.filter(start_date="today", end_date="today")
        assert len(journal.entries) == 1

    def test_yesterday_entry_found_by_yesterday_filter(self, journal):
        journal.new_entry("yesterday: Past event")
        journal.filter(start_date="yesterday", end_date="yesterday")
        assert len(journal.entries) == 1

    def test_write_then_query_across_day_boundary(self, journal):
        journal.new_entry("yesterday: Late night reflection")
        journal.new_entry("today: Morning thoughts")

        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        all_entries = list(journal.entries)
        assert len(all_entries) == 2
        assert all_entries[0].date.date() == yesterday
        assert all_entries[1].date.date() == datetime.date.today()


class TestWriteThenQueryIntegration:
    """录入后查询的完整链路集成测试（数据漂移回归）"""

    def test_cross_year_write_then_query(self, journal):
        journal.new_entry("2023-12-31: End of year reflection")
        journal.new_entry("2024-01-01: New year resolution")

        journal.filter(start_date="2024-01-01", end_date="2024-12-31")
        assert len(journal.entries) == 1
        assert journal.entries[0].date.year == 2024

    def test_cross_month_write_then_query(self, journal):
        journal.new_entry("2024-02-29: Leap day entry")
        journal.new_entry("2024-03-01: March entry")

        journal.filter(start_date="2024-02-29", end_date="2024-02-29")
        assert len(journal.entries) == 1
        assert journal.entries[0].date.day == 29

    def test_cross_day_write_then_query(self, journal):
        journal.new_entry("2023-06-15 23:59: Late night")
        journal.new_entry("2023-06-16 00:00: Early morning")

        journal.filter(start_date="2023-06-16", end_date="2023-06-16")
        assert len(journal.entries) == 1
        assert journal.entries[0].date.day == 16

    def test_no_data_drift_for_late_entries_on_year_boundary(self, journal):
        journal.new_entry("2023-12-31 23:59: Last moment of the year")

        journal.filter(end_date="2023-12-31")
        assert len(journal.entries) == 1
        assert journal.entries[0].date.year == 2023

        j2 = Journal(name="test2", default_hour=9, default_minute=0, timeformat="%Y-%m-%d %H:%M")
        j2.new_entry("2023-12-31 23:59: Last moment of the year")
        j2.filter(start_date="2024-01-01")
        assert len(j2.entries) == 0

    def test_no_data_drift_for_early_entries_on_year_boundary(self, journal):
        journal.new_entry("2024-01-01 00:00: First moment of the year")

        journal.filter(start_date="2024-01-01")
        assert len(journal.entries) == 1
        assert journal.entries[0].date.year == 2024

        j2 = Journal(name="test2", default_hour=9, default_minute=0, timeformat="%Y-%m-%d %H:%M")
        j2.new_entry("2024-01-01 00:00: First moment of the year")
        j2.filter(end_date="2023-12-31")
        assert len(j2.entries) == 0

    def test_no_data_drift_across_month_boundary(self, journal):
        journal.new_entry("2023-02-28 23:59: End of Feb")
        journal.new_entry("2023-03-01 00:00: Start of Mar")

        journal.filter(end_date="2023-02-28")
        assert len(journal.entries) == 1
        assert journal.entries[0].date.month == 2

        j2 = Journal(name="test2", default_hour=9, default_minute=0, timeformat="%Y-%m-%d %H:%M")
        j2.new_entry("2023-02-28 23:59: End of Feb")
        j2.new_entry("2023-03-01 00:00: Start of Mar")
        j2.filter(start_date="2023-03-01")
        assert len(j2.entries) == 1
        assert j2.entries[0].date.month == 3

    def test_no_data_drift_across_day_boundary(self, journal):
        journal.new_entry("2023-06-15 23:59: Late")
        journal.new_entry("2023-06-16 00:00: Early")

        journal.filter(start_date="2023-06-15", end_date="2023-06-15")
        assert len(journal.entries) == 1
        assert journal.entries[0].date.day == 15

        j2 = Journal(name="test2", default_hour=9, default_minute=0, timeformat="%Y-%m-%d %H:%M")
        j2.new_entry("2023-06-15 23:59: Late")
        j2.new_entry("2023-06-16 00:00: Early")
        j2.filter(start_date="2023-06-16", end_date="2023-06-16")
        assert len(j2.entries) == 1
        assert j2.entries[0].date.day == 16

    def test_leap_year_write_then_query_no_drift(self, journal):
        journal.new_entry("2024-02-29 09:00: Leap day entry")
        journal.new_entry("2024-03-01 09:00: March entry")

        journal.filter(end_date="2024-02-29")
        assert len(journal.entries) == 1
        assert journal.entries[0].date.month == 2
        assert journal.entries[0].date.day == 29

        j2 = Journal(name="test2", default_hour=9, default_minute=0, timeformat="%Y-%m-%d %H:%M")
        j2.new_entry("2024-02-29 09:00: Leap day entry")
        j2.new_entry("2024-03-01 09:00: March entry")
        j2.filter(start_date="2024-03-01")
        assert len(j2.entries) == 1
        assert j2.entries[0].date.month == 3

    def test_year_end_full_day_coverage(self, journal):
        journal.new_entry("2023-12-31 00:00: Start of last day")
        journal.new_entry("2023-12-31 12:00: Midday")
        journal.new_entry("2023-12-31 23:59: End of last day")

        journal.filter(start_date="2023-12-31", end_date="2023-12-31")
        assert len(journal.entries) == 3
        for e in journal.entries:
            assert e.date.year == 2023
            assert e.date.month == 12
            assert e.date.day == 31


# ============================================================
# 闰秒边界 - 查询与录入路径测试
# ============================================================


class TestLeapSecondBoundaryQuery:
    """查询路径：闰秒附近条目过滤"""

    def test_leap_second_entries_filter_correctly_june(self, journal):
        journal.new_entry("2023-06-30 23:59:59", date=datetime.datetime(2023, 6, 30, 23, 59, 59))
        journal.new_entry("2023-07-01 00:00:01", date=datetime.datetime(2023, 7, 1, 0, 0, 1))
        journal.new_entry("2023-07-01 00:01:00", date=datetime.datetime(2023, 7, 1, 0, 1, 0))

        journal.filter(start_date="2023-07-01")
        assert len(journal.entries) == 2
        for e in journal.entries:
            assert e.date.month == 7

        j2 = Journal(name="test2", default_hour=9, default_minute=0, timeformat="%Y-%m-%d %H:%M")
        j2.new_entry("2023-06-30 23:59:59", date=datetime.datetime(2023, 6, 30, 23, 59, 59))
        j2.new_entry("2023-07-01 00:00:01", date=datetime.datetime(2023, 7, 1, 0, 0, 1))
        j2.new_entry("2023-07-01 00:01:00", date=datetime.datetime(2023, 7, 1, 0, 1, 0))
        j2.filter(end_date="2023-06-30")
        assert len(j2.entries) == 1
        assert j2.entries[0].date.month == 6

    def test_leap_second_entries_filter_correctly_december(self, journal):
        journal.new_entry("2023-12-31 23:59:59", date=datetime.datetime(2023, 12, 31, 23, 59, 59))
        journal.new_entry("2024-01-01 00:00:01", date=datetime.datetime(2024, 1, 1, 0, 0, 1))
        journal.new_entry("2024-01-01 00:01:00", date=datetime.datetime(2024, 1, 1, 0, 1, 0))

        journal.filter(start_date="2024-01-01")
        assert len(journal.entries) == 2
        for e in journal.entries:
            assert e.date.year == 2024

        j2 = Journal(name="test2", default_hour=9, default_minute=0, timeformat="%Y-%m-%d %H:%M")
        j2.new_entry("2023-12-31 23:59:59", date=datetime.datetime(2023, 12, 31, 23, 59, 59))
        j2.new_entry("2024-01-01 00:00:01", date=datetime.datetime(2024, 1, 1, 0, 0, 1))
        j2.new_entry("2024-01-01 00:01:00", date=datetime.datetime(2024, 1, 1, 0, 1, 0))
        j2.filter(end_date="2023-12-31")
        assert len(j2.entries) == 1
        assert j2.entries[0].date.year == 2023

    def test_leap_second_string_used_as_filter(self, journal):
        """23:59:60 被解析为当天 00:00（parsedatetime fallback），start_date 会包含当天条目"""
        _make_entries(journal, "2023-06-30 09:00", "2023-07-01 09:00")

        journal.filter(start_date="2023-06-30 23:59:60")
        assert len(journal.entries) == 2
        assert journal.entries[0].date.month == 6
        assert journal.entries[1].date.month == 7

    def test_leap_second_on_date_returns_same_day(self, journal):
        """23:59:60 解析为当天 00:00，start=end 范围包含当天条目"""
        _make_entries(journal, "2023-12-31 09:00", "2024-01-01 09:00")

        journal.filter(start_date="2023-12-31 23:59:60", end_date="2023-12-31 23:59:60")
        assert len(journal.entries) == 1
        assert journal.entries[0].date.month == 12 and journal.entries[0].date.day == 31


class TestLeapSecondBoundaryWrite:
    """录入路径：闰秒附近条目创建"""

    def test_write_235959_then_000000_correct_order(self, journal):
        """使用 date= 参数精确控制时间，验证 23:59:59 < 00:00:01 的顺序"""
        journal.new_entry(
            "2023-06-30 23:59:59: Before leap second",
            date=datetime.datetime(2023, 6, 30, 23, 59, 59),
        )
        journal.new_entry(
            "2023-07-01 00:00:01: After leap second",
            date=datetime.datetime(2023, 7, 1, 0, 0, 1),
        )

        assert len(journal.entries) == 2
        assert journal.entries[0].date == datetime.datetime(2023, 6, 30, 23, 59, 59)
        assert journal.entries[1].date == datetime.datetime(2023, 7, 1, 0, 0, 1)

    def test_write_near_december_leap_second(self, journal):
        journal.new_entry("2023-12-31 23:59:59: Year end last moment")
        journal.new_entry("2024-01-01 00:00:00: New year first moment")

        assert len(journal.entries) == 2
        assert journal.entries[0].date.year == 2023
        assert journal.entries[1].date.year == 2024

    def test_leap_second_prefix_date_fallback(self, journal):
        entry = journal.new_entry("2023-06-30 23:59:60: Leap second entry")
        assert entry.date.date() == datetime.date(2023, 6, 30)
        assert entry.date.hour == 9

    def test_leap_second_december_prefix_date_fallback(self, journal):
        entry = journal.new_entry("2023-12-31 23:59:60: Year end leap second")
        assert entry.date.date() == datetime.date(2023, 12, 31)
        assert entry.date.hour == 9


class TestLeapSecondWriteThenQuery:
    """录入后查询：闰秒附近数据无漂移"""

    def test_write_then_query_near_leap_second_no_drift(self, journal):
        journal.new_entry("2023-06-30 23:59:59: Before leap")
        journal.new_entry("2023-07-01 00:00:00: After leap")

        journal.filter(end_date="2023-06-30")
        assert len(journal.entries) == 1
        assert journal.entries[0].date.month == 6

        j2 = Journal(name="test2", default_hour=9, default_minute=0, timeformat="%Y-%m-%d %H:%M")
        j2.new_entry("2023-06-30 23:59:59: Before leap")
        j2.new_entry("2023-07-01 00:00:00: After leap")
        j2.filter(start_date="2023-07-01")
        assert len(j2.entries) == 1
        assert j2.entries[0].date.month == 7

    def test_write_then_query_near_year_end_leap_second_no_drift(self, journal):
        journal.new_entry("2023-12-31 23:59:59: Year end")
        journal.new_entry("2024-01-01 00:00:00: Year start")

        journal.filter(end_date="2023-12-31")
        assert len(journal.entries) == 1
        assert journal.entries[0].date.year == 2023

        j2 = Journal(name="test2", default_hour=9, default_minute=0, timeformat="%Y-%m-%d %H:%M")
        j2.new_entry("2023-12-31 23:59:59: Year end")
        j2.new_entry("2024-01-01 00:00:00: Year start")
        j2.filter(start_date="2024-01-01")
        assert len(j2.entries) == 1
        assert j2.entries[0].date.year == 2024


# ============================================================
# 闰年2月29日 - 查询与录入路径测试
# ============================================================


class TestLeapYearFeb29Query:
    """查询路径：闰年2月29日过滤"""

    def test_leap_day_single_day_filter(self, journal):
        _make_entries(journal, "2024-02-28 09:00", "2024-02-29 09:00", "2024-03-01 09:00")

        journal.filter(start_date="2024-02-29", end_date="2024-02-29")
        assert len(journal.entries) == 1
        assert journal.entries[0].date.month == 2
        assert journal.entries[0].date.day == 29

    def test_leap_day_included_in_feb_range(self, journal):
        _make_entries(journal, "2024-02-01 09:00", "2024-02-29 09:00", "2024-03-01 09:00")

        journal.filter(start_date="2024-02-01", end_date="2024-02-29")
        assert len(journal.entries) == 2
        for e in journal.entries:
            assert e.date.month == 2

    def test_leap_day_excluded_from_march(self, journal):
        _make_entries(journal, "2024-02-29 09:00", "2024-03-01 09:00")

        journal.filter(start_date="2024-03-01")
        assert len(journal.entries) == 1
        assert journal.entries[0].date.month == 3

    def test_multiple_leap_years_filter(self, journal):
        _make_entries(
            journal,
            "2020-02-29 09:00",
            "2024-02-29 09:00",
            "2028-02-29 09:00",
        )

        journal.filter(start_date="2020-02-29", end_date="2024-02-29")
        assert len(journal.entries) == 2
        assert journal.entries[0].date.year == 2020
        assert journal.entries[1].date.year == 2024

    def test_leap_year_full_coverage_24h(self, journal):
        journal.new_entry("2024-02-29 00:00: Early leap day", date=datetime.datetime(2024, 2, 29, 0, 0, 0))
        journal.new_entry("2024-02-29 12:00: Mid leap day", date=datetime.datetime(2024, 2, 29, 12, 0, 0))
        journal.new_entry("2024-02-29 23:59:59: Late leap day", date=datetime.datetime(2024, 2, 29, 23, 59, 59))
        journal.new_entry("2024-03-01 00:00:00: March start", date=datetime.datetime(2024, 3, 1, 0, 0, 0))

        journal.filter(start_date="2024-02-29", end_date="2024-02-29")
        assert len(journal.entries) == 3
        for e in journal.entries:
            assert e.date.month == 2 and e.date.day == 29

    def test_non_leap_year_feb_29_filter_ignored(self, journal):
        _make_entries(journal, "2023-02-28 09:00", "2023-03-01 09:00")

        journal.filter(start_date="2023-02-29", end_date="2023-02-29")
        assert len(journal.entries) == 2

    def test_century_leap_year_2000(self, journal):
        _make_entries(journal, "2000-02-28 09:00", "2000-02-29 09:00", "2000-03-01 09:00")

        journal.filter(start_date="2000-02-29", end_date="2000-02-29")
        assert len(journal.entries) == 1
        assert journal.entries[0].date.year == 2000

    def test_century_non_leap_year_2100(self, journal):
        _make_entries(journal, "2100-02-28 09:00", "2100-03-01 09:00")

        journal.filter(start_date="2100-02-29", end_date="2100-02-29")
        assert len(journal.entries) == 2


class TestLeapYearFeb29Write:
    """录入路径：闰年2月29日条目创建"""

    def test_leap_day_entry_via_date_prefix(self, journal):
        entry = journal.new_entry("2024-02-29: Leap day entry")
        assert entry.date.year == 2024
        assert entry.date.month == 2
        assert entry.date.day == 29
        assert entry.date.hour == 9

    def test_leap_day_entry_with_time(self, journal):
        entry = journal.new_entry("2024-02-29 14:30: Afternoon leap day")
        assert entry.date == datetime.datetime(2024, 2, 29, 14, 30)

    def test_leap_day_last_moment(self, journal):
        entry = journal.new_entry("2024-02-29 23:59:59: Last leap moment")
        assert entry.date == datetime.datetime(2024, 2, 29, 23, 59, 59)

    def test_century_leap_year_2000_entry(self, journal):
        entry = journal.new_entry("2000-02-29: Century leap day")
        assert entry.date == datetime.datetime(2000, 2, 29, 9, 0)

    def test_non_leap_year_fallback_to_now(self, journal):
        entry = journal.new_entry("2023-02-29: Invalid leap day")
        assert entry.date.date() == datetime.date.today()

    def test_leap_day_entry_sorting(self, journal):
        journal.new_entry("2024-03-01: March 1st")
        journal.new_entry("2024-02-29: Leap day")
        dates = _entry_dates(journal)
        assert dates[0].month == 2 and dates[0].day == 29
        assert dates[1].month == 3 and dates[1].day == 1

    def test_multiple_leap_year_entries_sorting(self, journal):
        journal.new_entry("2024-02-29: 2024 leap")
        journal.new_entry("2020-02-29: 2020 leap")
        journal.new_entry("2000-02-29: 2000 leap")
        dates = _entry_dates(journal)
        assert dates[0].year == 2000
        assert dates[1].year == 2020
        assert dates[2].year == 2024


class TestLeapYearFeb29WriteThenQuery:
    """录入后查询：闰年2月29日数据无漂移"""

    def test_leap_day_write_then_query_no_drift(self, journal):
        journal.new_entry("2024-02-28: Feb 28")
        journal.new_entry("2024-02-29: Feb 29")
        journal.new_entry("2024-03-01: March 1")

        journal.filter(start_date="2024-02-29", end_date="2024-02-29")
        assert len(journal.entries) == 1
        assert journal.entries[0].date.month == 2 and journal.entries[0].date.day == 29

        j2 = Journal(name="test2", default_hour=9, default_minute=0, timeformat="%Y-%m-%d %H:%M")
        j2.new_entry("2024-02-28: Feb 28")
        j2.new_entry("2024-02-29: Feb 29")
        j2.new_entry("2024-03-01: March 1")
        j2.filter(end_date="2024-02-28")
        assert len(j2.entries) == 1
        assert j2.entries[0].date.day == 28

    def test_leap_year_range_query_no_drift(self, journal):
        journal.new_entry("2024-02-28 23:59:59: End of Feb 28")
        journal.new_entry("2024-02-29 00:00:00: Start of Feb 29")
        journal.new_entry("2024-02-29 23:59:59: End of Feb 29")
        journal.new_entry("2024-03-01 00:00:00: Start of March")

        journal.filter(start_date="2024-02-29", end_date="2024-02-29")
        assert len(journal.entries) == 2
        for e in journal.entries:
            assert e.date.month == 2 and e.date.day == 29

        j2 = Journal(name="test2", default_hour=9, default_minute=0, timeformat="%Y-%m-%d %H:%M")
        j2.new_entry("2024-02-28 23:59:59: End of Feb 28")
        j2.new_entry("2024-02-29 00:00:00: Start of Feb 29")
        j2.new_entry("2024-02-29 23:59:59: End of Feb 29")
        j2.new_entry("2024-03-01 00:00:00: Start of March")
        j2.filter(start_date="2024-03-01")
        assert len(j2.entries) == 1
        assert j2.entries[0].date.month == 3

    def test_non_leap_year_write_then_query(self, journal):
        journal.new_entry("2023-02-28 23:59:59: End of Feb 2023")
        journal.new_entry("2023-03-01 00:00:00: Start of March 2023")

        journal.filter(end_date="2023-02-28")
        assert len(journal.entries) == 1
        assert journal.entries[0].date.month == 2

        j2 = Journal(name="test2", default_hour=9, default_minute=0, timeformat="%Y-%m-%d %H:%M")
        j2.new_entry("2023-02-28 23:59:59: End of Feb 2023")
        j2.new_entry("2023-03-01 00:00:00: Start of March 2023")
        j2.filter(start_date="2023-03-01")
        assert len(j2.entries) == 1
        assert j2.entries[0].date.month == 3


# ============================================================
# 年末跨日精细边界 - 查询与录入路径测试
# ============================================================


class TestYearEndGranularBoundaryQuery:
    """查询路径：年末跨日精细过滤"""

    def test_year_end_exact_second_boundary(self, journal):
        journal.new_entry("2023-12-31 23:59:59: Year end last", date=datetime.datetime(2023, 12, 31, 23, 59, 59))
        journal.new_entry("2024-01-01 00:00:00: New year first", date=datetime.datetime(2024, 1, 1, 0, 0, 0))

        journal.filter(end_date="2023-12-31")
        assert len(journal.entries) == 1
        assert journal.entries[0].date.year == 2023

        j2 = Journal(name="test2", default_hour=9, default_minute=0, timeformat="%Y-%m-%d %H:%M")
        j2.new_entry("2023-12-31 23:59:59: Year end last", date=datetime.datetime(2023, 12, 31, 23, 59, 59))
        j2.new_entry("2024-01-01 00:00:00: New year first", date=datetime.datetime(2024, 1, 1, 0, 0, 0))
        j2.filter(start_date="2024-01-01")
        assert len(j2.entries) == 1
        assert j2.entries[0].date.year == 2024

    def test_year_end_full_day_includes_all_moments(self, journal):
        journal.new_entry("midnight", date=datetime.datetime(2023, 12, 31, 0, 0, 0))
        journal.new_entry("noon", date=datetime.datetime(2023, 12, 31, 12, 0, 0))
        journal.new_entry("last sec", date=datetime.datetime(2023, 12, 31, 23, 59, 59))
        journal.new_entry("new year", date=datetime.datetime(2024, 1, 1, 0, 0, 0))

        journal.filter(start_date="2023-12-31", end_date="2023-12-31")
        assert len(journal.entries) == 3
        for e in journal.entries:
            assert e.date.year == 2023 and e.date.month == 12 and e.date.day == 31

    def test_new_year_day_full_coverage(self, journal):
        journal.new_entry("year end", date=datetime.datetime(2023, 12, 31, 23, 59, 59))
        journal.new_entry("midnight", date=datetime.datetime(2024, 1, 1, 0, 0, 0))
        journal.new_entry("noon", date=datetime.datetime(2024, 1, 1, 12, 0, 0))
        journal.new_entry("late night", date=datetime.datetime(2024, 1, 1, 23, 59, 59))

        journal.filter(start_date="2024-01-01", end_date="2024-01-01")
        assert len(journal.entries) == 3
        for e in journal.entries:
            assert e.date.year == 2024 and e.date.month == 1 and e.date.day == 1

    def test_cross_year_range(self, journal):
        _make_entries(
            journal,
            "2023-12-30 09:00",
            "2023-12-31 09:00",
            "2024-01-01 09:00",
            "2024-01-02 09:00",
        )

        journal.filter(start_date="2023-12-31", end_date="2024-01-01")
        assert len(journal.entries) == 2
        assert journal.entries[0].date.year == 2023
        assert journal.entries[1].date.year == 2024

    def test_multiple_year_boundaries(self, journal):
        _make_entries(
            journal,
            "2022-12-31 09:00",
            "2023-01-01 09:00",
            "2023-12-31 09:00",
            "2024-01-01 09:00",
        )

        journal.filter(start_date="2023-01-01", end_date="2023-12-31")
        assert len(journal.entries) == 2
        for e in journal.entries:
            assert e.date.year == 2023


class TestYearEndGranularBoundaryWrite:
    """录入路径：年末跨日条目创建"""

    def test_new_year_midnight_entry_via_date(self, journal):
        entry = journal.new_entry("Midnight entry", date=datetime.datetime(2024, 1, 1, 0, 0, 0))
        assert entry.date == datetime.datetime(2024, 1, 1, 0, 0, 0)

    def test_year_end_last_second_entry(self, journal):
        entry = journal.new_entry("Last second entry", date=datetime.datetime(2023, 12, 31, 23, 59, 59))
        assert entry.date == datetime.datetime(2023, 12, 31, 23, 59, 59)

    def test_year_end_entry_via_prefix(self, journal):
        entry = journal.new_entry("2023-12-31: Year end reflection")
        assert entry.date == datetime.datetime(2023, 12, 31, 9, 0)

    def test_new_year_entry_via_prefix(self, journal):
        entry = journal.new_entry("2024-01-01: New year resolution")
        assert entry.date == datetime.datetime(2024, 1, 1, 9, 0)

    def test_year_end_with_time_prefix(self, journal):
        entry = journal.new_entry("2023-12-31 23:59: Year end toast")
        assert entry.date == datetime.datetime(2023, 12, 31, 23, 59)

    def test_new_year_with_12am_format(self, journal):
        entry = journal.new_entry("2024-01-01 12:00am: Happy new year")
        assert entry.date == datetime.datetime(2024, 1, 1, 9, 0)

    def test_year_end_with_1159pm_format(self, journal):
        entry = journal.new_entry("2023-12-31 11:59pm: Toast")
        assert entry.date == datetime.datetime(2023, 12, 31, 23, 59)

    def test_cross_year_entries_sorted(self, journal):
        journal.new_entry("2024-01-01: New year")
        journal.new_entry("2023-12-31: Year end")
        dates = _entry_dates(journal)
        assert dates[0].year == 2023
        assert dates[1].year == 2024
        assert dates[0] < dates[1]

    def test_multiple_cross_year_entries_sorted(self, journal):
        journal.new_entry("2024-01-01 09:00: Jan 1 morning")
        journal.new_entry("2023-12-31 23:59: Dec 31 late")
        journal.new_entry("2023-12-31 09:00: Dec 31 morning")
        dates = _entry_dates(journal)
        assert dates[0] == datetime.datetime(2023, 12, 31, 9, 0)
        assert dates[1] == datetime.datetime(2023, 12, 31, 23, 59)
        assert dates[2] == datetime.datetime(2024, 1, 1, 9, 0)


class TestYearEndGranularWriteThenQuery:
    """录入后查询：年末跨日数据无漂移"""

    def test_year_end_write_then_query_no_drift(self, journal):
        journal.new_entry("2023-12-31 23:59:59: Year end", date=datetime.datetime(2023, 12, 31, 23, 59, 59))
        journal.new_entry("2024-01-01 00:00:00: New year", date=datetime.datetime(2024, 1, 1, 0, 0, 0))

        journal.filter(end_date="2023-12-31")
        assert len(journal.entries) == 1
        assert journal.entries[0].date.year == 2023

        j2 = Journal(name="test2", default_hour=9, default_minute=0, timeformat="%Y-%m-%d %H:%M")
        j2.new_entry("2023-12-31 23:59:59: Year end", date=datetime.datetime(2023, 12, 31, 23, 59, 59))
        j2.new_entry("2024-01-01 00:00:00: New year", date=datetime.datetime(2024, 1, 1, 0, 0, 0))
        j2.filter(start_date="2024-01-01")
        assert len(j2.entries) == 1
        assert j2.entries[0].date.year == 2024

    def test_year_end_full_day_write_then_query_no_drift(self, journal):
        for h in range(24):
            journal.new_entry(
                f"2023-12-31 {h:02d}:00 entry",
                date=datetime.datetime(2023, 12, 31, h, 0, 0),
            )
        journal.new_entry(
            "2024-01-01 00:00 entry",
            date=datetime.datetime(2024, 1, 1, 0, 0, 0),
        )

        journal.filter(start_date="2023-12-31", end_date="2023-12-31")
        assert len(journal.entries) == 24
        for e in journal.entries:
            assert e.date.month == 12 and e.date.day == 31

    def test_multiple_year_end_no_drift(self, journal):
        journal.new_entry("2022-12-31 23:59:59: 2022 end", date=datetime.datetime(2022, 12, 31, 23, 59, 59))
        journal.new_entry("2023-01-01 00:00:00: 2023 start", date=datetime.datetime(2023, 1, 1, 0, 0, 0))
        journal.new_entry("2023-12-31 23:59:59: 2023 end", date=datetime.datetime(2023, 12, 31, 23, 59, 59))
        journal.new_entry("2024-01-01 00:00:00: 2024 start", date=datetime.datetime(2024, 1, 1, 0, 0, 0))

        journal.filter(start_date="2023-01-01", end_date="2023-12-31")
        assert len(journal.entries) == 2
        for e in journal.entries:
            assert e.date.year == 2023

        j2 = Journal(name="test2", default_hour=9, default_minute=0, timeformat="%Y-%m-%d %H:%M")
        j2.new_entry("2022-12-31 23:59:59: 2022 end", date=datetime.datetime(2022, 12, 31, 23, 59, 59))
        j2.new_entry("2023-01-01 00:00:00: 2023 start", date=datetime.datetime(2023, 1, 1, 0, 0, 0))
        j2.new_entry("2023-12-31 23:59:59: 2023 end", date=datetime.datetime(2023, 12, 31, 23, 59, 59))
        j2.new_entry("2024-01-01 00:00:00: 2024 start", date=datetime.datetime(2024, 1, 1, 0, 0, 0))
        j2.filter(start_date="2024-01-01")
        assert len(j2.entries) == 1
        assert j2.entries[0].date.year == 2024

    def test_year_end_keyword_write_then_query(self, journal):
        journal.new_entry("yesterday: Last day entry")
        journal.new_entry("today: Today entry")

        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        journal.filter(start_date="today", end_date="today")
        assert len(journal.entries) == 1
        assert journal.entries[0].date.date() == datetime.date.today()

        j2 = Journal(name="test2", default_hour=9, default_minute=0, timeformat="%Y-%m-%d %H:%M")
        j2.new_entry("yesterday: Last day entry")
        j2.new_entry("today: Today entry")
        j2.filter(start_date="yesterday", end_date="yesterday")
        assert len(j2.entries) == 1
        assert j2.entries[0].date.date() == yesterday
