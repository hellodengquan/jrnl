# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import datetime
import os
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


def _set_tz(tz_name: str) -> None:
    """Set the local timezone via TZ env var and refresh C library state."""
    os.environ["TZ"] = tz_name
    time_module.tzset()


def _restore_tz(original_tz: str | None) -> None:
    """Restore the original timezone."""
    if original_tz is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = original_tz
    time_module.tzset()


@pytest.fixture
def sydney_tz():
    """Temporarily set the local timezone to Australia/Sydney (southern hemisphere).

    Sydney observes DST with the pattern OPPOSITE to the northern hemisphere:
    - Summer (Oct-Apr): AEDT, UTC+11 (daylight time)
    - Winter (Apr-Oct): AEST, UTC+10 (standard time)
    - Spring forward: 1st Sunday in October (clocks go from 2:00 -> 3:00 AM)
    - Fall back: 1st Sunday in April (clocks go from 3:00 -> 2:00 AM)
    """
    original = os.environ.get("TZ")
    _set_tz("Australia/Sydney")
    try:
        yield
    finally:
        _restore_tz(original)


class TestSouthernHemisphereDst:
    """Tests that timezone normalization works correctly for southern hemisphere
    timezones where DST transitions happen in opposite months to the north."""

    @pytest.fixture
    def journal(self, sydney_tz):
        j = Journal("test", timeformat="%Y-%m-%d %H:%M")
        j.config["colors"] = {
            "body": "none",
            "date": "none",
            "tags": "none",
            "title": "none",
        }
        j.config["linewrap"] = False
        j.config["indent_character"] = ""
        j.config["highlight"] = True
        j.config["tag_symbols"] = ["@"]
        return j

    def test_southern_summer_has_daylight_offset(self, sydney_tz):
        """January (summer in Sydney) should use AEDT (UTC+11)."""
        utc_dt = datetime.datetime(
            2024, 1, 15, 0, 30, tzinfo=datetime.timezone.utc
        )
        result = jrnl_time.convert_aware_to_local_naive(utc_dt)
        expected = utc_dt.astimezone().replace(tzinfo=None)
        assert result == expected
        # AEDT is UTC+11, so 00:30 UTC -> 11:30 Sydney
        assert result.hour == 11
        assert result.tzinfo is None

    def test_southern_winter_has_standard_offset(self, sydney_tz):
        """July (winter in Sydney) should use AEST (UTC+10)."""
        utc_dt = datetime.datetime(
            2024, 7, 15, 0, 30, tzinfo=datetime.timezone.utc
        )
        result = jrnl_time.convert_aware_to_local_naive(utc_dt)
        expected = utc_dt.astimezone().replace(tzinfo=None)
        assert result == expected
        # AEST is UTC+10, so 00:30 UTC -> 10:30 Sydney
        assert result.hour == 10
        assert result.tzinfo is None

    def test_spring_forward_october_southern(self, sydney_tz):
        """Sydney spring forward happens in October (northern hemisphere fall).

        2024-10-06 02:00 AM local -> 03:00 AM local (clocks jump forward).
        In UTC terms: 2024-10-05 16:00 UTC is the transition point.
        Before: AEST (UTC+10), after: AEDT (UTC+11).
        """
        # Just before transition: 15:59 UTC = 01:59 AEST (standard time exists)
        utc_before = datetime.datetime(
            2024, 10, 5, 15, 59, tzinfo=datetime.timezone.utc
        )
        local_before = jrnl_time.convert_aware_to_local_naive(utc_before)
        assert local_before.hour == 1  # 01:59 AM AEST
        assert local_before.day == 6

        # Just after transition: 16:00 UTC = 03:00 AEDT (daylight time)
        utc_after = datetime.datetime(
            2024, 10, 5, 16, 0, tzinfo=datetime.timezone.utc
        )
        local_after = jrnl_time.convert_aware_to_local_naive(utc_after)
        assert local_after.hour == 3  # 03:00 AM AEDT
        assert local_after.day == 6

    def test_fall_back_april_southern(self, sydney_tz):
        """Sydney fall back happens in April (northern hemisphere spring).

        2024-04-07 03:00 AM local -> 02:00 AM local (clocks go back).
        In UTC terms: 2024-04-06 16:00 UTC is the transition point.
        Before: AEDT (UTC+11), after: AEST (UTC+10).
        """
        # Just before transition: 15:59 UTC = 02:59 AEDT (first 02:xx hour)
        utc_before = datetime.datetime(
            2024, 4, 6, 15, 59, tzinfo=datetime.timezone.utc
        )
        local_before = jrnl_time.convert_aware_to_local_naive(utc_before)
        assert local_before.hour == 2  # 02:59 AM AEDT
        assert local_before.day == 7

        # Just after transition: 16:00 UTC = 02:00 AEST (second 02:xx hour)
        utc_after = datetime.datetime(
            2024, 4, 6, 16, 0, tzinfo=datetime.timezone.utc
        )
        local_after = jrnl_time.convert_aware_to_local_naive(utc_after)
        assert local_after.hour == 2  # 02:00 AM AEST (fold=1)
        assert local_after.day == 7

    def test_entry_date_setter_southern_dst(self, journal):
        """Entry date property normalizes correctly under southern-hemisphere DST."""
        utc_dt = datetime.datetime(
            2024, 1, 20, 10, 0, tzinfo=datetime.timezone.utc
        )
        entry = Entry(journal, date=utc_dt, text="Summer entry")
        expected = utc_dt.astimezone().replace(tzinfo=None)
        assert entry.date == expected
        assert entry.date.tzinfo is None
        # AEDT (UTC+11): 10:00 UTC -> 21:00 Sydney
        assert entry.date.hour == 21

    def test_roundtrip_southern_hemisphere(self, journal):
        """Parse-serialize-parse roundtrip works under southern-hemisphere timezone."""
        original_txt = (
            "[2024-01-15T00:30:00Z] Summer entry (AEDT)\nBody\n\n"
            "[2024-07-15T00:30:00Z] Winter entry (AEST)\nBody\n\n"
            "[2024-10-05T16:30:00Z] Post spring-forward\nBody\n\n"
            "[2024-04-06T16:30:00Z] Post fall-back\nBody\n"
        )

        parsed_first = journal._parse(original_txt)
        assert len(parsed_first) == 4

        dates_first = [e.date for e in parsed_first]

        # Round-trip
        re_serialized = "\n".join(str(e) for e in parsed_first)
        parsed_second = journal._parse(re_serialized)
        assert len(parsed_second) == 4

        dates_second = [e.date for e in parsed_second]

        for d1, d2 in zip(dates_first, dates_second):
            assert d1 == d2
            assert d1.tzinfo is None
            assert d2.tzinfo is None

    def test_strptime_tz_format_southern_winter(self, sydney_tz):
        """strptime with %z format works correctly in southern winter."""
        journal_tz = Journal("test", timeformat="%Y-%m-%d %H:%M %z")
        journal_txt = "[2024-07-15 00:30 +0000] Winter UTC entry\nBody\n"
        entries = journal_tz._parse(journal_txt)
        assert len(entries) == 1
        # AEST = UTC+10, 00:30 UTC -> 10:30 Sydney
        assert entries[0].date.hour == 10
        assert entries[0].date.tzinfo is None

    def test_strptime_tz_format_southern_summer(self, sydney_tz):
        """strptime with %z format works correctly in southern summer."""
        journal_tz = Journal("test", timeformat="%Y-%m-%d %H:%M %z")
        journal_txt = "[2024-01-15 00:30 +0000] Summer UTC entry\nBody\n"
        entries = journal_tz._parse(journal_txt)
        assert len(entries) == 1
        # AEDT = UTC+11, 00:30 UTC -> 11:30 Sydney
        assert entries[0].date.hour == 11
        assert entries[0].date.tzinfo is None

    def test_modified_flag_not_set_by_normalization(self, journal):
        """Setting an aware datetime that normalizes to the same local time
        must NOT flip the modified flag to True. The date setter only
        normalizes; modified is a business-level concern.
        """
        # Start with a naive local datetime
        local_dt = datetime.datetime(2024, 1, 15, 11, 30)  # 11:30 AM Sydney
        entry = Entry(journal, date=local_dt, text="Test")
        assert entry.modified is False

        # Now set the same moment expressed as a UTC aware datetime
        # (11:30 AEDT = 00:30 UTC)
        utc_equivalent = datetime.datetime(
            2024, 1, 15, 0, 30, tzinfo=datetime.timezone.utc
        )
        entry.date = utc_equivalent

        # The normalized date should be the same local time
        assert entry.date == local_dt
        # modified should still be False — the moment didn't change,
        # it was just expressed in a different timezone
        # (Note: modified is NOT auto-set by the date property setter)
        assert entry.modified is False

    def test_modified_flag_explicitly_set(self, journal):
        """Setting the date to a DIFFERENT moment should still allow the
        caller to explicitly mark the entry as modified."""
        entry = Entry(journal, date=datetime.datetime(2024, 1, 15, 10, 0), text="Test")
        assert entry.modified is False

        # Explicitly set a different date AND mark as modified
        new_date = datetime.datetime(2024, 1, 16, 14, 0, tzinfo=datetime.timezone.utc)
        entry.date = new_date
        entry.modified = True

        assert entry.modified is True
        # The date should be normalized to local time
        assert entry.date.tzinfo is None
        # Should be different from the original date
        assert entry.date != datetime.datetime(2024, 1, 15, 10, 0)


# Southern-hemisphere timezones with diverse DST behaviors:
# - Pacific/Auckland: NZ, large offset (+13/+12), DST active in southern summer
# - America/Santiago: Chile, western hemisphere southern DST (-3/-4),
#   opposite sign and direction to eastern hemisphere
# - Australia/Perth: Western Australia, no DST, flat UTC+8 year-round
# - America/Sao_Paulo: Brazil, historically had DST but abolished ~2019, flat UTC-3
# - Africa/Johannesburg: South Africa, flat UTC+2, no DST
_MULTI_SOUTHERN_TZS = [
    "Pacific/Auckland",
    "America/Santiago",
    "Australia/Perth",
    "America/Sao_Paulo",
    "Africa/Johannesburg",
]


@pytest.fixture(params=_MULTI_SOUTHERN_TZS)
def southern_hemisphere_tz(request):
    """Parametrized fixture covering multiple southern-hemisphere timezones
    with diverse DST characteristics (DST, no-DST, western/eastern hemisphere)."""
    original = os.environ.get("TZ")
    _set_tz(request.param)
    try:
        yield request.param
    finally:
        _restore_tz(original)


class TestMultipleSouthernHemisphereTimezones:
    """Parametrized tests running across a diverse set of southern-hemisphere
    timezones to catch IANA-data edge cases (no-DST zones, western-hemisphere
    southern DST, abolished DST, etc.)."""

    @pytest.fixture
    def journal(self, southern_hemisphere_tz):
        j = Journal("test", timeformat="%Y-%m-%d %H:%M")
        j.config["colors"] = {
            "body": "none",
            "date": "none",
            "tags": "none",
            "title": "none",
        }
        j.config["linewrap"] = False
        j.config["indent_character"] = ""
        j.config["highlight"] = True
        j.config["tag_symbols"] = ["@"]
        return j

    def test_helper_jan_summer_matches_astimezone(self, southern_hemisphere_tz):
        """January is summer in the southern hemisphere."""
        utc_dt = datetime.datetime(
            2024, 1, 15, 12, 0, tzinfo=datetime.timezone.utc
        )
        expected = utc_dt.astimezone().replace(tzinfo=None)
        result = jrnl_time.convert_aware_to_local_naive(utc_dt)
        assert result == expected
        assert result.tzinfo is None

    def test_helper_jul_winter_matches_astimezone(self, southern_hemisphere_tz):
        """July is winter in the southern hemisphere."""
        utc_dt = datetime.datetime(
            2024, 7, 15, 12, 0, tzinfo=datetime.timezone.utc
        )
        expected = utc_dt.astimezone().replace(tzinfo=None)
        result = jrnl_time.convert_aware_to_local_naive(utc_dt)
        assert result == expected
        assert result.tzinfo is None

    def test_helper_non_utc_offset_converts(self, southern_hemisphere_tz):
        plus9 = datetime.timezone(datetime.timedelta(hours=9))
        dt = datetime.datetime(2024, 3, 20, 10, 30, tzinfo=plus9)
        expected = dt.astimezone().replace(tzinfo=None)
        result = jrnl_time.convert_aware_to_local_naive(dt)
        assert result == expected
        assert result.tzinfo is None

    def test_helper_naive_passthrough(self, southern_hemisphere_tz):
        naive = datetime.datetime(2024, 5, 1, 8, 0)
        result = jrnl_time.convert_aware_to_local_naive(naive)
        assert result == naive
        assert result.tzinfo is None

    def test_datetimes_equal_same_moment_different_tz_expressions(
        self, southern_hemisphere_tz
    ):
        """datetimes_equal should treat the same instant in different TZ
        representations as equal."""
        utc_dt = datetime.datetime(
            2024, 1, 15, 12, 0, tzinfo=datetime.timezone.utc
        )
        local_naive = utc_dt.astimezone().replace(tzinfo=None)
        assert jrnl_time.datetimes_equal(utc_dt, local_naive)

    def test_datetimes_equal_different_moments_not_equal(
        self, southern_hemisphere_tz
    ):
        a = datetime.datetime(2024, 1, 15, 12, 0, tzinfo=datetime.timezone.utc)
        b = datetime.datetime(2024, 1, 15, 13, 0, tzinfo=datetime.timezone.utc)
        assert not jrnl_time.datetimes_equal(a, b)

    def test_entry_date_property_normalizes(self, journal, southern_hemisphere_tz):
        utc_dt = datetime.datetime(
            2024, 4, 10, 9, 30, tzinfo=datetime.timezone.utc
        )
        entry = Entry(journal, date=utc_dt, text="Test")
        expected = utc_dt.astimezone().replace(tzinfo=None)
        assert entry.date == expected
        assert entry.date.tzinfo is None

    def test_roundtrip_parse_serialize_parse(self, journal, southern_hemisphere_tz):
        """The parse-serialize-parse roundtrip must be stable across all TZs."""
        original_txt = (
            "[2024-01-15T12:00:00Z] Jan entry\nBody1\n\n"
            "[2024-07-15T12:00:00Z] Jul entry\nBody2\n"
        )
        first = journal._parse(original_txt)
        assert len(first) == 2

        serialized = "\n".join(str(e) for e in first)
        second = journal._parse(serialized)
        assert len(second) == 2

        for a, b in zip(first, second):
            assert a.date == b.date
            assert a.date.tzinfo is None
            assert b.date.tzinfo is None


class TestNaiveAwareTypeError:
    """Tests that naive vs aware datetime comparisons never raise TypeError.

    Python raises TypeError when comparing a naive datetime with an aware one.
    All comparison paths in the codebase must avoid this.
    """

    @pytest.fixture
    def journal(self):
        j = Journal("test", timeformat="%Y-%m-%d %H:%M")
        j.config["colors"] = {
            "body": "none",
            "date": "none",
            "tags": "none",
            "title": "none",
        }
        j.config["linewrap"] = False
        j.config["indent_character"] = ""
        j.config["highlight"] = True
        j.config["tag_symbols"] = ["@"]
        return j

    def test_helper_datetimes_equal_no_typeerror(self, journal):
        naive = datetime.datetime(2024, 6, 15, 22, 30)
        aware_utc = datetime.datetime(
            2024, 6, 15, 14, 30, tzinfo=datetime.timezone.utc
        )
        # Must not raise TypeError
        result = jrnl_time.datetimes_equal(naive, aware_utc)
        assert isinstance(result, bool)

    def test_entry_eq_no_typeerror_mixed_naive_aware(self, journal):
        """Entry.__eq__ must not raise when dates have mixed tzinfo."""
        entry_naive = Entry(
            journal,
            date=datetime.datetime(2024, 6, 15, 22, 30),
            text="Same title",
        )
        entry_aware = Entry(
            journal,
            date=datetime.datetime(
                2024, 6, 15, 14, 30, tzinfo=datetime.timezone.utc
            ),
            text="Same title",
        )
        # Must not raise TypeError - the dates represent the same local moment
        # after normalization, so they should compare equal
        assert entry_naive == entry_aware

    def test_entry_eq_different_moments_not_equal_no_typeerror(self, journal):
        entry_a = Entry(
            journal,
            date=datetime.datetime(2024, 6, 15, 10, 0),
            text="title",
        )
        entry_b = Entry(
            journal,
            date=datetime.datetime(
                2024, 6, 16, 10, 0, tzinfo=datetime.timezone.utc
            ),
            text="title",
        )
        # Must not raise TypeError
        assert entry_a != entry_b

    def test_dayone_update_old_entry_no_typeerror(self, journal):
        """DayOne._update_old_entry must not raise TypeError for mixed dates."""
        from jrnl.journals.DayOneJournal import DayOne

        dayone = DayOne.__new__(DayOne)
        dayone.config = {"tagsymbols": ["@"]}

        old_entry = Entry(
            journal,
            date=datetime.datetime(2024, 6, 15, 22, 30),  # naive
            text="Body",
        )
        old_entry.modified = False

        # Same instant expressed as aware UTC
        same_instant = datetime.datetime(
            2024, 6, 15, 14, 30, tzinfo=datetime.timezone.utc
        )
        new_entry = Entry(journal, date=same_instant, text="Body")

        # Must not raise TypeError; same instant, so modified should stay False
        dayone._update_old_entry(old_entry, new_entry)
        assert old_entry.modified is False

    def test_dayone_update_old_entry_detects_real_change(self, journal):
        from jrnl.journals.DayOneJournal import DayOne

        dayone = DayOne.__new__(DayOne)
        dayone.config = {"tagsymbols": ["@"]}

        old_entry = Entry(
            journal,
            date=datetime.datetime(2024, 6, 15, 22, 30),
            text="Body",
        )
        old_entry.modified = False

        # Different instant (1 day later)
        different_instant = datetime.datetime(
            2024, 6, 16, 14, 30, tzinfo=datetime.timezone.utc
        )
        new_entry = Entry(journal, date=different_instant, text="Body")

        dayone._update_old_entry(old_entry, new_entry)
        assert old_entry.modified is True

    def test_journal_validate_parsing_no_typeerror(self, journal):
        """Journal.validate_parsing internally uses Entry.__eq__ and must
        not raise TypeError even when roundtrip normalization changes
        tzinfo representation."""
        original_txt = "[2024-06-15T14:30:00Z] Test entry\nBody\n"
        journal.entries = journal._parse(original_txt)
        # validate_parsing should not raise TypeError
        assert journal.validate_parsing() is True

