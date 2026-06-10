# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import datetime
import os

import pytest

from jrnl import time
from jrnl.journals import Journal
from jrnl.journals.FolderJournal import Folder


class TestFilterAbsoluteDates:
    def test_filter_start_date(self, journal_with_dates):
        journal, base = journal_with_dates
        start = (base - datetime.timedelta(days=3)).strftime("%Y-%m-%d")
        journal.filter(start_date=start)
        assert len(journal) == 5

    def test_filter_end_date(self, journal_with_dates):
        journal, base = journal_with_dates
        end = (base + datetime.timedelta(days=3)).strftime("%Y-%m-%d")
        journal.filter(end_date=end)
        assert len(journal) == 5

    def test_filter_date_range(self, journal_with_dates):
        journal, base = journal_with_dates
        start = (base - datetime.timedelta(days=2)).strftime("%Y-%m-%d")
        end = (base + datetime.timedelta(days=2)).strftime("%Y-%m-%d")
        journal.filter(start_date=start, end_date=end)
        assert len(journal) == 3

    def test_filter_specific_month(self, journal_with_dates):
        journal, _ = journal_with_dates
        journal.filter(month="6")
        for entry in journal.entries:
            assert entry.date.month == 6

    def test_filter_specific_year(self, journal_with_dates):
        journal, _ = journal_with_dates
        journal.filter(year="2023")
        assert len(journal) == 7
        for entry in journal.entries:
            assert entry.date.year == 2023

    def test_filter_specific_day(self, journal_with_dates):
        journal, base = journal_with_dates
        journal.filter(day="15")
        for entry in journal.entries:
            assert entry.date.day == 15

    def test_filter_on_date(self, journal_with_dates):
        journal, base = journal_with_dates
        on_date = base.strftime("%Y-%m-%d")
        journal.filter(start_date=on_date, end_date=on_date)
        assert len(journal) == 1
        assert journal.entries[0].date.date() == base.date()


class TestFilterRelativeDates:
    def test_filter_yesterday(self):
        now = datetime.datetime.now()
        yesterday = now - datetime.timedelta(days=1)
        two_days_ago = now - datetime.timedelta(days=2)

        journal = Journal()
        journal.new_entry("Today entry", date=now)
        journal.new_entry("Yesterday entry", date=yesterday)
        journal.new_entry("Two days ago entry", date=two_days_ago)
        journal.sort()

        yesterday_str = yesterday.strftime("%Y-%m-%d")
        journal.filter(
            start_date=yesterday_str,
            end_date=yesterday_str,
        )
        assert len(journal) == 1
        assert journal.entries[0].date.date() == yesterday.date()

    def test_filter_last_week(self):
        now = datetime.datetime.now()
        last_week = now - datetime.timedelta(weeks=1)
        two_weeks_ago = now - datetime.timedelta(weeks=2)

        journal = Journal()
        journal.new_entry("Today entry", date=now)
        journal.new_entry("Last week entry", date=last_week)
        journal.new_entry("Two weeks ago entry", date=two_weeks_ago)
        journal.sort()

        start = (now - datetime.timedelta(weeks=1, days=1)).strftime("%Y-%m-%d")
        end = (now - datetime.timedelta(weeks=1)).strftime("%Y-%m-%d")
        last_week_str = last_week.strftime("%Y-%m-%d")
        journal.filter(start_date=last_week_str, end_date=last_week_str)
        assert len(journal) == 1
        assert journal.entries[0].date.date() == last_week.date()

    def test_filter_last_month(self):
        now = datetime.datetime.now()
        last_month_approx = now - datetime.timedelta(days=30)
        two_months_ago = now - datetime.timedelta(days=60)

        journal = Journal()
        journal.new_entry("Today entry", date=now)
        journal.new_entry("Last month entry", date=last_month_approx)
        journal.new_entry("Two months ago entry", date=two_months_ago)
        journal.sort()

        start = last_month_approx.strftime("%Y-%m-%d")
        end = last_month_approx.strftime("%Y-%m-%d")
        journal.filter(start_date=start, end_date=end)
        assert len(journal) == 1
        assert journal.entries[0].date.date() == last_month_approx.date()

    def test_filter_from_yesterday_to_now(self):
        now = datetime.datetime.now()
        yesterday = now - datetime.timedelta(days=1)
        three_days_ago = now - datetime.timedelta(days=3)

        journal = Journal()
        journal.new_entry("Today entry", date=now)
        journal.new_entry("Yesterday entry", date=yesterday)
        journal.new_entry("Three days ago", date=three_days_ago)
        journal.sort()

        yesterday_str = yesterday.strftime("%Y-%m-%d")
        journal.filter(start_date=yesterday_str)
        assert len(journal) == 2

    def test_filter_up_to_yesterday(self):
        now = datetime.datetime.now()
        yesterday = now - datetime.timedelta(days=1)
        three_days_ago = now - datetime.timedelta(days=3)

        journal = Journal()
        journal.new_entry("Today entry", date=now)
        journal.new_entry("Yesterday entry", date=yesterday)
        journal.new_entry("Three days ago", date=three_days_ago)
        journal.sort()

        yesterday_str = yesterday.strftime("%Y-%m-%d")
        journal.filter(end_date=yesterday_str)
        assert len(journal) == 2

    def test_filter_today_in_history_via_month_and_day(self):
        now = datetime.datetime.now()
        this_year = now.year

        journal = Journal()
        journal.new_entry(
            "This year today",
            date=datetime.datetime(this_year, now.month, now.day, 10, 0),
        )
        journal.new_entry(
            "Last year same day",
            date=datetime.datetime(this_year - 1, now.month, now.day, 10, 0),
        )
        journal.new_entry(
            "Different day",
            date=datetime.datetime(this_year, now.month, max(1, now.day - 5), 10, 0),
        )
        journal.sort()

        journal.filter(month=str(now.month), day=str(now.day))
        assert len(journal) == 2
        for entry in journal.entries:
            assert entry.date.month == now.month
            assert entry.date.day == now.day


class TestFilterRelativeDatesWithParsedTime:
    def test_parse_yesterday(self):
        result = time.parse("yesterday")
        expected = datetime.datetime.now() - datetime.timedelta(days=1)
        assert result.date() == expected.date()

    def test_parse_today(self):
        result = time.parse("today")
        expected = datetime.datetime.now()
        assert result.date() == expected.date()

    def test_filter_using_parsed_yesterday(self):
        now = datetime.datetime.now()
        yesterday = now - datetime.timedelta(days=1)
        two_days_ago = now - datetime.timedelta(days=2)

        journal = Journal()
        journal.new_entry("Today entry", date=now)
        journal.new_entry("Yesterday entry", date=yesterday)
        journal.new_entry("Two days ago entry", date=two_days_ago)
        journal.sort()

        parsed_yesterday = time.parse("yesterday")
        yesterday_str = parsed_yesterday.strftime("%Y-%m-%d")
        journal.filter(start_date=yesterday_str, end_date=yesterday_str)
        assert len(journal) == 1

    def test_filter_using_parsed_last_week(self):
        now = datetime.datetime.now()
        last_week = now - datetime.timedelta(weeks=1)
        two_weeks_ago = now - datetime.timedelta(weeks=2)

        journal = Journal()
        journal.new_entry("Today entry", date=now)
        journal.new_entry("Last week entry", date=last_week)
        journal.new_entry("Two weeks ago", date=two_weeks_ago)
        journal.sort()

        from_date = time.parse("last week")
        if from_date:
            from_str = from_date.strftime("%Y-%m-%d")
            journal.filter(start_date=from_str)
            assert len(journal) >= 2


class TestFilterDatesOnFolderJournal:
    def test_folder_journal_date_range_filter(self, folder_journal_with_entries):
        folder_path = folder_journal_with_entries
        journal = Folder(
            name="notes",
            journal=folder_path,
            tagsymbols="@#",
            timeformat="%Y-%m-%d %H:%M",
            default_hour=9,
            default_minute=0,
            highlight=True,
            linewrap=79,
            indent_character="|",
        )
        journal.open()

        journal.filter(start_date="2023-01-01", end_date="2023-01-31")
        for entry in journal.entries:
            assert entry.date.month == 1
            assert entry.date.year == 2023

    def test_folder_journal_month_filter(self, folder_journal_with_entries):
        folder_path = folder_journal_with_entries
        journal = Folder(
            name="notes",
            journal=folder_path,
            tagsymbols="@#",
            timeformat="%Y-%m-%d %H:%M",
            default_hour=9,
            default_minute=0,
            highlight=True,
            linewrap=79,
            indent_character="|",
        )
        journal.open()

        journal.filter(month="2")
        for entry in journal.entries:
            assert entry.date.month == 2


class TestFilterDatesOnEncryptedJournal:
    def test_encrypted_journal_date_range(self, tmp_path):
        from jrnl.encryption.NoEncryption import NoEncryption

        journal_path = str(tmp_path / "test.journal")
        journal = Journal(
            name="enc_test",
            journal=journal_path,
            tagsymbols="@",
            timeformat="%Y-%m-%d %H:%M",
            default_hour=9,
            default_minute=0,
            highlight=True,
            linewrap=79,
            indent_character="|",
        )
        journal.new_entry(
            "2023-01-15 entry",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        journal.new_entry(
            "2023-02-15 entry",
            date=datetime.datetime(2023, 2, 15, 10, 0),
        )
        journal.new_entry(
            "2023-03-15 entry",
            date=datetime.datetime(2023, 3, 15, 10, 0),
        )

        journal.encryption_method = NoEncryption(journal_path, journal.config)
        journal.write()

        journal2 = Journal(
            name="enc_test",
            journal=journal_path,
            tagsymbols="@",
            timeformat="%Y-%m-%d %H:%M",
            default_hour=9,
            default_minute=0,
            highlight=True,
            linewrap=79,
            indent_character="|",
        )
        journal2.encryption_method = NoEncryption(journal_path, journal2.config)
        journal2.open()

        journal2.filter(start_date="2023-01-01", end_date="2023-01-31")
        assert len(journal2) == 1
        assert journal2.entries[0].date.month == 1

    def test_encrypted_journal_month_filter(self, tmp_path):
        from jrnl.encryption.NoEncryption import NoEncryption

        journal_path = str(tmp_path / "test.journal")
        journal = Journal(
            name="enc_test",
            journal=journal_path,
            tagsymbols="@",
            timeformat="%Y-%m-%d %H:%M",
            default_hour=9,
            default_minute=0,
            highlight=True,
            linewrap=79,
            indent_character="|",
        )
        journal.new_entry(
            "2023-01-15 entry",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        journal.new_entry(
            "2023-02-15 entry",
            date=datetime.datetime(2023, 2, 15, 10, 0),
        )

        journal.encryption_method = NoEncryption(journal_path, journal.config)
        journal.write()

        journal2 = Journal(
            name="enc_test",
            journal=journal_path,
            tagsymbols="@",
            timeformat="%Y-%m-%d %H:%M",
            default_hour=9,
            default_minute=0,
            highlight=True,
            linewrap=79,
            indent_character="|",
        )
        journal2.encryption_method = NoEncryption(journal_path, journal2.config)
        journal2.open()

        journal2.filter(month="2")
        assert len(journal2) == 1
        assert journal2.entries[0].date.month == 2
