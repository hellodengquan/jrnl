# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import datetime
import time as time_module
from unittest import mock

import pytest

from jrnl import time as jrnl_time
from jrnl.journals import Entry
from jrnl.journals import Journal


class TestHelperDstCorrectness:
    def test_convert_aware_no_now_dependency(self):
        """Verify that convert_aware_to_local_naive produces the correct result
        regardless of the *current* moment (i.e., it doesn't pick a DST offset
        based on "now", but based on the dt being converted). We verify this by
        checking that the output of convert_aware_to_local_naive is exactly
        equal to dt.astimezone().replace(tzinfo=None) for a variety of dates
        spanning both sides of DST transitions.
        """
        test_dts = [
            # Standard time (winter)
            datetime.datetime(2024, 1, 15, 14, 30, tzinfo=datetime.timezone.utc),
            datetime.datetime(2024, 2, 29, 23, 59, tzinfo=datetime.timezone.utc),
            # Daylight time (summer)
            datetime.datetime(2024, 6, 15, 14, 30, tzinfo=datetime.timezone.utc),
            datetime.datetime(2024, 8, 1, 0, 0, tzinfo=datetime.timezone.utc),
            # Spring forward day
            datetime.datetime(2024, 3, 10, 6, 59, tzinfo=datetime.timezone.utc),
            datetime.datetime(2024, 3, 10, 7, 0, tzinfo=datetime.timezone.utc),
            # Fall back day
            datetime.datetime(2024, 11, 3, 5, 59, tzinfo=datetime.timezone.utc),
            datetime.datetime(2024, 11, 3, 6, 0, tzinfo=datetime.timezone.utc),
        ]
        for aware_dt in test_dts:
            expected = aware_dt.astimezone().replace(tzinfo=None)
            result = jrnl_time.convert_aware_to_local_naive(aware_dt)
            assert result == expected, f"Failed for {aware_dt}: got {result}, expected {expected}"
            assert result.tzinfo is None

    def test_convert_aware_standard_time_conversion(self):
        """During standard (winter) time, a UTC+0 datetime shifts by standard offset.

        We verify this by comparing:
        - utc_dt.astimezone().replace(tzinfo=None)  (correct, per dt's moment)
        - convert_aware_to_local_naive(utc_dt)     (what our helper produces)
        They MUST be equal.
        """
        utc_dt = datetime.datetime(
            2024, 1, 15, 14, 30, tzinfo=datetime.timezone.utc
        )
        expected = utc_dt.astimezone().replace(tzinfo=None)
        result = jrnl_time.convert_aware_to_local_naive(utc_dt)
        assert result == expected
        assert result.tzinfo is None

    def test_convert_aware_daylight_time_conversion(self):
        """Same test for daylight (summer) time."""
        utc_dt = datetime.datetime(
            2024, 6, 15, 14, 30, tzinfo=datetime.timezone.utc
        )
        expected = utc_dt.astimezone().replace(tzinfo=None)
        result = jrnl_time.convert_aware_to_local_naive(utc_dt)
        assert result == expected
        assert result.tzinfo is None

    def test_convert_aware_spring_forward_hour_after(self):
        """Right after spring-forward (clocks moved ahead 1h)."""
        # A known post-spring-forward instant in UTC - pick one after
        # March 10 2024 (the US 2024 spring-forward date) in UTC.
        utc_dt = datetime.datetime(
            2024, 3, 10, 12, 0, tzinfo=datetime.timezone.utc
        )
        expected = utc_dt.astimezone().replace(tzinfo=None)
        result = jrnl_time.convert_aware_to_local_naive(utc_dt)
        assert result == expected
        assert result.tzinfo is None

    def test_convert_aware_fall_back_hour_before(self):
        """Right before fall-back (clocks move back 1h - the ambiguous local hour)."""
        utc_dt = datetime.datetime(
            2024, 11, 3, 5, 0, tzinfo=datetime.timezone.utc
        )
        expected = utc_dt.astimezone().replace(tzinfo=None)
        result = jrnl_time.convert_aware_to_local_naive(utc_dt)
        assert result == expected
        assert result.tzinfo is None

    def test_convert_aware_plus8_offset(self):
        plus8 = datetime.timezone(datetime.timedelta(hours=8))
        dt = datetime.datetime(2024, 6, 15, 14, 30, tzinfo=plus8)
        expected = dt.astimezone().replace(tzinfo=None)
        result = jrnl_time.convert_aware_to_local_naive(dt)
        assert result == expected
        assert result.tzinfo is None

    def test_convert_aware_negative_offset(self):
        minus5 = datetime.timezone(datetime.timedelta(hours=-5))
        dt = datetime.datetime(2024, 6, 15, 14, 30, tzinfo=minus5)
        expected = dt.astimezone().replace(tzinfo=None)
        result = jrnl_time.convert_aware_to_local_naive(dt)
        assert result == expected
        assert result.tzinfo is None

    def test_naive_datetime_passthrough(self):
        naive_dt = datetime.datetime(2024, 6, 15, 14, 30)
        result = jrnl_time.convert_aware_to_local_naive(naive_dt)
        assert result == naive_dt
        assert result.tzinfo is None


class TestEntryDstConsistency:
    @pytest.fixture
    def journal(self):
        j = Journal("test", timeformat="%Y-%m-%d %H:%M")
        j.config["colors"] = {"body": "none", "date": "none", "tags": "none", "title": "none"}
        j.config["linewrap"] = False
        j.config["indent_character"] = ""
        j.config["highlight"] = True
        j.config["tag_symbols"] = ["@"]
        return j

    def test_entry_init_normalizes_aware_date(self, journal):
        """Entry constructor must normalize aware datetime to local naive."""
        utc_dt = datetime.datetime(
            2024, 6, 15, 14, 30, tzinfo=datetime.timezone.utc
        )
        entry = Entry(journal, date=utc_dt, text="Test entry")
        expected = utc_dt.astimezone().replace(tzinfo=None)
        assert entry.date == expected
        assert entry.date.tzinfo is None

    def test_entry_str_normalizes_aware_date(self, journal):
        """Entry.__str__ must normalize even if .date was externally set to aware."""
        entry = Entry(
            journal,
            date=datetime.datetime(2024, 6, 15, 10, 0),
            text="Original entry",
        )
        # Directly mutate .date to an aware datetime (simulating buggy external code)
        utc_dt = datetime.datetime(
            2024, 6, 15, 14, 30, tzinfo=datetime.timezone.utc
        )
        entry.date = utc_dt

        expected = utc_dt.astimezone().replace(tzinfo=None)
        serialized = str(entry)
        expected_str = expected.strftime(journal.config["timeformat"])
        assert expected_str in serialized

    def test_entry_pprint_normalizes_aware_date(self, journal):
        entry = Entry(journal, date=datetime.datetime(2024, 6, 15, 10, 0), text="T")
        utc_dt = datetime.datetime(
            2024, 1, 15, 14, 30, tzinfo=datetime.timezone.utc
        )
        entry.date = utc_dt

        expected = utc_dt.astimezone().replace(tzinfo=None)
        printed = entry.pprint()
        expected_str = expected.strftime(journal.config["timeformat"])
        assert expected_str in printed

    def test_entry_repr_normalizes_aware_date(self, journal):
        entry = Entry(journal, date=datetime.datetime(2024, 6, 15, 10, 0), text="Title")
        utc_dt = datetime.datetime(
            2024, 11, 15, 9, 0, tzinfo=datetime.timezone.utc
        )
        entry.date = utc_dt

        expected = utc_dt.astimezone().replace(tzinfo=None)
        repr_str = repr(entry)
        expected_str = expected.strftime("%Y-%m-%d %H:%M")
        assert expected_str in repr_str


class TestJournalParseDstAwareInputs:
    @pytest.fixture
    def journal(self):
        j = Journal("test", timeformat="%Y-%m-%d %H:%M")
        j.config["colors"] = {"body": "none", "date": "none", "tags": "none", "title": "none"}
        j.config["linewrap"] = False
        j.config["indent_character"] = ""
        j.config["highlight"] = True
        j.config["tag_symbols"] = ["@"]
        return j

    def test_utc_z_string_around_march_clock_change(self, journal):
        journal_txt = "[2024-03-10T12:00:00Z] Post spring forward\nBody\n"
        entries = journal._parse(journal_txt)
        assert len(entries) == 1
        entry = entries[0]

        utc_dt = datetime.datetime(
            2024, 3, 10, 12, 0, tzinfo=datetime.timezone.utc
        )
        expected = utc_dt.astimezone().replace(tzinfo=None)
        assert entry.date == expected
        assert entry.date.tzinfo is None

    def test_utc_z_string_around_november_clock_change(self, journal):
        journal_txt = "[2024-11-03T05:30:00Z] Pre fall back\nBody\n"
        entries = journal._parse(journal_txt)
        assert len(entries) == 1
        entry = entries[0]

        utc_dt = datetime.datetime(
            2024, 11, 3, 5, 30, tzinfo=datetime.timezone.utc
        )
        expected = utc_dt.astimezone().replace(tzinfo=None)
        assert entry.date == expected
        assert entry.date.tzinfo is None

    def test_strptime_with_tz_format_dst_summer(self, journal):
        journal_tz = Journal("test", timeformat="%Y-%m-%d %H:%M %z")
        journal_txt = "[2024-06-15 14:30 +0000] Summer UTC entry\nBody\n"
        entries = journal_tz._parse(journal_txt)
        assert len(entries) == 1

        utc_dt = datetime.datetime(
            2024, 6, 15, 14, 30, tzinfo=datetime.timezone.utc
        )
        expected = utc_dt.astimezone().replace(tzinfo=None)
        assert entries[0].date == expected
        assert entries[0].date.tzinfo is None

    def test_strptime_with_tz_format_dst_winter(self, journal):
        journal_tz = Journal("test", timeformat="%Y-%m-%d %H:%M %z")
        journal_txt = "[2024-01-15 14:30 +0000] Winter UTC entry\nBody\n"
        entries = journal_tz._parse(journal_txt)
        assert len(entries) == 1

        utc_dt = datetime.datetime(
            2024, 1, 15, 14, 30, tzinfo=datetime.timezone.utc
        )
        expected = utc_dt.astimezone().replace(tzinfo=None)
        assert entries[0].date == expected
        assert entries[0].date.tzinfo is None


class TestRoundTripConsistency:
    def test_parse_serialize_parse_preserves_local_semantics(self):
        """Round-trip: parse journal with UTC timestamps, serialize, parse again.

        The parsed local times must remain identical across both parses.
        Any discrepancy would indicate a DST or timezone inconsistency
        between the read and write paths.
        """
        journal = Journal("test", timeformat="%Y-%m-%d %H:%M")
        journal.config["colors"] = {"body": "none", "date": "none", "tags": "none", "title": "none"}
        journal.config["linewrap"] = False
        journal.config["indent_character"] = ""
        journal.config["highlight"] = True
        journal.config["tag_symbols"] = ["@"]

        original_txt = (
            "[2024-01-15T14:30:00Z] Winter entry\nWinter body\n\n"
            "[2024-06-15T14:30:00Z] Summer entry\nSummer body\n\n"
            "[2024-03-10T12:00:00Z] Post spring-forward\nBody\n\n"
            "[2024-11-03T06:00:00Z] Post fall-back\nBody\n"
        )

        parsed_first = journal._parse(original_txt)
        assert len(parsed_first) == 4

        dates_first = [e.date for e in parsed_first]

        # Round-trip: write entries back out using __str__
        re_serialized = "\n".join(str(e) for e in parsed_first)

        # Parse again
        parsed_second = journal._parse(re_serialized)
        assert len(parsed_second) == 4

        dates_second = [e.date for e in parsed_second]

        # Local moments must match exactly
        for d1, d2 in zip(dates_first, dates_second):
            assert d1 == d2, f"Round-trip mismatch: {d1} != {d2}"
            assert d1.tzinfo is None
            assert d2.tzinfo is None

    def test_entry_init_with_now_equivalence(self):
        """An entry created at time T should match Entry(date=parse('now'))."""
        journal = Journal("test", timeformat="%Y-%m-%d %H:%M")
        journal.config["colors"] = {"body": "none", "date": "none", "tags": "none", "title": "none"}
        journal.config["linewrap"] = False
        journal.config["indent_character"] = ""
        journal.config["highlight"] = True
        journal.config["tag_symbols"] = ["@"]

        now = datetime.datetime.now()
        entry_now = Entry(journal, text="Now entry")
        entry_explicit = Entry(journal, date=now, text="Explicit entry")

        # Both entries should reference essentially the same local moment
        # (within a few seconds due to call ordering)
        diff_seconds = abs(
            (entry_now.date - entry_explicit.date).total_seconds()
        )
        assert diff_seconds < 5

        # Both should be naive local datetime
        assert entry_now.date.tzinfo is None
        assert entry_explicit.date.tzinfo is None
