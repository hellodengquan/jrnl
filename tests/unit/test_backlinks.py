# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import datetime
import tempfile
from argparse import Namespace

import pytest

from jrnl.controller import _backlinks_search_results
from jrnl.journals import Journal
from jrnl.journals.FolderJournal import Folder


@pytest.fixture
def basic_journal_config():
    """Return a basic journal configuration."""
    return {
        "journal": "test_journal.txt",
        "encrypt": False,
        "default_hour": 9,
        "default_minute": 0,
        "timeformat": "%Y-%m-%d %H:%M",
        "tagsymbols": "@#",
        "highlight": False,
        "linewrap": 80,
        "indent_character": "|",
        "display_references": True,
        "colors": {
            "body": "none",
            "date": "none",
            "tags": "none",
            "title": "none",
            "references": "none",
            "backlinks": "none",
        },
    }


@pytest.fixture
def test_entries_data():
    """Return test entry data for creating a journal with references."""
    return [
        {
            "date": datetime.datetime(2024, 1, 1, 10, 0),
            "text": "First entry. This is the beginning of my journal.",
        },
        {
            "date": datetime.datetime(2024, 1, 2, 14, 30),
            "text": (
                "Second entry referencing [[2024-01-01 10:00]]. "
                "Building on previous ideas."
            ),
        },
        {
            "date": datetime.datetime(2024, 1, 3, 9, 0),
            "text": (
                "Third entry referencing [[First entry]]. "
                "Also linking to [[2024-01-02]]."
            ),
        },
        {
            "date": datetime.datetime(2024, 1, 4, 16, 0),
            "text": "Fourth entry with no references.",
        },
        {
            "date": datetime.datetime(2024, 1, 5, 11, 30),
            "text": "Fifth entry referencing [[2024-01-01]] and [[Fourth entry]].",
        },
    ]


def make_backlinks_args(*identifier_parts):
    """Create an args object for --backlinks query, avoiding parse_args date parsing."""
    args = Namespace()
    args.backlinks = list(identifier_parts) if identifier_parts else None
    # Set other required attributes to None/default
    args.edit = False
    args.delete = False
    args.change_time = None
    args.export = False
    args.tags = False
    args.short = False
    return args


class TestSingleFileJournalBacklinks:
    """Test backlink functionality for single-file journals."""

    def test_references_parsing(self, basic_journal_config, test_entries_data):
        """Test that references are correctly parsed from entry text."""
        journal = Journal("test", **basic_journal_config)

        for entry_data in test_entries_data:
            entry = journal.new_entry(
                entry_data["text"], date=entry_data["date"], sort=False
            )
            entry._parse_text()

        journal.sort()
        journal.build_references_index()

        assert journal.entries[0].references == []
        assert journal.entries[1].references == ["2024-01-01 10:00"]
        assert set(journal.entries[2].references) == {"2024-01-02", "First entry"}
        assert journal.entries[3].references == []
        assert set(journal.entries[4].references) == {"2024-01-01", "Fourth entry"}

    def test_backlinks_building(self, basic_journal_config, test_entries_data):
        """Test that backlinks index is correctly built."""
        journal = Journal("test", **basic_journal_config)

        for entry_data in test_entries_data:
            entry = journal.new_entry(
                entry_data["text"], date=entry_data["date"], sort=False
            )
            entry._parse_text()

        journal.sort()
        journal.build_references_index()

        # Entry 0 (2024-01-01) should be referenced by entries 1, 2, 4
        assert len(journal.entries[0].backlinks) == 3
        backlink_dates = [e.date for e in journal.entries[0].backlinks]
        assert test_entries_data[1]["date"] in backlink_dates
        assert test_entries_data[2]["date"] in backlink_dates
        assert test_entries_data[4]["date"] in backlink_dates

        # Entry 1 (2024-01-02) should be referenced by entry 2
        assert len(journal.entries[1].backlinks) == 1
        assert journal.entries[1].backlinks[0].date == test_entries_data[2]["date"]

        # Entry 3 (Fourth entry) should be referenced by entry 4
        assert len(journal.entries[3].backlinks) == 1
        assert journal.entries[3].backlinks[0].date == test_entries_data[4]["date"]

        # Entry 4 should have no backlinks
        assert len(journal.entries[4].backlinks) == 0

    def test_backlinks_search_by_date(self, basic_journal_config, test_entries_data):
        """Test searching backlinks by exact datetime."""
        journal = Journal("test", **basic_journal_config)

        for entry_data in test_entries_data:
            entry = journal.new_entry(
                entry_data["text"], date=entry_data["date"], sort=False
            )
            entry._parse_text()

        journal.sort()
        journal.build_references_index()

        old_entries = journal.entries.copy()

        # Search backlinks for entry on 2024-01-01 10:00
        args = make_backlinks_args("2024-01-01", "10:00")
        _backlinks_search_results(
            args=args, journal=journal, old_entries=old_entries
        )

        # Should find entries 1, 2, 4 that reference entry 0
        assert len(journal.entries) == 3
        result_dates = [e.date for e in journal.entries]
        assert test_entries_data[1]["date"] in result_dates
        assert test_entries_data[2]["date"] in result_dates
        assert test_entries_data[4]["date"] in result_dates

    def test_backlinks_search_by_date_only(
        self, basic_journal_config, test_entries_data
    ):
        """Test searching backlinks by date only (without time)."""
        journal = Journal("test", **basic_journal_config)

        for entry_data in test_entries_data:
            entry = journal.new_entry(
                entry_data["text"], date=entry_data["date"], sort=False
            )
            entry._parse_text()

        journal.sort()
        journal.build_references_index()

        old_entries = journal.entries.copy()

        # Search backlinks for entries on 2024-01-02 (date only)
        args = make_backlinks_args("2024-01-02")
        _backlinks_search_results(
            args=args, journal=journal, old_entries=old_entries
        )

        # Should find entry 2 that references entry 1
        assert len(journal.entries) == 1
        assert journal.entries[0].date == test_entries_data[2]["date"]

    def test_backlinks_search_by_title_keyword(
        self, basic_journal_config, test_entries_data
    ):
        """Test searching backlinks by title keyword.

        Note: When target entry is found by title keyword, ALL entries that reference
        it are returned (whether by date or by title reference).
        """
        journal = Journal("test", **basic_journal_config)

        for entry_data in test_entries_data:
            entry = journal.new_entry(
                entry_data["text"], date=entry_data["date"], sort=False
            )
            entry._parse_text()

        journal.sort()
        journal.build_references_index()

        old_entries = journal.entries.copy()

        # Search backlinks for "First entry" by title keyword
        args = make_backlinks_args("First", "entry")
        _backlinks_search_results(
            args=args, journal=journal, old_entries=old_entries
        )

        # Should find all entries that reference the "First entry" (entry 0)
        # Entry 1 references by date [[2024-01-01 10:00]]
        # Entry 2 references by title [[First entry]]
        # Entry 4 references by date [[2024-01-01]]
        assert len(journal.entries) == 3
        result_dates = [e.date for e in journal.entries]
        assert test_entries_data[1]["date"] in result_dates
        assert test_entries_data[2]["date"] in result_dates
        assert test_entries_data[4]["date"] in result_dates

    def test_backlinks_search_not_found(self, basic_journal_config, test_entries_data):
        """Test searching backlinks for a non-existent entry."""
        journal = Journal("test", **basic_journal_config)

        for entry_data in test_entries_data:
            entry = journal.new_entry(
                entry_data["text"], date=entry_data["date"], sort=False
            )
            entry._parse_text()

        journal.sort()
        journal.build_references_index()

        old_entries = journal.entries.copy()

        # Search backlinks for non-existent entry
        args = make_backlinks_args("nonexistent", "entry")
        _backlinks_search_results(
            args=args, journal=journal, old_entries=old_entries
        )

        # Should return empty results
        assert len(journal.entries) == 0

    def test_backlinks_search_no_backlinks(
        self, basic_journal_config, test_entries_data
    ):
        """Test searching backlinks for an entry that has no backlinks."""
        journal = Journal("test", **basic_journal_config)

        for entry_data in test_entries_data:
            entry = journal.new_entry(
                entry_data["text"], date=entry_data["date"], sort=False
            )
            entry._parse_text()

        journal.sort()
        journal.build_references_index()

        old_entries = journal.entries.copy()

        # Search backlinks for fifth entry (no one references it)
        args = make_backlinks_args("2024-01-05", "11:30")
        _backlinks_search_results(
            args=args, journal=journal, old_entries=old_entries
        )

        # Should return empty results - no entries reference the fifth entry
        assert len(journal.entries) == 0

    def test_backlinks_search_for_referenced_entry_by_title(
        self, basic_journal_config, test_entries_data
    ):
        """Test searching backlinks for Fourth entry (referenced by fifth entry)."""
        journal = Journal("test", **basic_journal_config)

        for entry_data in test_entries_data:
            entry = journal.new_entry(
                entry_data["text"], date=entry_data["date"], sort=False
            )
            entry._parse_text()

        journal.sort()
        journal.build_references_index()

        old_entries = journal.entries.copy()

        # Search backlinks for "Fourth entry" by title
        args = make_backlinks_args("Fourth", "entry")
        _backlinks_search_results(
            args=args, journal=journal, old_entries=old_entries
        )

        # Should find fifth entry that references "Fourth entry"
        assert len(journal.entries) == 1
        assert journal.entries[0].date == test_entries_data[4]["date"]


class TestFolderJournalBacklinks:
    """Test backlink functionality for folder-based journals."""

    def test_folder_journal_backlinks_building(
        self, basic_journal_config, test_entries_data
    ):
        """Test that backlinks work correctly with folder journals."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = basic_journal_config.copy()
            config["journal"] = tmpdir

            journal = Folder("test_folder", **config)

            for entry_data in test_entries_data:
                entry = journal.new_entry(
                    entry_data["text"], date=entry_data["date"], sort=False
                )
                entry._parse_text()

            journal.sort()
            journal.write()

            # Reopen to ensure entries are loaded from files
            journal2 = Folder("test_folder", **config)
            journal2.open()
            journal2.build_references_index()

            # Entry 0 (2024-01-01) should be referenced by entries 1, 2, 4
            assert len(journal2.entries[0].backlinks) == 3
            backlink_dates = [e.date for e in journal2.entries[0].backlinks]
            assert test_entries_data[1]["date"] in backlink_dates
            assert test_entries_data[2]["date"] in backlink_dates
            assert test_entries_data[4]["date"] in backlink_dates

            # Entry 1 (2024-01-02) should be referenced by entry 2
            assert len(journal2.entries[1].backlinks) == 1
            assert journal2.entries[1].backlinks[0].date == test_entries_data[2]["date"]

    def test_folder_journal_backlinks_search(
        self, basic_journal_config, test_entries_data
    ):
        """Test --backlinks command works with folder journals."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = basic_journal_config.copy()
            config["journal"] = tmpdir

            journal = Folder("test_folder", **config)

            for entry_data in test_entries_data:
                entry = journal.new_entry(
                    entry_data["text"], date=entry_data["date"], sort=False
                )
                entry._parse_text()

            journal.sort()
            journal.write()

            # Reopen to ensure entries are loaded from files
            journal2 = Folder("test_folder", **config)
            journal2.open()
            journal2.build_references_index()

            old_entries = journal2.entries.copy()

            # Search backlinks for entry on 2024-01-01
            args = make_backlinks_args("2024-01-01")
            _backlinks_search_results(
                args=args, journal=journal2, old_entries=old_entries
            )

            # Should find entries that reference the Jan 1 entry
            assert len(journal2.entries) == 3
            result_dates = [e.date for e in journal2.entries]
            assert test_entries_data[1]["date"] in result_dates
            assert test_entries_data[2]["date"] in result_dates
            assert test_entries_data[4]["date"] in result_dates

    def test_folder_journal_cross_file_references(
        self, basic_journal_config, test_entries_data
    ):
        """Test that references work across files in folder journals."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = basic_journal_config.copy()
            config["journal"] = tmpdir

            # Create entries one at a time and save between each
            journal = Folder("test_folder", **config)

            # Create entry 0
            journal.new_entry(
                test_entries_data[0]["text"], date=test_entries_data[0]["date"]
            )
            journal.write()

            # Create entry 1 referencing entry 0
            journal2 = Folder("test_folder", **config)
            journal2.open()
            journal2.new_entry(
                test_entries_data[1]["text"], date=test_entries_data[1]["date"]
            )
            journal2.write()

            # Create entry 2 referencing entries 0 and 1
            journal3 = Folder("test_folder", **config)
            journal3.open()
            journal3.new_entry(
                test_entries_data[2]["text"], date=test_entries_data[2]["date"]
            )
            journal3.write()

            # Open final journal and verify references
            final_journal = Folder("test_folder", **config)
            final_journal.open()
            final_journal.build_references_index()

            # Entry 0 should have backlinks from entries 1 and 2
            assert len(final_journal.entries[0].backlinks) == 2

            # Entry 1 should have backlink from entry 2
            assert len(final_journal.entries[1].backlinks) == 1
            target_date = test_entries_data[2]["date"]
            assert final_journal.entries[1].backlinks[0].date == target_date

    def test_folder_journal_editable_str_includes_backlinks(
        self, basic_journal_config, test_entries_data
    ):
        """Test that editable_str includes reference metadata for folder journals."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = basic_journal_config.copy()
            config["journal"] = tmpdir

            journal = Folder("test_folder", **config)

            for entry_data in test_entries_data:
                entry = journal.new_entry(
                    entry_data["text"], date=entry_data["date"], sort=False
                )
                entry._parse_text()

            journal.sort()
            journal.build_references_index()

            editable = journal.editable_str()

            # Check that reference metadata is included
            assert "%% References:" in editable
            assert "%% Backlinks" in editable

            # Check that metadata lines use %% prefix
            for line in editable.splitlines():
                stripped = line.lstrip()
                if "References:" in stripped or "Backlinks" in stripped:
                    assert stripped.startswith("%%")

    def test_folder_journal_metadata_stripping(
        self, basic_journal_config, test_entries_data
    ):
        """Test that metadata lines are correctly stripped when parsing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = basic_journal_config.copy()
            config["journal"] = tmpdir

            journal = Folder("test_folder", **config)

            for entry_data in test_entries_data:
                entry = journal.new_entry(
                    entry_data["text"], date=entry_data["date"], sort=False
                )
                entry._parse_text()

            journal.sort()
            journal.build_references_index()

            editable = journal.editable_str()

            # Parse the editable string and verify metadata is stripped
            parsed_entries = journal._parse(editable)

            # Check that no entry text contains %% metadata
            for entry in parsed_entries:
                assert "%% References:" not in entry.title
                assert "%% References:" not in entry.body
                assert "%% Backlinks" not in entry.title
                assert "%% Backlinks" not in entry.body
