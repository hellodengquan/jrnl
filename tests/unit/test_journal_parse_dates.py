# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import datetime
import time as time_module

import pytest

from jrnl.journals import Journal


def _local_offset_hours():
    return -time_module.timezone / 3600


class TestJournalParseDateStrptimeBranch:
    @pytest.fixture
    def journal_with_tz_format(self):
        journal = Journal(
            "test",
            timeformat="%Y-%m-%d %H:%M %z",
        )
        return journal

    def test_strptime_with_utc_offset_converts_to_local(self, journal_with_tz_format):
        journal_txt = "[2024-06-20 14:30 +0000] Test entry\nBody text\n"
        entries = journal_with_tz_format._parse(journal_txt)
        assert len(entries) == 1
        entry = entries[0]
        expected_hour = 14 + _local_offset_hours()
        assert entry.date.hour == int(expected_hour)
        assert entry.date.tzinfo is None

    def test_strptime_with_positive_offset_converts_to_local(self, journal_with_tz_format):
        journal_txt = "[2024-06-20 14:30 +0800] Test entry\nBody\n"
        entries = journal_with_tz_format._parse(journal_txt)
        assert len(entries) == 1
        entry = entries[0]
        local_offset = _local_offset_hours()
        expected_hour = 14 + (local_offset - 8)
        assert entry.date.hour == int(expected_hour)
        assert entry.date.tzinfo is None

    def test_strptime_with_negative_offset_converts_to_local(self, journal_with_tz_format):
        journal_txt = "[2024-06-20 14:30 -0500] Test entry\nBody\n"
        entries = journal_with_tz_format._parse(journal_txt)
        assert len(entries) == 1
        entry = entries[0]
        local_offset = _local_offset_hours()
        expected_dt = datetime.datetime(2024, 6, 20, 14, 30) + datetime.timedelta(
            hours=local_offset + 5
        )
        assert entry.date.year == expected_dt.year
        assert entry.date.month == expected_dt.month
        assert entry.date.day == expected_dt.day
        assert entry.date.hour == expected_dt.hour
        assert entry.date.minute == expected_dt.minute
        assert entry.date.tzinfo is None

    def test_strptime_naive_timeformat_unchanged(self):
        journal = Journal("test", timeformat="%Y-%m-%d %H:%M")
        journal_txt = "[2024-06-20 14:30] Test entry\nBody text\n"
        entries = journal._parse(journal_txt)
        assert len(entries) == 1
        entry = entries[0]
        assert entry.date.hour == 14
        assert entry.date.minute == 30
        assert entry.date.tzinfo is None


class TestJournalParseTimeParseFallbackBranch:
    @pytest.fixture
    def journal_standard_format(self):
        journal = Journal(
            "test",
            timeformat="%Y-%m-%d %H:%M",
        )
        return journal

    def test_fallback_to_timeparse_with_utc_z(self, journal_standard_format):
        journal_txt = "[2024-06-20T14:30:00Z] Test entry\nBody\n"
        entries = journal_standard_format._parse(journal_txt)
        assert len(entries) == 1
        entry = entries[0]
        expected_hour = 14 + _local_offset_hours()
        assert entry.date.hour == int(expected_hour)
        assert entry.date.tzinfo is None

    def test_fallback_to_timeparse_with_utc_offset(self, journal_standard_format):
        journal_txt = "[2024-06-20T14:30:00+00:00] Test entry\nBody\n"
        entries = journal_standard_format._parse(journal_txt)
        assert len(entries) == 1
        entry = entries[0]
        expected_hour = 14 + _local_offset_hours()
        assert entry.date.hour == int(expected_hour)
        assert entry.date.tzinfo is None

    def test_fallback_to_timeparse_with_utc_string(self, journal_standard_format):
        journal_txt = "[2024-06-20 14:30 UTC] Test entry\nBody\n"
        entries = journal_standard_format._parse(journal_txt)
        assert len(entries) == 1
        entry = entries[0]
        expected_hour = 14 + _local_offset_hours()
        assert entry.date.hour == int(expected_hour)
        assert entry.date.tzinfo is None

    def test_fallback_to_timeparse_with_plus8_offset(self, journal_standard_format):
        journal_txt = "[2024-06-20T14:30:00+08:00] Test entry\nBody\n"
        entries = journal_standard_format._parse(journal_txt)
        assert len(entries) == 1
        entry = entries[0]
        local_offset = _local_offset_hours()
        expected_hour = 14 + (local_offset - 8)
        assert entry.date.hour == int(expected_hour)
        assert entry.date.tzinfo is None

    def test_fallback_to_timeparse_naive_string_unchanged(self, journal_standard_format):
        journal_txt = "[Jun 20, 2024 2:30 PM] Test entry\nBody\n"
        entries = journal_standard_format._parse(journal_txt)
        assert len(entries) == 1
        entry = entries[0]
        assert entry.date.hour == 14
        assert entry.date.minute == 30
        assert entry.date.tzinfo is None

    def test_multiple_entries_with_mixed_formats(self, journal_standard_format):
        journal_txt = (
            "[2024-06-20T10:00:00Z] First entry\nBody 1\n\n"
            "[2024-06-20T15:00:00+00:00] Second entry\nBody 2\n\n"
            "[2024-06-20 22:00] Third entry\nBody 3\n"
        )
        entries = journal_standard_format._parse(journal_txt)
        assert len(entries) == 3

        local_offset = _local_offset_hours()
        assert entries[0].date.hour == int(10 + local_offset)
        assert entries[1].date.hour == int(15 + local_offset)
        assert entries[2].date.hour == 22

        for entry in entries:
            assert entry.date.tzinfo is None


class TestConvertAwareToLocalNaive:
    def test_naive_datetime_unchanged(self):
        from jrnl import time as jrnl_time

        naive_dt = datetime.datetime(2024, 6, 20, 14, 30)
        result = jrnl_time.convert_aware_to_local_naive(naive_dt)
        assert result == naive_dt
        assert result.tzinfo is None

    def test_utc_aware_converts_to_local(self):
        from jrnl import time as jrnl_time

        utc_dt = datetime.datetime(2024, 6, 20, 14, 30, tzinfo=datetime.timezone.utc)
        result = jrnl_time.convert_aware_to_local_naive(utc_dt)
        expected_hour = 14 + _local_offset_hours()
        assert result.hour == int(expected_hour)
        assert result.tzinfo is None

    def test_plus8_aware_converts_to_local(self):
        from jrnl import time as jrnl_time

        plus8_tz = datetime.timezone(datetime.timedelta(hours=8))
        plus8_dt = datetime.datetime(2024, 6, 20, 14, 30, tzinfo=plus8_tz)
        result = jrnl_time.convert_aware_to_local_naive(plus8_dt)
        local_offset = _local_offset_hours()
        expected_hour = 14 + (local_offset - 8)
        assert result.hour == int(expected_hour)
        assert result.tzinfo is None
