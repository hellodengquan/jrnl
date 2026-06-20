# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import datetime
import tempfile
from argparse import Namespace

import pytest

from jrnl.color import colorize
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


class TestBacklinksErrorMessages:
    """Test error messages for backlinks query."""

    def test_no_entry_found_for_backlinks(
        self, basic_journal_config, test_entries_data
    ):
        """Test error message when target entry is not found."""
        journal = Journal("test", **basic_journal_config)

        for entry_data in test_entries_data:
            entry = journal.new_entry(
                entry_data["text"], date=entry_data["date"], sort=False
            )
            entry._parse_text()

        journal.sort()
        journal.build_references_index()

        old_entries = journal.entries.copy()

        # Query for non-existent entry
        args = make_backlinks_args("nonexistent", "entry")
        _backlinks_search_results(
            args=args, journal=journal, old_entries=old_entries
        )

        assert len(journal.entries) == 0
        assert hasattr(args, "_backlinks_target_found")
        assert args._backlinks_target_found is False
        assert args._backlinks_identifier == "nonexistent entry"

    def test_no_backlinks_found_for_entry(
        self, basic_journal_config, test_entries_data
    ):
        """Test message when target entry exists but has no backlinks."""
        journal = Journal("test", **basic_journal_config)

        for entry_data in test_entries_data:
            entry = journal.new_entry(
                entry_data["text"], date=entry_data["date"], sort=False
            )
            entry._parse_text()

        journal.sort()
        journal.build_references_index()

        old_entries = journal.entries.copy()

        # Query for fifth entry which has no backlinks
        args = make_backlinks_args("2024-01-05", "11:30")
        _backlinks_search_results(
            args=args, journal=journal, old_entries=old_entries
        )

        assert len(journal.entries) == 0
        assert hasattr(args, "_backlinks_target_found")
        assert args._backlinks_target_found is True
        assert args._backlinks_identifier == "2024-01-05 11:30"


class TestEditorBacklinksDisplay:
    """Test backlinks display in editor."""

    def test_single_entry_with_backlinks_shows_prominent_header(
        self, basic_journal_config, test_entries_data
    ):
        """Test that editing a single entry with backlinks shows prominent header."""
        journal = Journal("test", **basic_journal_config)

        for entry_data in test_entries_data:
            entry = journal.new_entry(
                entry_data["text"], date=entry_data["date"], sort=False
            )
            entry._parse_text()

        journal.sort()
        journal.build_references_index()

        # Entry 0 has backlinks
        entry_with_backlinks = journal.entries[0]
        assert len(entry_with_backlinks.backlinks) > 0

        # Generate editable string with prominent backlinks
        editable = journal.editable_str_with_backlinks(entry_with_backlinks)

        # Check for prominent header
        assert "%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%" in editable
        assert "NOTE: This entry is referenced by other entries" in editable

        # Check for numbered backlink list with reference formats
        assert "[1]" in editable
        assert "←" in editable  # Same arrow style as pprint output
        assert "Reference: [[" in editable
        assert "Quick ref: [[" in editable

    def test_single_entry_without_backlinks_no_prominent_header(
        self, basic_journal_config, test_entries_data
    ):
        """Test that editing a single entry without backlinks doesn't show header."""
        journal = Journal("test", **basic_journal_config)

        for entry_data in test_entries_data:
            entry = journal.new_entry(
                entry_data["text"], date=entry_data["date"], sort=False
            )
            entry._parse_text()

        journal.sort()
        journal.build_references_index()

        # Entry 3 (Fourth entry) is referenced but let's use entry 4 (Fifth entry)
        # which has no backlinks
        entry_without_backlinks = journal.entries[4]
        assert len(entry_without_backlinks.backlinks) == 0

        # Generate editable string
        editable = journal.editable_str_with_backlinks(entry_without_backlinks)

        # Should not have prominent header
        assert "NOTE: This entry is referenced by other entries" not in editable

    def test_editable_str_with_backlinks_preserves_entry_content(
        self, basic_journal_config, test_entries_data
    ):
        """Test editable_str_with_backlinks preserves original entry content."""
        journal = Journal("test", **basic_journal_config)

        for entry_data in test_entries_data:
            entry = journal.new_entry(
                entry_data["text"], date=entry_data["date"], sort=False
            )
            entry._parse_text()

        journal.sort()
        journal.build_references_index()

        entry_with_backlinks = journal.entries[0]
        editable = journal.editable_str_with_backlinks(entry_with_backlinks)

        # Should contain the original entry content
        assert str(entry_with_backlinks).rstrip() in editable

    def test_editable_str_with_backlinks_meta_stripped_on_parse(
        self, basic_journal_config, test_entries_data
    ):
        """Test that prominent header metadata is properly stripped when parsing."""
        journal = Journal("test", **basic_journal_config)

        for entry_data in test_entries_data:
            entry = journal.new_entry(
                entry_data["text"], date=entry_data["date"], sort=False
            )
            entry._parse_text()

        journal.sort()
        journal.build_references_index()

        entry_with_backlinks = journal.entries[0]
        editable = journal.editable_str_with_backlinks(entry_with_backlinks)

        # Parse the editable string
        parsed_entries = journal._parse(editable)

        # Should have exactly one entry
        assert len(parsed_entries) == 1

        # Entry content should not contain metadata
        assert "NOTE: This entry is referenced" not in parsed_entries[0].title
        assert "NOTE: This entry is referenced" not in parsed_entries[0].body

    def test_editor_format_aligns_with_pprint_style(
        self, basic_journal_config, test_entries_data
    ):
        """Test that editor metadata uses same formatting structure as pprint output.

        Both should use consistent arrow format (← for backlinks, → for references)
        and same date+title ordering to keep the visual style aligned between
        `jrnl --view` and the editor interface.
        """
        journal = Journal("test", **basic_journal_config)

        for entry_data in test_entries_data:
            entry = journal.new_entry(
                entry_data["text"], date=entry_data["date"], sort=False
            )
            entry._parse_text()

        journal.sort()
        journal.build_references_index()

        entry_with_backlinks = journal.entries[0]

        # Get plain text backlinks from Entry (same style as pprint plain=True)
        plain_backlinks = entry_with_backlinks._format_backlinks(plain=True)

        # Get editor metadata backlinks
        editor_meta = journal._format_backlinks_meta(entry_with_backlinks)

        # Both should contain the same entries with ← arrow prefix
        for line in plain_backlinks.split("\n"):
            line = line.strip()
            if line.startswith("←"):
                # The core content after the arrow should appear in the editor metadata
                core_content = line
                assert core_content in editor_meta, (
                    f"Expected '{core_content}' in editor meta for style alignment"
                )

        # Both should use the same arrow symbols
        assert "←" in plain_backlinks
        assert "←" in editor_meta

        # Editor meta should be prefixed with %% as metadata marker
        for line in editor_meta.split("\n"):
            if line.strip():
                assert line.lstrip().startswith("%%")


class TestNoColorSupport:
    """Test NO_COLOR environment variable support for backlinks."""

    def test_colorize_respects_no_color(self, monkeypatch):
        """Test that colorize returns plain text when NO_COLOR is set."""
        test_text = "Hello, World!"
        esc = "\x1b"

        # Without NO_COLOR, should add color codes
        monkeypatch.delenv("NO_COLOR", raising=False)
        result = colorize(test_text, "blue")
        assert esc in result

        # With NO_COLOR=1, should return plain text
        monkeypatch.setenv("NO_COLOR", "1")
        result = colorize(test_text, "blue")
        assert esc not in result
        assert result == test_text

        # With NO_COLOR=true, should return plain text
        monkeypatch.setenv("NO_COLOR", "true")
        result = colorize(test_text, "red", bold=True)
        assert esc not in result
        assert result == test_text

        # With empty NO_COLOR, should still use color (per no-color.org spec)
        monkeypatch.setenv("NO_COLOR", "")
        result = colorize(test_text, "green")
        assert esc in result

    def test_entry_pprint_respects_no_color(
        self, basic_journal_config, test_entries_data, monkeypatch
    ):
        """Test that entry pprint respects NO_COLOR for backlinks."""
        journal = Journal("test", **basic_journal_config)
        # Enable colors for this test
        journal.config["colors"] = {
            "body": "none",
            "date": "black",
            "tags": "yellow",
            "title": "cyan",
            "references": "blue",
            "backlinks": "magenta",
        }

        for entry_data in test_entries_data:
            entry = journal.new_entry(
                entry_data["text"], date=entry_data["date"], sort=False
            )
            entry._parse_text()

        journal.sort()
        journal.build_references_index()

        entry_with_backlinks = journal.entries[0]
        esc = "\x1b"

        # Without NO_COLOR
        monkeypatch.delenv("NO_COLOR", raising=False)
        output = entry_with_backlinks.pprint()
        # Should contain some color codes for date
        assert esc in output

        # With NO_COLOR
        monkeypatch.setenv("NO_COLOR", "1")
        output = entry_with_backlinks.pprint()
        # Should not contain ANSI escape codes
        assert esc not in output
        # But should still contain the backlinks text
        assert "Backlinks:" in output

    def test_highlight_references_respects_no_color(
        self, basic_journal_config, test_entries_data, monkeypatch
    ):
        """Test that reference highlighting respects NO_COLOR."""
        from jrnl.color import highlight_references

        journal = Journal("test", **basic_journal_config)
        journal.config["highlight"] = True
        journal.config["colors"]["references"] = "blue"

        entry = journal.new_entry(
            "See [[First entry]] for details.", date=datetime.datetime(2024, 1, 10)
        )
        entry._parse_text()

        test_text = "Reference to [[First entry]] here."
        esc = "\x1b"

        # Without NO_COLOR - with a valid color it should highlight
        monkeypatch.delenv("NO_COLOR", raising=False)
        result = highlight_references(entry, test_text, "none")
        # Should contain color codes because references color is set to blue
        assert esc in result

        # With NO_COLOR - should not add any colors
        monkeypatch.setenv("NO_COLOR", "1")
        result = highlight_references(entry, test_text, "none")
        assert esc not in result
        assert "[[First entry]]" in result

    def test_highlight_tags_respects_no_color(
        self, basic_journal_config, monkeypatch
    ):
        """Test that tag background highlighting respects NO_COLOR."""
        from jrnl.color import highlight_tags_with_background_color

        journal = Journal("test", **basic_journal_config)
        journal.config["highlight"] = True
        journal.config["colors"]["tags"] = "yellow"
        journal.config["colors"]["title"] = "cyan"

        entry = journal.new_entry(
            "Hello @world this is a #test.", date=datetime.datetime(2024, 1, 10)
        )
        entry._parse_text()

        test_text = "Hello @world this is a #test."
        esc = "\x1b"

        # Without NO_COLOR - should add colors
        monkeypatch.delenv("NO_COLOR", raising=False)
        result = highlight_tags_with_background_color(entry, test_text, "none")
        assert esc in result, f"Expected color codes in: {repr(result)}"

        # With NO_COLOR - should return plain text without colors
        monkeypatch.setenv("NO_COLOR", "1")
        result = highlight_tags_with_background_color(entry, test_text, "none")
        assert esc not in result
        assert "@world" in result
        assert "#test" in result

    def test_set_no_color_cli_flag(self, monkeypatch):
        """Test that set_no_color() CLI flag works like NO_COLOR env var."""
        from jrnl.color import _should_use_color
        from jrnl.color import set_no_color

        # Reset the flag first (in case other tests set it)
        set_no_color(False)

        # Without flag set, should use color
        monkeypatch.delenv("NO_COLOR", raising=False)
        assert _should_use_color() is True

        # Set flag to True, should disable color (even without env var)
        set_no_color(True)
        assert _should_use_color() is False

        # Reset flag
        set_no_color(False)
        assert _should_use_color() is True

    def test_no_color_cli_arg_is_recognized(self):
        """Test that --no-color argument is parsed correctly."""
        from jrnl.args import parse_args

        # Without --no-color (empty args)
        args = parse_args([])
        assert hasattr(args, "no_color")
        assert args.no_color is False

        # With --no-color
        args = parse_args(["--no-color"])
        assert args.no_color is True

        # --no-color combined with other flags
        args = parse_args(["--no-color", "-n", "5"])
        assert args.no_color is True


class TestBacklinksExitCodes:
    """Test exit codes for backlinks CLI queries."""

    def test_status_code_success(self, basic_journal_config, test_entries_data):
        """Test status code 0 when backlinks are found."""
        from jrnl.controller import _determine_status_code

        journal = Journal("test", **basic_journal_config)

        for entry_data in test_entries_data:
            entry = journal.new_entry(
                entry_data["text"], date=entry_data["date"], sort=False
            )
            entry._parse_text()

        journal.sort()
        journal.build_references_index()

        old_entries = journal.entries.copy()
        args = make_backlinks_args("2024-01-01")
        _backlinks_search_results(
            args=args, journal=journal, old_entries=old_entries
        )

        # Found backlinks - should return 0
        assert len(journal.entries) > 0
        assert _determine_status_code(args, journal) == 0

    def test_status_code_invalid_input(
        self, basic_journal_config, test_entries_data
    ):
        """Test status code 1 when backlinks identifier is invalid."""
        from jrnl.controller import _determine_status_code

        journal = Journal("test", **basic_journal_config)

        for entry_data in test_entries_data:
            entry = journal.new_entry(
                entry_data["text"], date=entry_data["date"], sort=False
            )
            entry._parse_text()

        journal.sort()
        journal.build_references_index()

        old_entries = journal.entries.copy()
        # Empty identifier - using a list with empty strings
        args = make_backlinks_args("")
        _backlinks_search_results(
            args=args, journal=journal, old_entries=old_entries
        )

        # Invalid input - should return 1
        assert getattr(args, "_backlinks_status", -1) == 1
        assert _determine_status_code(args, journal) == 1

    def test_status_code_target_not_found(
        self, basic_journal_config, test_entries_data
    ):
        """Test status code 2 when target entry is not found."""
        from jrnl.controller import _determine_status_code

        journal = Journal("test", **basic_journal_config)

        for entry_data in test_entries_data:
            entry = journal.new_entry(
                entry_data["text"], date=entry_data["date"], sort=False
            )
            entry._parse_text()

        journal.sort()
        journal.build_references_index()

        old_entries = journal.entries.copy()
        args = make_backlinks_args("nonexistent", "entry")
        _backlinks_search_results(
            args=args, journal=journal, old_entries=old_entries
        )

        # Target not found - should return 2
        assert getattr(args, "_backlinks_target_found", False) is False
        assert getattr(args, "_backlinks_status", -1) == 2
        assert _determine_status_code(args, journal) == 2

    def test_status_code_no_backlinks(self, basic_journal_config, test_entries_data):
        """Test status code 3 when target exists but has no backlinks."""
        from jrnl.controller import _determine_status_code

        journal = Journal("test", **basic_journal_config)

        for entry_data in test_entries_data:
            entry = journal.new_entry(
                entry_data["text"], date=entry_data["date"], sort=False
            )
            entry._parse_text()

        journal.sort()
        journal.build_references_index()

        old_entries = journal.entries.copy()
        # Fifth entry exists but has no backlinks
        args = make_backlinks_args("2024-01-05", "11:30")
        _backlinks_search_results(
            args=args, journal=journal, old_entries=old_entries
        )

        # Target found but no backlinks - should return 3
        assert getattr(args, "_backlinks_target_found", False) is True
        assert len(journal.entries) == 0
        assert getattr(args, "_backlinks_status", -1) == 3
        assert _determine_status_code(args, journal) == 3

    def test_status_code_normal_operation(self, basic_journal_config):
        """Test status code 0 for normal operations (non-backlinks)."""
        from jrnl.controller import _determine_status_code

        journal = Journal("test", **basic_journal_config)
        args = make_backlinks_args()
        args.backlinks = None  # Not a backlinks query

        # Normal operation - should return 0
        assert _determine_status_code(args, journal) == 0
