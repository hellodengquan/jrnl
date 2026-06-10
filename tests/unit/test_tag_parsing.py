# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import pytest

from jrnl.journals import Entry
from jrnl.journals import Journal


class TestTagRegex:
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
        result = pattern.findall(
            "@tag-with-dashes @tag_with_underscores @tag/with/slashes"
        )
        assert result == [
            "@tag-with-dashes",
            "@tag_with_underscores",
            "@tag/with/slashes",
        ]

    def test_tag_regex_plus_and_star_symbols(self):
        pattern = Entry.tag_regex("@+*")
        result = pattern.findall("@tag +plus *star")
        assert result == ["@tag", "+plus", "*star"]

    def test_tag_regex_does_not_match_midword(self):
        pattern = Entry.tag_regex("@")
        result = pattern.findall("email@domain.com")
        assert result == []


class TestEntryTagParsing:
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
        journal = Journal(tagsymbols="#@!")
        entry = Entry(journal, text="#hash @at and !bang tags")
        assert set(entry.tags) == {"#hash", "@at", "!bang"}

    def test_tag_parsing_no_tags(self):
        journal = Journal()
        entry = Entry(journal, text="Just a plain text entry with no tags")
        assert entry.tags == []

    def test_tags_normalized_to_lowercase(self):
        journal = Journal()
        entry = Entry(journal, text="@MixedCase @lowercase @UPPERCASE")
        for tag in entry.tags:
            assert tag == tag.lower()

    def test_tag_setter_bypasses_parse(self):
        journal = Journal()
        entry = Entry(journal, text="some text")
        entry.tags = ["@custom", "@tags"]
        assert entry.tags == ["@custom", "@tags"]

    def test_fulltext_includes_title_and_body(self):
        journal = Journal()
        entry = Entry(journal, text="@idea for the project\nBody text here")
        assert "@idea" in entry.fulltext
        assert "Body" in entry.fulltext


class TestJournalTagsProperty:
    def test_tags_counts_single_entry(self):
        journal = Journal()
        journal.new_entry(
            "2023-01-01 09:00: @tag1 @tag2 @tag1",
            date=__import__("datetime").datetime(2023, 1, 1, 9, 0),
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
            date=__import__("datetime").datetime(2023, 1, 1, 9, 0),
        )
        journal.new_entry(
            "2023-01-02 09:00: @tag1 @tag3",
            date=__import__("datetime").datetime(2023, 1, 2, 9, 0),
        )
        journal.new_entry(
            "2023-01-03 09:00: @tag1 again",
            date=__import__("datetime").datetime(2023, 1, 3, 9, 0),
        )
        tags = journal.tags
        tag_counts = {t.name: t.count for t in tags}
        assert tag_counts["@tag1"] == 3
        assert tag_counts["@tag2"] == 1
        assert tag_counts["@tag3"] == 1

    def test_tags_empty_journal(self):
        journal = Journal()
        assert journal.tags == []

    def test_tag_repr(self):
        from jrnl.journals.Journal import Tag

        tag = Tag("@test", count=5)
        assert repr(tag) == "<Tag '@test'>"
        assert str(tag) == "@test"
