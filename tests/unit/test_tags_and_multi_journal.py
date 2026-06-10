# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import datetime
import os
import tempfile
from unittest import mock

import pytest

import jrnl
from jrnl.args import parse_args
from jrnl.config import DEFAULT_JOURNAL_KEY
from jrnl.config import get_journal_name
from jrnl.config import scope_config
from jrnl.config import validate_journal_name
from jrnl.exception import JrnlException
from jrnl.journals import Entry
from jrnl.journals import Journal


class TestEntryTagParsing:
    def test_tag_regex_single_symbol(self):
        pattern = Entry.tag_regex("@")
        result = pattern.findall("hello @world and @jrnl test")
        assert result == ["@world", "@jrnl"]

    def test_tag_regex_multiple_symbols(self):
        pattern = Entry.tag_regex("@#")
        result = pattern.findall("hello @world and #jrnl test")
        assert result == ["@world", "#jrnl"]

    def test_tag_regex_no_tags(self):
        pattern = Entry.tag_regex("@")
        result = pattern.findall("hello world no tags here")
        assert result == []

    def test_tag_regex_tags_with_special_chars(self):
        pattern = Entry.tag_regex("@")
        result = pattern.findall("@tag-with-dashes @tag_with_underscores @tag/with/slashes")
        assert result == ["@tag-with-dashes", "@tag_with_underscores", "@tag/with/slashes"]

    def test_tag_case_insensitive_parsing(self):
        journal = Journal()
        entry = Entry(journal, text="Hello @World and @WORLD and @world")
        assert entry.tags == ["@world"]

    def test_tag_parsing_title_and_body(self):
        journal = Journal()
        text = "My @idea is amazing.\nAnd I also love @jrnl"
        entry = Entry(journal, text=text)
        assert set(entry.tags) == {"@idea", "@jrnl"}

    def test_tag_parsing_duplicates_removed(self):
        journal = Journal()
        entry = Entry(journal, text="@tag @tag @TAG another @tag")
        assert entry.tags == ["@tag"]

    def test_tag_parsing_with_different_symbols(self):
        journal_config = {"tagsymbols": "#@!"}
        journal = Journal(**journal_config)
        entry = Entry(journal, text="#hash @at and !bang tags")
        assert set(entry.tags) == {"#hash", "@at", "!bang"}


class TestJournalFilterByTags:
    @pytest.fixture
    def journal_with_tags(self):
        journal = Journal()
        journal.new_entry(
            "2023-01-15 10:00: Meeting with @john and @jane about project @alpha",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        journal.new_entry(
            "2023-01-16 14:00: @jane asked about @beta project",
            date=datetime.datetime(2023, 1, 16, 14, 0),
        )
        journal.new_entry(
            "2023-01-17 09:00: Lunch with @bob",
            date=datetime.datetime(2023, 1, 17, 9, 0),
        )
        journal.new_entry(
            "2023-01-18 16:00: No tags here, just plain entry",
            date=datetime.datetime(2023, 1, 18, 16, 0),
        )
        journal.new_entry(
            "2023-01-19 11:00: @alpha and @beta meeting",
            date=datetime.datetime(2023, 1, 19, 11, 0),
        )
        return journal

    def test_filter_single_tag_or_mode(self, journal_with_tags):
        journal_with_tags.filter(tags=["@john"])
        assert len(journal_with_tags) == 1
        assert "@john" in journal_with_tags.entries[0].tags

    def test_filter_multiple_tags_or_mode(self, journal_with_tags):
        journal_with_tags.filter(tags=["@john", "@bob"])
        assert len(journal_with_tags) == 2

    def test_filter_multiple_tags_and_mode(self, journal_with_tags):
        journal_with_tags.filter(tags=["@alpha", "@beta"], strict=True)
        assert len(journal_with_tags) == 1
        assert "@alpha" in journal_with_tags.entries[0].tags
        assert "@beta" in journal_with_tags.entries[0].tags

    def test_filter_tag_case_insensitive(self, journal_with_tags):
        journal_with_tags.filter(tags=["@JOHN"])
        assert len(journal_with_tags) == 1

    def test_filter_exclude_tags(self, journal_with_tags):
        journal_with_tags.filter(exclude=["@jane"])
        assert len(journal_with_tags) == 3
        for entry in journal_with_tags.entries:
            assert "@jane" not in entry.tags

    def test_filter_tagged_only(self, journal_with_tags):
        journal_with_tags.filter(tagged=True)
        assert len(journal_with_tags) == 4

    def test_filter_untagged_only(self, journal_with_tags):
        journal_with_tags.filter(tagged=False, exclude_tagged=True)
        assert len(journal_with_tags) == 1
        assert len(journal_with_tags.entries[0].tags) == 0

    def test_filter_combined_tags_and_exclude(self, journal_with_tags):
        journal_with_tags.filter(tags=["@alpha"], exclude=["@jane"])
        assert len(journal_with_tags) == 1
        assert "@alpha" in journal_with_tags.entries[0].tags
        assert "@jane" not in journal_with_tags.entries[0].tags

    def test_filter_tags_nonexistent(self, journal_with_tags):
        journal_with_tags.filter(tags=["@nonexistent"])
        assert len(journal_with_tags) == 0


class TestJournalFilterByRelativeDates:
    @pytest.fixture
    def journal_with_dates(self):
        journal = Journal()
        base_date = datetime.datetime(2023, 6, 15, 12, 0)
        dates = [
            base_date - datetime.timedelta(days=10),
            base_date - datetime.timedelta(days=5),
            base_date - datetime.timedelta(days=1),
            base_date,
            base_date + datetime.timedelta(days=1),
            base_date + datetime.timedelta(days=5),
            base_date + datetime.timedelta(days=10),
        ]
        for i, d in enumerate(dates):
            journal.new_entry(f"Entry {i} for date {d}", date=d, sort=False)
        journal.sort()
        return journal, base_date

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


class TestMultiJournalIsolation:
    @pytest.fixture
    def temp_journal_dir(self):
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def multi_journal_config(self, temp_journal_dir):
        default_path = os.path.join(temp_journal_dir, "default.journal")
        work_path = os.path.join(temp_journal_dir, "work.journal")
        personal_path = os.path.join(temp_journal_dir, "personal.journal")

        return {
            "version": "4.0",
            "journals": {
                "default": {
                    "journal": default_path,
                    "tagsymbols": "@",
                },
                "work": {
                    "journal": work_path,
                    "tagsymbols": "#",
                    "linewrap": 100,
                },
                "personal": {
                    "journal": personal_path,
                    "tagsymbols": "@!",
                },
            },
            "editor": "",
            "encrypt": False,
            "default_hour": 9,
            "default_minute": 0,
            "timeformat": "%Y-%m-%d %H:%M",
            "highlight": True,
            "linewrap": 79,
            "indent_character": "|",
            "colors": {"body": "none", "date": "none", "tags": "none", "title": "none"},
        }

    def test_journal_data_isolation(self, multi_journal_config):
        journals = {}
        for name in ["default", "work", "personal"]:
            journal = Journal(
                name=name,
                **scope_config(multi_journal_config.copy(), name)
            )
            journals[name] = journal

        journals["default"].new_entry(
            "2023-01-01 09:00: Default entry @defaulttag",
            date=datetime.datetime(2023, 1, 1, 9, 0),
        )
        journals["work"].new_entry(
            "2023-01-02 10:00: Work entry #worktag",
            date=datetime.datetime(2023, 1, 2, 10, 0),
        )
        journals["personal"].new_entry(
            "2023-01-03 11:00: Personal entry @personaltag !family",
            date=datetime.datetime(2023, 1, 3, 11, 0),
        )

        assert len(journals["default"]) == 1
        assert len(journals["work"]) == 1
        assert len(journals["personal"]) == 1

        assert "@defaulttag" in journals["default"].entries[0].tags
        assert "#worktag" not in journals["default"].entries[0].tags

        assert "#worktag" in journals["work"].entries[0].tags
        assert "@defaulttag" not in journals["work"].entries[0].tags

        assert set(journals["personal"].entries[0].tags) == {"@personaltag", "!family"}

    def test_journal_config_isolation(self, multi_journal_config):
        default_config = scope_config(multi_journal_config.copy(), "default")
        work_config = scope_config(multi_journal_config.copy(), "work")
        personal_config = scope_config(multi_journal_config.copy(), "personal")

        assert default_config["tagsymbols"] == "@"
        assert work_config["tagsymbols"] == "#"
        assert personal_config["tagsymbols"] == "@!"

        assert default_config["linewrap"] == 79
        assert work_config["linewrap"] == 100

    def test_get_journal_name_from_args_default(self, multi_journal_config):
        args = parse_args(["some", "text"])
        args = get_journal_name(args, multi_journal_config)
        assert args.journal_name == DEFAULT_JOURNAL_KEY
        assert args.text == ["some", "text"]

    def test_get_journal_name_from_args_specific(self, multi_journal_config):
        args = parse_args(["work:", "meeting", "notes"])
        args = get_journal_name(args, multi_journal_config)
        assert args.journal_name == "work"
        assert args.text == ["meeting", "notes"]

    def test_get_journal_name_nonexistent_stays_default(self, multi_journal_config):
        args = parse_args(["nonexistent:", "text"])
        args = get_journal_name(args, multi_journal_config)
        assert args.journal_name == DEFAULT_JOURNAL_KEY
        assert args.text == ["nonexistent:", "text"]

    def test_validate_journal_name_valid(self, multi_journal_config):
        validate_journal_name("default", multi_journal_config)
        validate_journal_name("work", multi_journal_config)
        validate_journal_name("personal", multi_journal_config)

    def test_validate_journal_name_invalid(self, multi_journal_config):
        with pytest.raises(JrnlException):
            validate_journal_name("nonexistent", multi_journal_config)

    def test_search_in_specific_journal_isolated(self, multi_journal_config):
        journals = {}
        for name in ["default", "work", "personal"]:
            journal = Journal(
                name=name,
                **scope_config(multi_journal_config.copy(), name)
            )
            journals[name] = journal

        journals["default"].new_entry(
            "2023-01-01 09:00: Shared topic @important",
            date=datetime.datetime(2023, 1, 1, 9, 0),
        )
        journals["default"].new_entry(
            "2023-01-02 09:00: Only default",
            date=datetime.datetime(2023, 1, 2, 9, 0),
        )
        journals["work"].new_entry(
            "2023-01-01 09:00: Shared topic #important",
            date=datetime.datetime(2023, 1, 1, 9, 0),
        )
        journals["personal"].new_entry(
            "2023-01-01 09:00: Different topic @home",
            date=datetime.datetime(2023, 1, 1, 9, 0),
        )

        journals["default"].filter(tags=["@important"])
        assert len(journals["default"]) == 1

        journals["work"].filter(tags=["#important"])
        assert len(journals["work"]) == 1

        journals["personal"].filter(tags=["@important"])
        assert len(journals["personal"]) == 0


class TestTagCaseSensitivityAndConflicts:
    def test_tag_search_case_insensitive(self):
        journal = Journal()
        journal.new_entry(
            "2023-01-15 10:00: @Hello World and @HELLO again",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        journal.new_entry(
            "2023-01-16 10:00: @hello lowercase",
            date=datetime.datetime(2023, 1, 16, 10, 0),
        )

        journal.filter(tags=["@HELLO"])
        assert len(journal) == 2

    def test_tags_normalized_to_lowercase(self):
        journal = Journal()
        entry = Entry(journal, text="@MixedCase @lowercase @UPPERCASE")
        for tag in entry.tags:
            assert tag == tag.lower()

    def test_different_tag_symbols_no_conflict(self):
        journal = Journal(tagsymbols="@#")
        entry = Entry(journal, text="@tag #tag @another #another")
        tags = set(entry.tags)
        assert "@tag" in tags
        assert "#tag" in tags
        assert "@another" in tags
        assert "#another" in tags
        assert len(tags) == 4

    def test_same_tag_different_journals_isolated(self):
        j1 = Journal(name="journal1", tagsymbols="@")
        j2 = Journal(name="journal2", tagsymbols="@")

        j1.new_entry(
            "2023-01-01 09:00: Entry in j1 @shared",
            date=datetime.datetime(2023, 1, 1, 9, 0),
        )
        j1.new_entry(
            "2023-01-02 09:00: Another in j1 @shared @onlyj1",
            date=datetime.datetime(2023, 1, 2, 9, 0),
        )
        j2.new_entry(
            "2023-01-01 09:00: Entry in j2 @shared @onlyj2",
            date=datetime.datetime(2023, 1, 1, 9, 0),
        )

        j1.filter(tags=["@shared"])
        assert len(j1) == 2

        j2.filter(tags=["@shared"])
        assert len(j2) == 1

        j1_copy = Journal(name="journal1", tagsymbols="@")
        j1_copy.new_entry(
            "2023-01-01 09:00: Entry in j1 @shared",
            date=datetime.datetime(2023, 1, 1, 9, 0),
        )
        j1_copy.new_entry(
            "2023-01-02 09:00: Another in j1 @shared @onlyj1",
            date=datetime.datetime(2023, 1, 2, 9, 0),
        )
        j1_copy.filter(tags=["@onlyj1"])
        assert len(j1_copy) == 1

        j2_copy = Journal(name="journal2", tagsymbols="@")
        j2_copy.new_entry(
            "2023-01-01 09:00: Entry in j2 @shared @onlyj2",
            date=datetime.datetime(2023, 1, 1, 9, 0),
        )
        j2_copy.filter(tags=["@onlyj2"])
        assert len(j2_copy) == 1


class TestCombinedFilters:
    @pytest.fixture
    def complex_journal(self):
        journal = Journal(tagsymbols="@#")
        entries_data = [
            ("2023-01-15 09:00", "Work meeting @projectA @meeting", True),
            ("2023-01-16 14:00", "Personal note #family #vacation", False),
            ("2023-01-17 10:00", "Work review @projectA @review", True),
            ("2023-01-18 16:00", "Dinner with friends #friends", False),
            ("2023-01-19 11:00", "ProjectA planning @projectA #planning", True),
            ("2023-02-01 09:00", "New month start @projectB", False),
            ("2023-02-15 14:00", "ProjectB milestone @projectB @milestone", True),
        ]
        for date_str, text, starred in entries_data:
            date = datetime.datetime.strptime(date_str, "%Y-%m-%d %H:%M")
            entry = Entry(journal, date=date, text=text, starred=starred)
            journal.entries.append(entry)
        journal.sort()
        return journal

    def test_tags_and_date_range(self, complex_journal):
        complex_journal.filter(
            tags=["@projectA"],
            start_date="2023-01-16",
            end_date="2023-01-18",
        )
        assert len(complex_journal) == 1
        assert "@review" in complex_journal.entries[0].tags

    def test_tags_and_starred(self, complex_journal):
        complex_journal.filter(tags=["@projectA"], starred=True)
        assert len(complex_journal) == 3
        for entry in complex_journal.entries:
            assert entry.starred is True
            assert "@projecta" in entry.tags

    def test_tags_month_and_strict(self, complex_journal):
        complex_journal.filter(
            tags=["@projecta", "#planning"],
            month="1",
            strict=True,
        )
        assert len(complex_journal) == 1
        entry = complex_journal.entries[0]
        assert "@projecta" in entry.tags
        assert "#planning" in entry.tags
        assert entry.date.month == 1

    def test_exclude_with_date(self, complex_journal):
        complex_journal.filter(
            start_date="2023-01-01",
            end_date="2023-01-31",
            exclude=["@projectA"],
        )
        assert len(complex_journal) == 2
        for entry in complex_journal.entries:
            assert "@projecta" not in entry.tags
            assert 1 <= entry.date.day <= 31
            assert entry.date.month == 1


class TestDefaultAndSpecifiedJournalMixing:
    @pytest.fixture
    def mixed_journals_config(self, tmp_path):
        default_path = str(tmp_path / "default.txt")
        work_path = str(tmp_path / "work.txt")
        return {
            "version": "4.0",
            "journals": {
                "default": default_path,
                "work": {
                    "journal": work_path,
                    "tagsymbols": "@#",
                },
            },
            "editor": "",
            "encrypt": False,
            "default_hour": 9,
            "default_minute": 0,
            "timeformat": "%Y-%m-%d %H:%M",
            "tagsymbols": "@",
            "highlight": True,
            "linewrap": 79,
            "indent_character": "|",
            "colors": {"body": "none", "date": "none", "tags": "none", "title": "none"},
        }

    def test_default_journal_string_path(self, mixed_journals_config):
        scoped = scope_config(mixed_journals_config.copy(), "default")
        assert "journal" in scoped
        assert scoped["journal"].endswith("default.txt")

    def test_work_journal_dict_path(self, mixed_journals_config):
        scoped = scope_config(mixed_journals_config.copy(), "work")
        assert scoped["journal"].endswith("work.txt")
        assert scoped["tagsymbols"] == "@#"

    def test_default_journal_no_prefix_in_args(self, mixed_journals_config):
        args = parse_args(["entry", "text"])
        args = get_journal_name(args, mixed_journals_config)
        assert args.journal_name == "default"
        assert args.text == ["entry", "text"]

    def test_work_journal_prefix_in_args(self, mixed_journals_config):
        args = parse_args(["work:", "meeting", "notes"])
        args = get_journal_name(args, mixed_journals_config)
        assert args.journal_name == "work"
        assert args.text == ["meeting", "notes"]

    def test_scope_config_inherits_global(self, mixed_journals_config):
        default_scoped = scope_config(mixed_journals_config.copy(), "default")
        work_scoped = scope_config(mixed_journals_config.copy(), "work")

        assert default_scoped["editor"] == mixed_journals_config["editor"]
        assert work_scoped["editor"] == mixed_journals_config["editor"]

        assert default_scoped["default_hour"] == mixed_journals_config["default_hour"]
        assert work_scoped["default_hour"] == mixed_journals_config["default_hour"]


class TestJournalTagsProperty:
    def test_tags_counts_single_entry(self):
        journal = Journal()
        journal.new_entry(
            "2023-01-01 09:00: @tag1 @tag2 @tag1",
            date=datetime.datetime(2023, 1, 1, 9, 0),
        )
        tags = journal.tags
        tag_names = [t.name for t in tags]
        assert "@tag1" in tag_names
        assert "@tag2" in tag_names
        tag1 = [t for t in tags if t.name == "@tag1"][0]
        tag2 = [t for t in tags if t.name == "@tag2"][0]
        assert tag1.count == 1
        assert tag2.count == 1

    def test_tags_counts_multiple_entries(self):
        journal = Journal()
        journal.new_entry(
            "2023-01-01 09:00: @tag1 @tag2",
            date=datetime.datetime(2023, 1, 1, 9, 0),
        )
        journal.new_entry(
            "2023-01-02 09:00: @tag1 @tag3",
            date=datetime.datetime(2023, 1, 2, 9, 0),
        )
        journal.new_entry(
            "2023-01-03 09:00: @tag1 again",
            date=datetime.datetime(2023, 1, 3, 9, 0),
        )
        tags = journal.tags
        tag_counts = {t.name: t.count for t in tags}
        assert tag_counts["@tag1"] == 3
        assert tag_counts["@tag2"] == 1
        assert tag_counts["@tag3"] == 1

    def test_tags_empty_journal(self):
        journal = Journal()
        assert journal.tags == []
