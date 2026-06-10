# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import datetime
import os
import shutil

import pytest

from jrnl.journals import Entry
from jrnl.journals import Journal
from jrnl.journals.FolderJournal import Folder


class TestFilterSingleTag:
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


class TestFilterCaseSensitivityAndConflicts:
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

    def test_different_tag_symbols_no_conflict(self):
        journal = Journal(tagsymbols="@#")
        entry = Entry(journal, text="@tag #tag @another #another")
        tags = set(entry.tags)
        assert "@tag" in tags
        assert "#tag" in tags
        assert "@another" in tags
        assert "#another" in tags
        assert len(tags) == 4

    def test_exclude_tag_case_insensitive(self):
        journal = Journal()
        journal.new_entry(
            "2023-01-15 10:00: Entry with @TagOne",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        journal.new_entry(
            "2023-01-16 10:00: Entry with @OtherTag",
            date=datetime.datetime(2023, 1, 16, 10, 0),
        )
        journal.filter(exclude=["@TAGONE"])
        assert len(journal) == 1
        assert "@othertag" in journal.entries[0].tags


class TestCombinedFilters:
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
            assert entry.date.month == 1


class TestFilterOnFolderJournal:
    def test_folder_journal_tag_search(self, folder_journal_with_entries):
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
        assert len(journal) > 0

        journal.filter(tags=["@john"])
        assert len(journal) == 1
        assert "@john" in journal.entries[0].tags

    def test_folder_journal_exclude_tag(self, folder_journal_with_entries):
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

        journal.filter(exclude=["@john"])
        for entry in journal.entries:
            assert "@john" not in entry.tags

    def test_folder_journal_tagged_only(self, folder_journal_with_entries):
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

        journal.filter(tagged=True)
        assert len(journal) > 0
        for entry in journal.entries:
            assert len(entry.tags) > 0

    def test_folder_journal_different_tag_symbols(self, folder_journal_with_entries):
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

        journal.filter(tags=["#team"])
        assert len(journal) == 1
        assert "#team" in journal.entries[0].tags

    def test_folder_journal_case_insensitive_search(self, folder_journal_with_entries):
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

        journal.filter(tags=["@JOHN"])
        assert len(journal) == 1


class TestFilterOnEncryptedJournal:
    def test_encrypted_journal_tag_search(self, tmp_path):
        from jrnl.encryption.NoEncryption import NoEncryption

        journal_path = str(tmp_path / "test.journal")
        journal = Journal(
            name="encrypted_test",
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
            "2023-01-15 10:00: Secret meeting @confidential",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        journal.new_entry(
            "2023-01-16 14:00: Public note @public",
            date=datetime.datetime(2023, 1, 16, 14, 0),
        )

        journal.encryption_method = NoEncryption(journal_path, journal.config)
        journal.write()

        journal2 = Journal(
            name="encrypted_test",
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

        journal2.filter(tags=["@confidential"])
        assert len(journal2) == 1
        assert "@confidential" in journal2.entries[0].tags

    def test_encrypted_journal_exclude_tag(self, tmp_path):
        from jrnl.encryption.NoEncryption import NoEncryption

        journal_path = str(tmp_path / "test.journal")
        journal = Journal(
            name="encrypted_test",
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
            "2023-01-15 10:00: Secret meeting @confidential",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        journal.new_entry(
            "2023-01-16 14:00: Public note @public",
            date=datetime.datetime(2023, 1, 16, 14, 0),
        )

        journal.encryption_method = NoEncryption(journal_path, journal.config)
        journal.write()

        journal2 = Journal(
            name="encrypted_test",
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

        journal2.filter(exclude=["@confidential"])
        assert len(journal2) == 1
        assert "@public" in journal2.entries[0].tags

    def test_encrypted_journal_case_insensitive(self, tmp_path):
        from jrnl.encryption.NoEncryption import NoEncryption

        journal_path = str(tmp_path / "test.journal")
        journal = Journal(
            name="encrypted_test",
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
            "2023-01-15 10:00: Tag with @MixedCase",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )

        journal.encryption_method = NoEncryption(journal_path, journal.config)
        journal.write()

        journal2 = Journal(
            name="encrypted_test",
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

        journal2.filter(tags=["@MIXEDCASE"])
        assert len(journal2) == 1
