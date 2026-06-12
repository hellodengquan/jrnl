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
