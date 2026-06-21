# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import datetime
import json
import os
from unittest import mock

import pytest

from jrnl.exception import JrnlException
from jrnl.journals.Entry import Entry
from jrnl.journals.Journal import Journal
from jrnl.plugins.fancy_exporter import check_provided_linewrap_viability
from jrnl.plugins.json_exporter import JSONExporter
from jrnl.plugins.markdown_exporter import MarkdownExporter
from jrnl.plugins.text_exporter import TextExporter
from jrnl.plugins.yaml_exporter import YAMLExporter


@pytest.fixture()
def datestr():
    yield "2020-10-20 16:59"


def build_card_header(datestr):
    top_left_corner = "┎─╮"
    content = top_left_corner + datestr
    return content


@pytest.fixture
def sample_journal():
    journal = Journal(
        name="test",
        timeformat="%Y-%m-%d %H:%M",
        tagsymbols="@",
        highlight=False,
        linewrap=False,
        indent_character="",
    )
    entry1 = Entry(
        journal,
        date=datetime.datetime(2020, 8, 29, 11, 11),
        text="Entry the first.\nLorem @ipsum dolor sit amet. @tagone @tagtwo",
    )
    entry2 = Entry(
        journal,
        date=datetime.datetime(2020, 8, 31, 14, 32),
        text="A second entry.\nSed sit amet metus. @tagtwo",
        starred=True,
    )
    journal.entries = [entry1, entry2]
    journal.sort()
    return journal


@pytest.fixture
def single_entry_journal():
    journal = Journal(
        name="test",
        timeformat="%Y-%m-%d %H:%M",
        tagsymbols="@",
        highlight=False,
        linewrap=False,
        indent_character="",
    )
    entry = Entry(
        journal,
        date=datetime.datetime(2020, 10, 20, 16, 59),
        text="Test entry title.\nThis is the body with @mytag.",
    )
    journal.entries = [entry]
    return journal


@pytest.fixture
def empty_body_journal():
    journal = Journal(
        name="test",
        timeformat="%Y-%m-%d %H:%M",
        tagsymbols="@",
        highlight=False,
        linewrap=False,
        indent_character="",
    )
    entry = Entry(
        journal,
        date=datetime.datetime(2020, 10, 20, 16, 59),
        text="Title only entry.",
    )
    journal.entries = [entry]
    return journal


@pytest.fixture
def custom_tags_journal():
    journal = Journal(
        name="test",
        timeformat="%Y-%m-%d %H:%M",
        tagsymbols="#",
        highlight=False,
        linewrap=False,
        indent_character="",
    )
    entry = Entry(
        journal,
        date=datetime.datetime(2020, 10, 20, 16, 59),
        text="Custom tags entry.\nUsing #hashtag style tags.",
    )
    journal.entries = [entry]
    return journal


class TestFancy:
    def test_too_small_linewrap(self, datestr):
        journal = "test_journal"
        content = build_card_header(datestr)

        total_linewrap = 12

        with pytest.raises(JrnlException):
            check_provided_linewrap_viability(total_linewrap, [content], journal)


class TestYaml:
    @mock.patch("builtins.open")
    def test_export_to_nonexisting_folder(self, mock_open):
        with pytest.raises(JrnlException):
            YAMLExporter.write_file("journal", "non-existing-path")
        mock_open.assert_not_called()


class TestTextExporter:
    def test_export_entry_contains_date_title_body(self, single_entry_journal):
        entry = single_entry_journal.entries[0]
        result = TextExporter.export_entry(entry)

        assert "[2020-10-20 16:59]" in result
        assert "Test entry title." in result
        assert "This is the body with @mytag." in result

    def test_export_entry_field_order(self, single_entry_journal):
        entry = single_entry_journal.entries[0]
        result = TextExporter.export_entry(entry)

        date_pos = result.find("[2020-10-20 16:59]")
        title_pos = result.find("Test entry title.")
        body_pos = result.find("This is the body with @mytag.")

        assert date_pos != -1
        assert title_pos != -1
        assert body_pos != -1
        assert date_pos < title_pos
        assert title_pos < body_pos

    def test_export_entry_starred(self, sample_journal):
        starred_entry = sample_journal.entries[-1]
        result = TextExporter.export_entry(starred_entry)

        first_line = result.split("\n")[0]
        assert first_line.rstrip().endswith("*")

    def test_export_journal_contains_all_entries(self, sample_journal):
        result = TextExporter.export_journal(sample_journal)

        assert "Entry the first." in result
        assert "A second entry." in result
        assert result.count("[2020-") == 2

    def test_export_journal_entries_ordered_by_date(self, sample_journal):
        result = TextExporter.export_journal(sample_journal)

        first_entry_pos = result.find("Entry the first.")
        second_entry_pos = result.find("A second entry.")

        assert first_entry_pos < second_entry_pos

    def test_export_entry_with_empty_body(self, empty_body_journal):
        entry = empty_body_journal.entries[0]
        result = TextExporter.export_entry(entry)

        assert "[2020-10-20 16:59]" in result
        assert "Title only entry." in result

    def test_export_with_custom_tags(self, custom_tags_journal):
        entry = custom_tags_journal.entries[0]
        result = TextExporter.export_entry(entry)

        assert "#hashtag" in result

    def test_slugify_function(self):
        assert TextExporter._slugify("Hello World") == "hello-world"
        assert TextExporter._slugify("Test@Entry#1") == "testentry1"
        assert TextExporter._slugify("  Multiple  Spaces  ") == "multiple-spaces"

    def test_make_filename(self, single_entry_journal):
        entry = single_entry_journal.entries[0]
        filename = TextExporter.make_filename(entry)

        assert filename.startswith("2020-10-20_")
        assert filename.endswith(".txt")
        assert "test-entry-title" in filename.lower()


class TestMarkdownExporter:
    def test_export_entry_single_file_heading_level(self, single_entry_journal):
        entry = single_entry_journal.entries[0]
        result = MarkdownExporter.export_entry(entry, to_multifile=False)

        assert result.startswith("### ")
        assert "2020-10-20 16:59" in result
        assert "Test entry title." in result

    def test_export_entry_multi_file_heading_level(self, single_entry_journal):
        entry = single_entry_journal.entries[0]
        result = MarkdownExporter.export_entry(entry, to_multifile=True)

        assert result.startswith("# ")

    def test_export_entry_field_order(self, single_entry_journal):
        entry = single_entry_journal.entries[0]
        result = MarkdownExporter.export_entry(entry, to_multifile=False)

        heading_pos = result.find("### 2020-10-20 16:59 Test entry title.")
        body_pos = result.find("This is the body with @mytag.")

        assert heading_pos != -1
        assert body_pos != -1
        assert heading_pos < body_pos

    def test_export_journal_year_month_structure(self, sample_journal):
        result = MarkdownExporter.export_journal(sample_journal)

        assert "# 2020" in result
        assert "## August" in result

        year_pos = result.find("# 2020")
        month_pos = result.find("## August")
        first_entry_pos = result.find("### 2020-08-29")
        second_entry_pos = result.find("### 2020-08-31")

        assert year_pos < month_pos
        assert month_pos < first_entry_pos
        assert first_entry_pos < second_entry_pos

    def test_markdown_increases_atx_headings(self):
        journal = Journal(
            name="test",
            timeformat="%Y-%m-%d %H:%M",
            tagsymbols="@",
            highlight=False,
            linewrap=False,
            indent_character="",
        )
        entry = Entry(
            journal,
            date=datetime.datetime(2020, 10, 20, 16, 59),
            text="Heading test.\n# H1 Heading\n\n## H2 Heading\n\nBody text.",
        )
        journal.entries = [entry]

        result = MarkdownExporter.export_entry(entry, to_multifile=False)

        assert "#### H1 Heading" in result
        assert "##### H2 Heading" in result

    def test_markdown_increases_setext_headings(self):
        journal = Journal(
            name="test",
            timeformat="%Y-%m-%d %H:%M",
            tagsymbols="@",
            highlight=False,
            linewrap=False,
            indent_character="",
        )
        entry = Entry(
            journal,
            date=datetime.datetime(2020, 10, 20, 16, 59),
            text="Heading test.\nH1 Title\n=\n\nH2 Title\n-\n\nBody text.",
        )
        journal.entries = [entry]

        result = MarkdownExporter.export_entry(entry, to_multifile=False)

        assert "#### H1 Title" in result
        assert "##### H2 Title" in result

    def test_export_entry_with_empty_body(self, empty_body_journal):
        entry = empty_body_journal.entries[0]
        result = MarkdownExporter.export_entry(entry, to_multifile=False)

        assert "### 2020-10-20 16:59 Title only entry." in result

    def test_export_with_custom_tags(self, custom_tags_journal):
        entry = custom_tags_journal.entries[0]
        result = MarkdownExporter.export_entry(entry, to_multifile=False)

        assert "#hashtag" in result


class TestJSONExporter:
    def test_entry_to_dict_field_order_and_keys(self, single_entry_journal):
        entry = single_entry_journal.entries[0]
        result = JSONExporter.entry_to_dict(entry)

        expected_keys = ["title", "body", "date", "time", "tags", "starred"]
        actual_keys = list(result.keys())

        for key in expected_keys:
            assert key in result

        assert actual_keys[:6] == expected_keys

    def test_entry_to_dict_values(self, single_entry_journal):
        entry = single_entry_journal.entries[0]
        result = JSONExporter.entry_to_dict(entry)

        assert result["title"] == "Test entry title."
        assert "This is the body with @mytag." in result["body"]
        assert result["date"] == "2020-10-20"
        assert result["time"] == "16:59"
        assert "@mytag" in result["tags"]
        assert result["starred"] is False

    def test_entry_to_dict_starred(self, sample_journal):
        starred_entry = sample_journal.entries[-1]
        result = JSONExporter.entry_to_dict(starred_entry)

        assert result["starred"] is True

    def test_export_entry_valid_json(self, single_entry_journal):
        entry = single_entry_journal.entries[0]
        result = JSONExporter.export_entry(entry)

        parsed = json.loads(result)
        assert isinstance(parsed, dict)
        assert "title" in parsed

    def test_export_journal_structure(self, sample_journal):
        result = JSONExporter.export_journal(sample_journal)

        parsed = json.loads(result)

        assert "tags" in parsed
        assert "entries" in parsed
        assert isinstance(parsed["tags"], dict)
        assert isinstance(parsed["entries"], list)
        assert len(parsed["entries"]) == 2

    def test_export_journal_tags_count(self, sample_journal):
        result = JSONExporter.export_journal(sample_journal)

        parsed = json.loads(result)

        assert "@tagtwo" in parsed["tags"]
        assert parsed["tags"]["@tagtwo"] == 2
        assert "@ipsum" in parsed["tags"]
        assert parsed["tags"]["@ipsum"] == 1

    def test_export_journal_entries_ordered(self, sample_journal):
        result = JSONExporter.export_journal(sample_journal)

        parsed = json.loads(result)
        entries = parsed["entries"]

        assert entries[0]["date"] == "2020-08-29"
        assert entries[1]["date"] == "2020-08-31"

    def test_entry_to_dict_with_uuid(self, single_entry_journal):
        entry = single_entry_journal.entries[0]
        entry.uuid = "test-uuid-123"

        result = JSONExporter.entry_to_dict(entry)

        assert "uuid" in result
        assert result["uuid"] == "test-uuid-123"

    def test_entry_to_dict_without_uuid(self, single_entry_journal):
        entry = single_entry_journal.entries[0]

        result = JSONExporter.entry_to_dict(entry)

        assert "uuid" not in result

    def test_entry_to_dict_with_creator_fields(self, single_entry_journal):
        entry = single_entry_journal.entries[0]
        entry.creator_device_agent = "iPhone"
        entry.creator_software_agent = "jrnl"

        result = JSONExporter.entry_to_dict(entry)

        assert "creator" in result
        assert result["creator"]["device_agent"] == "iPhone"
        assert result["creator"]["software_agent"] == "jrnl"

    def test_export_with_custom_tags(self, custom_tags_journal):
        entry = custom_tags_journal.entries[0]
        result = JSONExporter.entry_to_dict(entry)

        assert "#hashtag" in result["tags"]


class TestYAMLExporter:
    def test_export_entry_field_order_in_front_matter(self, single_entry_journal):
        entry = single_entry_journal.entries[0]
        result = YAMLExporter.export_entry(entry)

        lines = result.split("\n")
        front_matter_lines = []
        in_front_matter = False

        for line in lines:
            if line == "---":
                in_front_matter = True
                continue
            if line == "..." or line.startswith("body:"):
                break
            if in_front_matter and ":" in line:
                front_matter_lines.append(line.split(":")[0].strip())

        expected_order = ["title", "date", "starred", "tags"]
        assert front_matter_lines[:4] == expected_order

    def test_export_entry_front_matter_values(self, single_entry_journal):
        entry = single_entry_journal.entries[0]
        result = YAMLExporter.export_entry(entry)

        assert "title: Test entry title." in result
        assert "date: 2020-10-20 16:59" in result
        assert "starred: False" in result
        assert "tags:" in result

    def test_export_entry_body_indented(self, single_entry_journal):
        entry = single_entry_journal.entries[0]
        result = YAMLExporter.export_entry(entry)

        assert "body: |" in result
        assert "\tThis is the body with @mytag." in result

    def test_export_entry_starred(self, sample_journal):
        starred_entry = sample_journal.entries[-1]
        result = YAMLExporter.export_entry(starred_entry)

        assert "starred: True" in result

    def test_export_entry_tags(self, sample_journal):
        entry = sample_journal.entries[0]
        result = YAMLExporter.export_entry(entry)

        assert "tags:" in result
        assert "ipsum" in result
        assert "tagone" in result
        assert "tagtwo" in result

    def test_export_journal_raises_error(self, sample_journal):
        with pytest.raises(JrnlException):
            YAMLExporter.export_journal(sample_journal)

    def test_export_entry_non_multifile_raises_error(self, single_entry_journal):
        entry = single_entry_journal.entries[0]
        with pytest.raises(JrnlException):
            YAMLExporter.export_entry(entry, to_multifile=False)

    def test_export_entry_with_uuid(self, single_entry_journal):
        entry = single_entry_journal.entries[0]
        entry.uuid = "test-uuid-123"

        result = YAMLExporter.export_entry(entry)

        assert "uuid: test-uuid-123" in result

    def test_export_entry_with_creator_fields(self, single_entry_journal):
        entry = single_entry_journal.entries[0]
        entry.creator_device_agent = "iPhone"
        entry.creator_host_name = "test-host"
        entry.creator_software_agent = "jrnl"

        result = YAMLExporter.export_entry(entry)

        assert "creator:" in result
        assert "device agent: iPhone" in result
        assert "host name: test-host" in result
        assert "software agent: jrnl" in result

    def test_export_with_custom_tags(self, custom_tags_journal):
        entry = custom_tags_journal.entries[0]
        result = YAMLExporter.export_entry(entry)

        assert "hashtag" in result


class TestCrossJournalExport:
    def test_text_export_consistent_across_journals(self):
        journal1 = Journal(
            name="journal1",
            timeformat="%Y-%m-%d %H:%M",
            tagsymbols="@",
            highlight=False,
            linewrap=False,
            indent_character="",
        )
        journal2 = Journal(
            name="journal2",
            timeformat="%Y-%m-%d %H:%M",
            tagsymbols="@",
            highlight=False,
            linewrap=False,
            indent_character="",
        )

        entry1 = Entry(
            journal1,
            date=datetime.datetime(2020, 10, 20, 16, 59),
            text="Same entry.\nBody text @tag",
        )
        entry2 = Entry(
            journal2,
            date=datetime.datetime(2020, 10, 20, 16, 59),
            text="Same entry.\nBody text @tag",
        )

        result1 = TextExporter.export_entry(entry1)
        result2 = TextExporter.export_entry(entry2)

        assert result1 == result2

    def test_json_export_consistent_across_journals(self):
        journal1 = Journal(
            name="journal1",
            timeformat="%Y-%m-%d %H:%M",
            tagsymbols="@",
            highlight=False,
            linewrap=False,
            indent_character="",
        )
        journal2 = Journal(
            name="journal2",
            timeformat="%Y-%m-%d %H:%M",
            tagsymbols="@",
            highlight=False,
            linewrap=False,
            indent_character="",
        )

        entry1 = Entry(
            journal1,
            date=datetime.datetime(2020, 10, 20, 16, 59),
            text="Same entry.\nBody text @tag",
        )
        entry2 = Entry(
            journal2,
            date=datetime.datetime(2020, 10, 20, 16, 59),
            text="Same entry.\nBody text @tag",
        )

        dict1 = JSONExporter.entry_to_dict(entry1)
        dict2 = JSONExporter.entry_to_dict(entry2)

        assert dict1["title"] == dict2["title"]
        assert dict1["date"] == dict2["date"]
        assert dict1["tags"] == dict2["tags"]

    def test_markdown_export_consistent_across_journals(self):
        journal1 = Journal(
            name="journal1",
            timeformat="%Y-%m-%d %H:%M",
            tagsymbols="@",
            highlight=False,
            linewrap=False,
            indent_character="",
        )
        journal2 = Journal(
            name="journal2",
            timeformat="%Y-%m-%d %H:%M",
            tagsymbols="@",
            highlight=False,
            linewrap=False,
            indent_character="",
        )

        entry1 = Entry(
            journal1,
            date=datetime.datetime(2020, 10, 20, 16, 59),
            text="Same entry.\nBody text @tag",
        )
        entry2 = Entry(
            journal2,
            date=datetime.datetime(2020, 10, 20, 16, 59),
            text="Same entry.\nBody text @tag",
        )

        result1 = MarkdownExporter.export_entry(entry1, to_multifile=False)
        result2 = MarkdownExporter.export_entry(entry2, to_multifile=False)

        assert result1 == result2

    def test_yaml_export_consistent_across_journals(self):
        journal1 = Journal(
            name="journal1",
            timeformat="%Y-%m-%d %H:%M",
            tagsymbols="@",
            highlight=False,
            linewrap=False,
            indent_character="",
        )
        journal2 = Journal(
            name="journal2",
            timeformat="%Y-%m-%d %H:%M",
            tagsymbols="@",
            highlight=False,
            linewrap=False,
            indent_character="",
        )

        entry1 = Entry(
            journal1,
            date=datetime.datetime(2020, 10, 20, 16, 59),
            text="Same entry.\nBody text @tag",
        )
        entry2 = Entry(
            journal2,
            date=datetime.datetime(2020, 10, 20, 16, 59),
            text="Same entry.\nBody text @tag",
        )

        result1 = YAMLExporter.export_entry(entry1)
        result2 = YAMLExporter.export_entry(entry2)

        assert result1 == result2

    def test_different_timeformat_affects_output(self):
        journal1 = Journal(
            name="journal1",
            timeformat="%Y-%m-%d %H:%M",
            tagsymbols="@",
            highlight=False,
            linewrap=False,
            indent_character="",
        )
        journal2 = Journal(
            name="journal2",
            timeformat="%m/%d/%Y",
            tagsymbols="@",
            highlight=False,
            linewrap=False,
            indent_character="",
        )

        entry1 = Entry(
            journal1,
            date=datetime.datetime(2020, 10, 20, 16, 59),
            text="Test entry.\nBody",
        )
        entry2 = Entry(
            journal2,
            date=datetime.datetime(2020, 10, 20, 16, 59),
            text="Test entry.\nBody",
        )

        result1 = TextExporter.export_entry(entry1)
        result2 = TextExporter.export_entry(entry2)

        assert "[2020-10-20 16:59]" in result1
        assert "[10/20/2020]" in result2


class TestEntryFieldAccess:
    def test_entry_title_property(self, single_entry_journal):
        entry = single_entry_journal.entries[0]
        assert entry.title == "Test entry title."

    def test_entry_body_property(self, single_entry_journal):
        entry = single_entry_journal.entries[0]
        assert "This is the body with @mytag." in entry.body

    def test_entry_tags_property(self, single_entry_journal):
        entry = single_entry_journal.entries[0]
        assert "@mytag" in entry.tags

    def test_entry_date_property(self, single_entry_journal):
        entry = single_entry_journal.entries[0]
        assert isinstance(entry.date, datetime.datetime)
        assert entry.date.year == 2020
        assert entry.date.month == 10
        assert entry.date.day == 20

    def test_entry_starred_property(self, sample_journal):
        normal_entry = sample_journal.entries[0]
        starred_entry = sample_journal.entries[-1]

        assert normal_entry.starred is False
        assert starred_entry.starred is True

    def test_entry_tags_lowercase(self):
        journal = Journal(
            name="test",
            timeformat="%Y-%m-%d %H:%M",
            tagsymbols="@",
            highlight=False,
            linewrap=False,
            indent_character="",
        )
        entry = Entry(
            journal,
            date=datetime.datetime(2020, 10, 20, 16, 59),
            text="Test @MixedCase tags.",
        )

        assert "@mixedcase" in entry.tags

    def test_entry_multiple_tags_unique(self):
        journal = Journal(
            name="test",
            timeformat="%Y-%m-%d %H:%M",
            tagsymbols="@",
            highlight=False,
            linewrap=False,
            indent_character="",
        )
        entry = Entry(
            journal,
            date=datetime.datetime(2020, 10, 20, 16, 59),
            text="Test @tag @tag @TAG duplicate.",
        )

        assert entry.tags.count("@tag") == 1
        assert len(entry.tags) == 1
