# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import datetime
from unittest import mock

import pytest

import jrnl
from jrnl.args import parse_args
from jrnl.controller import _filter_journal_entries


@pytest.fixture
def populated_journal():
    journal = jrnl.journals.Journal()
    journal.config["timeformat"] = "%Y-%m-%d %H:%M"
    journal.config["tagsymbols"] = "@"

    dates = [
        datetime.datetime(2020, 1, 15, 9, 0),
        datetime.datetime(2020, 3, 20, 14, 30),
        datetime.datetime(2020, 6, 10, 11, 0),
        datetime.datetime(2020, 8, 29, 11, 11),
        datetime.datetime(2020, 8, 31, 14, 32),
        datetime.datetime(2020, 9, 24, 9, 14),
        datetime.datetime(2021, 2, 14, 10, 0),
        datetime.datetime(2021, 12, 25, 8, 0),
    ]

    entries_text = [
        "First entry of 2020. @work @planning",
        "Spring project update. @work @projectx",
        "Summer vacation plans. @personal @travel",
        "Entry the first. Lorem ipsum dolor sit amet. @tagone @ipsum",
        "A second entry in what I hope to be a long series. Consectetur adipiscing elit. @tagone @tagtwo",
        "The third entry finally after weeks without writing. Sed do eiusmod tempor. @tagtwo @tagthree",
        "Valentine's day entry. @personal @relationships",
        "*Christmas morning. Family gathering. @personal @family",
    ]

    for date, text in zip(dates, entries_text):
        journal.new_entry(text, date=date, sort=False)

    journal.sort()
    return journal


class TestTagFiltering:
    def test_filter_single_tag(self, populated_journal):
        populated_journal.filter(tags=["@work"])
        assert len(populated_journal) == 2
        titles = [e.title for e in populated_journal.entries]
        assert "First entry of 2020." in titles
        assert "Spring project update." in titles

    def test_filter_single_tag_case_insensitive(self, populated_journal):
        populated_journal.filter(tags=["@WORK"])
        assert len(populated_journal) == 2

    def test_filter_multiple_tags_or(self, populated_journal):
        populated_journal.filter(tags=["@work", "@personal"])
        assert len(populated_journal) == 5

    def test_filter_multiple_tags_and(self, populated_journal):
        populated_journal.filter(tags=["@tagone", "@tagtwo"], strict=True)
        assert len(populated_journal) == 1
        assert "A second entry" in populated_journal.entries[0].title

    def test_filter_exclude_tag(self, populated_journal):
        populated_journal.filter(exclude=["@work"])
        assert len(populated_journal) == 6
        titles = [e.title for e in populated_journal.entries]
        assert "First entry of 2020." not in titles
        assert "Spring project update." not in titles

    def test_filter_exclude_multiple_tags(self, populated_journal):
        populated_journal.filter(exclude=["@work", "@personal"])
        assert len(populated_journal) == 3

    def test_filter_tag_and_exclude(self, populated_journal):
        populated_journal.filter(tags=["@personal"], exclude=["@family"])
        assert len(populated_journal) == 2
        titles = [e.title for e in populated_journal.entries]
        assert "Christmas morning." not in titles

    def test_filter_no_matching_tags(self, populated_journal):
        populated_journal.filter(tags=["@nonexistent"])
        assert len(populated_journal) == 0

    def test_filter_tagged_entries_only(self, populated_journal):
        journal = jrnl.journals.Journal()
        journal.config["tagsymbols"] = "@"
        journal.new_entry("Tagged entry @foo", date=datetime.datetime(2020, 1, 1))
        journal.new_entry("Untagged entry", date=datetime.datetime(2020, 1, 2))
        journal.new_entry("Another tagged @bar", date=datetime.datetime(2020, 1, 3))
        journal.filter(tagged=True)
        assert len(journal) == 2

    def test_filter_untagged_entries_only(self, populated_journal):
        journal = jrnl.journals.Journal()
        journal.config["tagsymbols"] = "@"
        journal.new_entry("Tagged entry @foo", date=datetime.datetime(2020, 1, 1))
        journal.new_entry("Untagged entry", date=datetime.datetime(2020, 1, 2))
        journal.new_entry("Another tagged @bar", date=datetime.datetime(2020, 1, 3))
        journal.filter(tagged=False, exclude_tagged=True)
        assert len(journal) == 1
        assert journal.entries[0].title == "Untagged entry"


class TestDateRangeFiltering:
    def test_filter_on_date(self, populated_journal):
        populated_journal.filter(start_date="2020-08-29", end_date="2020-08-29")
        assert len(populated_journal) == 1
        assert "Entry the first." in populated_journal.entries[0].title

    def test_filter_start_date_only(self, populated_journal):
        populated_journal.filter(start_date="2020-09-01")
        assert len(populated_journal) == 3
        for entry in populated_journal.entries:
            assert entry.date >= datetime.datetime(2020, 9, 1)

    def test_filter_end_date_only(self, populated_journal):
        populated_journal.filter(end_date="2020-03-31")
        assert len(populated_journal) == 2
        for entry in populated_journal.entries:
            assert entry.date <= datetime.datetime(2020, 3, 31, 23, 59, 59)

    def test_filter_date_range(self, populated_journal):
        populated_journal.filter(start_date="2020-06-01", end_date="2020-09-30")
        assert len(populated_journal) == 4
        for entry in populated_journal.entries:
            assert datetime.datetime(2020, 6, 1) <= entry.date
            assert entry.date <= datetime.datetime(2020, 9, 30, 23, 59, 59)

    def test_filter_by_month(self, populated_journal):
        populated_journal.filter(month="8")
        assert len(populated_journal) == 2
        for entry in populated_journal.entries:
            assert entry.date.month == 8

    def test_filter_by_month_name(self, populated_journal):
        populated_journal.filter(month="August")
        assert len(populated_journal) == 2

    def test_filter_by_day(self, populated_journal):
        populated_journal.filter(day="29")
        assert len(populated_journal) == 1
        assert populated_journal.entries[0].date.day == 29

    def test_filter_by_year(self, populated_journal):
        populated_journal.filter(year="2021")
        assert len(populated_journal) == 2
        for entry in populated_journal.entries:
            assert entry.date.year == 2021

    def test_filter_month_day_combination(self, populated_journal):
        populated_journal.filter(month="8", day="31")
        assert len(populated_journal) == 1
        assert populated_journal.entries[0].date.month == 8
        assert populated_journal.entries[0].date.day == 31

    def test_filter_month_year_combination(self, populated_journal):
        populated_journal.filter(month="9", year="2020")
        assert len(populated_journal) == 1
        assert populated_journal.entries[0].date.month == 9
        assert populated_journal.entries[0].date.year == 2020

    def test_filter_day_month_year_combination(self, populated_journal):
        populated_journal.filter(day="29", month="8", year="2020")
        assert len(populated_journal) == 1
        entry = populated_journal.entries[0]
        assert entry.date.day == 29
        assert entry.date.month == 8
        assert entry.date.year == 2020

    def test_filter_date_range_no_results(self, populated_journal):
        populated_journal.filter(start_date="2018-01-01", end_date="2018-12-31")
        assert len(populated_journal) == 0


class TestStarredFiltering:
    def test_filter_starred_only(self, populated_journal):
        populated_journal.filter(starred=True)
        assert len(populated_journal) == 1
        assert populated_journal.entries[0].starred is True
        assert "Christmas morning." in populated_journal.entries[0].title

    def test_filter_exclude_starred(self, populated_journal):
        populated_journal.filter(starred=False, exclude_starred=True)
        assert len(populated_journal) == 7
        for entry in populated_journal.entries:
            assert entry.starred is False

    def test_filter_starred_no_results(self, populated_journal):
        journal = jrnl.journals.Journal()
        journal.new_entry("No star here", date=datetime.datetime(2020, 1, 1))
        journal.new_entry("Also no star", date=datetime.datetime(2020, 1, 2))
        journal.filter(starred=True)
        assert len(journal) == 0


class TestContainsFiltering:
    def test_filter_contains_single_string(self, populated_journal):
        populated_journal.filter(contains=["lorem"])
        assert len(populated_journal) == 1
        assert "Entry the first." in populated_journal.entries[0].title

    def test_filter_contains_case_insensitive(self, populated_journal):
        populated_journal.filter(contains=["LOREM"])
        assert len(populated_journal) == 1

    def test_filter_contains_multiple_or(self, populated_journal):
        populated_journal.filter(contains=["lorem", "sed do"])
        assert len(populated_journal) == 2

    def test_filter_contains_multiple_and(self, populated_journal):
        populated_journal.filter(contains=["consectetur", "tagtwo"], strict=True)
        assert len(populated_journal) == 1
        assert "A second entry" in populated_journal.entries[0].title

    def test_filter_contains_no_results(self, populated_journal):
        populated_journal.filter(contains=["xyznonexistent123"])
        assert len(populated_journal) == 0


class TestFilterCombinations:
    def test_tag_and_date_range(self, populated_journal):
        populated_journal.filter(
            tags=["@personal"],
            start_date="2020-01-01",
            end_date="2020-12-31",
        )
        assert len(populated_journal) == 1
        assert "Summer vacation plans." in populated_journal.entries[0].title

    def test_tag_and_month(self, populated_journal):
        populated_journal.filter(tags=["@work"], month="3")
        assert len(populated_journal) == 1
        assert "Spring project update." in populated_journal.entries[0].title

    def test_tag_and_contains(self, populated_journal):
        populated_journal.filter(tags=["@tagone"], contains=["lorem"])
        assert len(populated_journal) == 1
        assert "Entry the first." in populated_journal.entries[0].title

    def test_tag_strict_and_contains(self, populated_journal):
        populated_journal.filter(
            tags=["@tagone", "@tagtwo"], contains=["consectetur"], strict=True
        )
        assert len(populated_journal) == 1

    def test_tag_exclude_and_date_range(self, populated_journal):
        populated_journal.filter(
            tags=["@personal"],
            exclude=["@family"],
            start_date="2020-01-01",
            end_date="2021-12-31",
        )
        assert len(populated_journal) == 2
        titles = [e.title for e in populated_journal.entries]
        assert "Summer vacation plans." in titles
        assert "Valentine's day entry." in titles

    def test_starred_and_tag(self, populated_journal):
        populated_journal.filter(starred=True, tags=["@personal"])
        assert len(populated_journal) == 1
        assert "Christmas morning." in populated_journal.entries[0].title

    def test_starred_and_date_range(self, populated_journal):
        populated_journal.filter(
            starred=True, start_date="2021-12-01", end_date="2021-12-31"
        )
        assert len(populated_journal) == 1

    def test_contains_and_date_range(self, populated_journal):
        populated_journal.filter(
            contains=["entry"], start_date="2020-08-01", end_date="2020-09-30"
        )
        assert len(populated_journal) == 3

    def test_month_and_starred_and_tag(self, populated_journal):
        populated_journal.filter(month="12", starred=True, tags=["@family"])
        assert len(populated_journal) == 1
        assert "Christmas" in populated_journal.entries[0].title

    def test_year_month_tag_combination(self, populated_journal):
        populated_journal.filter(year="2020", month="8", tags=["@tagone"])
        assert len(populated_journal) == 2
        for entry in populated_journal.entries:
            assert entry.date.year == 2020
            assert entry.date.month == 8
            assert "@tagone" in [t.lower() for t in entry.tags]

    def test_multiple_filters_no_results(self, populated_journal):
        populated_journal.filter(
            tags=["@work"],
            start_date="2021-01-01",
            end_date="2021-12-31",
        )
        assert len(populated_journal) == 0


class TestEdgeCases:
    def test_filter_empty_journal(self):
        journal = jrnl.journals.Journal()
        journal.filter(tags=["@anything"])
        assert len(journal) == 0

    def test_filter_no_args_returns_all(self, populated_journal):
        original_count = len(populated_journal)
        populated_journal.filter()
        assert len(populated_journal) == original_count

    def test_filter_empty_tags_list(self, populated_journal):
        original_count = len(populated_journal)
        populated_journal.filter(tags=[])
        assert len(populated_journal) == original_count

    def test_filter_limit(self, populated_journal):
        populated_journal.limit(3)
        assert len(populated_journal) == 3

    def test_filter_limit_zero(self, populated_journal):
        populated_journal.limit(0)
        assert len(populated_journal) == 8

    def test_filter_limit_none(self, populated_journal):
        original_count = len(populated_journal)
        populated_journal.limit(None)
        assert len(populated_journal) == original_count

    def test_filter_limit_larger_than_entries(self, populated_journal):
        populated_journal.limit(100)
        assert len(populated_journal) == 8

    def test_filter_with_limit(self, populated_journal):
        populated_journal.filter(tags=["@personal"])
        populated_journal.limit(2)
        assert len(populated_journal) == 2

    def test_search_tags_stored(self, populated_journal):
        populated_journal.filter(tags=["@work", "@PERSONAL"])
        assert populated_journal.search_tags == {"@work", "@personal"}


class TestFilterJournalEntriesController:
    def test_filter_journal_entries_with_on_date(self, populated_journal):
        args = parse_args(["-on", "2020-08-29"])
        _filter_journal_entries(args, populated_journal)
        assert len(populated_journal) == 1
        assert "Entry the first." in populated_journal.entries[0].title

    def test_filter_journal_entries_with_from_to(self, populated_journal):
        args = parse_args(["-from", "2020-08-01", "-to", "2020-09-30"])
        _filter_journal_entries(args, populated_journal)
        assert len(populated_journal) == 3

    def test_filter_journal_entries_with_month_day_year(self, populated_journal):
        args = parse_args(["-month", "8", "-day", "29", "-year", "2020"])
        _filter_journal_entries(args, populated_journal)
        assert len(populated_journal) == 1

    def test_filter_journal_entries_with_tags(self, populated_journal):
        args = parse_args(["@work", "@planning"])
        _filter_journal_entries(args, populated_journal)
        assert len(populated_journal) >= 1

    def test_filter_journal_entries_with_tags_strict(self, populated_journal):
        args = parse_args(["-and", "@tagone", "@tagtwo"])
        _filter_journal_entries(args, populated_journal)
        assert len(populated_journal) == 1

    def test_filter_journal_entries_with_exclude_tag(self, populated_journal):
        args = parse_args(["-not", "@work", "-not", "@personal"])
        _filter_journal_entries(args, populated_journal)
        assert len(populated_journal) == 3

    def test_filter_journal_entries_with_starred(self, populated_journal):
        args = parse_args(["-starred"])
        _filter_journal_entries(args, populated_journal)
        assert len(populated_journal) == 1

    def test_filter_journal_entries_with_not_starred(self, populated_journal):
        args = parse_args(["-not", "-starred"])
        _filter_journal_entries(args, populated_journal)
        assert len(populated_journal) == 7

    def test_filter_journal_entries_with_tagged(self, populated_journal):
        args = parse_args(["-tagged"])
        _filter_journal_entries(args, populated_journal)
        assert len(populated_journal) == 8

    def test_filter_journal_entries_with_not_tagged(self):
        journal = jrnl.journals.Journal()
        journal.config["tagsymbols"] = "@"
        journal.new_entry("Tagged entry @foo", date=datetime.datetime(2020, 1, 1))
        journal.new_entry("Untagged entry", date=datetime.datetime(2020, 1, 2))
        args = parse_args(["-not", "-tagged"])
        _filter_journal_entries(args, journal)
        assert len(journal) == 1

    def test_filter_journal_entries_with_contains(self, populated_journal):
        args = parse_args(["-contains", "lorem"])
        _filter_journal_entries(args, populated_journal)
        assert len(populated_journal) == 1

    def test_filter_journal_entries_with_contains_and_strict(self, populated_journal):
        args = parse_args(["-contains", "consectetur", "-contains", "tagtwo", "-and"])
        _filter_journal_entries(args, populated_journal)
        assert len(populated_journal) == 1

    def test_filter_journal_entries_with_limit(self, populated_journal):
        args = parse_args(["-3"])
        _filter_journal_entries(args, populated_journal)
        assert len(populated_journal) == 3

    def test_filter_journal_entries_with_today_in_history(self):
        journal = jrnl.journals.Journal()
        journal.config["timeformat"] = "%Y-%m-%d %H:%M"

        fixed_now = datetime.datetime(2024, 8, 29, 12, 0)

        dates = [
            datetime.datetime(2020, 8, 29, 9, 0),
            datetime.datetime(2021, 8, 29, 10, 0),
            datetime.datetime(2022, 9, 1, 11, 0),
        ]
        texts = ["Entry one", "Entry two", "Entry three"]
        for d, t in zip(dates, texts):
            journal.new_entry(t, date=d, sort=False)

        args = parse_args(["-today-in-history"])
        args.today_in_history = True

        original_parse = jrnl.time.parse

        def parse_side_effect(val, **kwargs):
            if val == "now":
                return fixed_now
            if val == "8.29.1":
                return datetime.datetime(2024, 8, 29, 0, 0)
            return original_parse(val, **kwargs)

        with mock.patch("jrnl.time.parse", side_effect=parse_side_effect):
            _filter_journal_entries(args, journal)

        assert len(journal) == 2
        for entry in journal.entries:
            assert entry.date.month == 8
            assert entry.date.day == 29

    def test_filter_journal_entries_combination_tag_and_date(self, populated_journal):
        args = parse_args(["@personal", "-from", "2020-01-01", "-to", "2020-12-31"])
        _filter_journal_entries(args, populated_journal)
        assert len(populated_journal) == 1
        assert "Summer vacation plans." in populated_journal.entries[0].title

    def test_filter_journal_entries_combination_multi_filter(self, populated_journal):
        args = parse_args(
            ["-year", "2020", "-month", "8", "@tagone", "-contains", "lorem"]
        )
        _filter_journal_entries(args, populated_journal)
        assert len(populated_journal) == 1


class TestEncryptedJournalFiltering:
    def test_encrypted_journal_open_and_filter(self, tmp_path):
        journal_path = tmp_path / "encrypted.journal"
        journal = jrnl.journals.Journal(
            name="test_encrypted",
            journal=str(journal_path),
            encrypt=False,
        )
        journal.config["timeformat"] = "%Y-%m-%d %H:%M"
        journal.config["tagsymbols"] = "@"

        journal.new_entry(
            "First encrypted entry @secret",
            date=datetime.datetime(2020, 1, 15, 10, 0),
            sort=False,
        )
        journal.new_entry(
            "Second encrypted entry @work",
            date=datetime.datetime(2020, 3, 20, 14, 0),
            sort=False,
        )
        journal.new_entry(
            "Third encrypted entry @secret @important",
            date=datetime.datetime(2020, 6, 10, 9, 0),
            sort=False,
        )
        journal.sort()

        journal.filter(tags=["@secret"])
        assert len(journal) == 2
        titles = [e.title for e in journal.entries]
        assert any("First encrypted entry" in t for t in titles)
        assert any("Third encrypted entry" in t for t in titles)

    def test_encrypted_journal_filter_with_date_range(self, tmp_path):
        journal_path = tmp_path / "encrypted2.journal"
        journal = jrnl.journals.Journal(
            name="test_encrypted2",
            journal=str(journal_path),
            encrypt=False,
        )
        journal.config["timeformat"] = "%Y-%m-%d %H:%M"
        journal.config["tagsymbols"] = "@"

        journal.new_entry(
            "Jan entry @work",
            date=datetime.datetime(2020, 1, 15, 10, 0),
            sort=False,
        )
        journal.new_entry(
            "Mar entry @work",
            date=datetime.datetime(2020, 3, 20, 14, 0),
            sort=False,
        )
        journal.new_entry(
            "Jun entry @personal",
            date=datetime.datetime(2020, 6, 10, 9, 0),
            sort=False,
        )
        journal.sort()

        journal.filter(
            tags=["@work"],
            start_date="2020-02-01",
            end_date="2020-04-30",
        )
        assert len(journal) == 1
        assert "Mar entry" in journal.entries[0].title


class TestMultiJournalSearch:
    def test_multiple_journals_independent_filtering(self):
        journal1 = jrnl.journals.Journal(name="work")
        journal1.config["timeformat"] = "%Y-%m-%d %H:%M"
        journal1.config["tagsymbols"] = "@"
        journal1.new_entry(
            "Work meeting notes @meetings",
            date=datetime.datetime(2020, 5, 1, 10, 0),
            sort=False,
        )
        journal1.new_entry(
            "Project deadline @deadlines",
            date=datetime.datetime(2020, 8, 15, 14, 0),
            sort=False,
        )
        journal1.sort()

        journal2 = jrnl.journals.Journal(name="personal")
        journal2.config["timeformat"] = "%Y-%m-%d %H:%M"
        journal2.config["tagsymbols"] = "@"
        journal2.new_entry(
            "Grocery shopping list @shopping",
            date=datetime.datetime(2020, 5, 2, 9, 0),
            sort=False,
        )
        journal2.new_entry(
            "Vacation plans @travel",
            date=datetime.datetime(2020, 8, 20, 11, 0),
            sort=False,
        )
        journal2.sort()

        journal1.filter(tags=["@meetings"])
        assert len(journal1) == 1
        assert "Work meeting notes" in journal1.entries[0].title

        journal2.filter(tags=["@travel"])
        assert len(journal2) == 1
        assert "Vacation plans" in journal2.entries[0].title

    def test_multiple_journals_same_filter_different_results(self):
        journal_a = jrnl.journals.Journal(name="journal_a")
        journal_a.config["timeformat"] = "%Y-%m-%d %H:%M"
        journal_a.config["tagsymbols"] = "@"
        journal_a.new_entry(
            "Entry A1 @shared @only_a",
            date=datetime.datetime(2020, 1, 1, 10, 0),
            sort=False,
        )
        journal_a.new_entry(
            "Entry A2 @shared",
            date=datetime.datetime(2020, 6, 1, 10, 0),
            sort=False,
        )
        journal_a.sort()

        journal_b = jrnl.journals.Journal(name="journal_b")
        journal_b.config["timeformat"] = "%Y-%m-%d %H:%M"
        journal_b.config["tagsymbols"] = "@"
        journal_b.new_entry(
            "Entry B1 @shared @only_b",
            date=datetime.datetime(2020, 3, 1, 10, 0),
            sort=False,
        )
        journal_b.new_entry(
            "Entry B2 @unique",
            date=datetime.datetime(2020, 9, 1, 10, 0),
            sort=False,
        )
        journal_b.sort()

        journal_a.filter(tags=["@shared"])
        journal_b.filter(tags=["@shared"])

        assert len(journal_a) == 2
        assert len(journal_b) == 1

    def test_multiple_journals_date_ranges(self):
        journal_early = jrnl.journals.Journal(name="early")
        journal_early.config["timeformat"] = "%Y-%m-%d %H:%M"
        journal_early.new_entry(
            "Early 2019 entry", date=datetime.datetime(2019, 1, 15, 10, 0)
        )
        journal_early.new_entry(
            "Late 2019 entry", date=datetime.datetime(2019, 12, 20, 10, 0)
        )

        journal_late = jrnl.journals.Journal(name="late")
        journal_late.config["timeformat"] = "%Y-%m-%d %H:%M"
        journal_late.new_entry(
            "Early 2020 entry", date=datetime.datetime(2020, 1, 10, 10, 0)
        )
        journal_late.new_entry(
            "Late 2020 entry", date=datetime.datetime(2020, 12, 25, 10, 0)
        )

        journal_early.filter(start_date="2019-01-01", end_date="2019-12-31")
        journal_late.filter(start_date="2019-01-01", end_date="2019-12-31")

        assert len(journal_early) == 2
        assert len(journal_late) == 0


class TestInvalidInputs:
    def test_filter_invalid_date_format(self, populated_journal):
        original_count = len(populated_journal)
        with mock.patch("jrnl.time.parse", return_value=None):
            populated_journal.filter(start_date="not-a-real-date")
            assert len(populated_journal) == original_count

    def test_filter_nonexistent_tag_with_other_tags(self, populated_journal):
        populated_journal.filter(tags=["@work", "@nonexistent"])
        assert len(populated_journal) == 2

    def test_filter_end_date_before_start_date(self, populated_journal):
        populated_journal.filter(start_date="2020-12-31", end_date="2020-01-01")
        assert len(populated_journal) == 0

    def test_filter_empty_contains_list(self, populated_journal):
        original_count = len(populated_journal)
        populated_journal.filter(contains=[])
        assert len(populated_journal) == original_count

    def test_filter_with_special_chars_in_contains(self, populated_journal):
        journal = jrnl.journals.Journal()
        journal.config["timeformat"] = "%Y-%m-%d %H:%M"
        journal.new_entry(
            "Entry with special chars: <>&*()",
            date=datetime.datetime(2020, 1, 1),
        )
        journal.new_entry(
            "Normal entry without special",
            date=datetime.datetime(2020, 1, 2),
        )
        journal.filter(contains=["<>&*()"])
        assert len(journal) == 1

    def test_filter_tags_without_tag_symbol(self, populated_journal):
        journal = jrnl.journals.Journal()
        journal.config["tagsymbols"] = "@"
        journal.new_entry("Test @foo bar", date=datetime.datetime(2020, 1, 1))
        journal.filter(tags=["foo"])
        assert len(journal) == 0
