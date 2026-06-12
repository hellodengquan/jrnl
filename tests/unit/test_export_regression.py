# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import datetime
import json
import os
from xml.dom import minidom

import pytest

from jrnl.journals.Entry import Entry
from jrnl.journals.Journal import Journal
from jrnl.plugins import get_exporter
from jrnl.plugins.dates_exporter import DatesExporter
from jrnl.plugins.fancy_exporter import FancyExporter
from jrnl.plugins.json_exporter import JSONExporter
from jrnl.plugins.markdown_exporter import MarkdownExporter
from jrnl.plugins.pretty_exporter import PrettyExporter
from jrnl.plugins.pretty_exporter import ShortExporter
from jrnl.plugins.tag_exporter import TagExporter
from jrnl.plugins.text_exporter import TextExporter
from jrnl.plugins.xml_exporter import XMLExporter
from jrnl.plugins.yaml_exporter import YAMLExporter


BASELINE_DIR = os.path.join(os.path.dirname(__file__), "export_baselines")

JOURNAL_CONFIG = {
    "journal": "journal.txt",
    "encrypt": False,
    "default_hour": 9,
    "default_minute": 0,
    "timeformat": "%Y-%m-%d %H:%M",
    "tagsymbols": "@",
    "highlight": False,
    "linewrap": 80,
    "indent_character": "|",
    "colors": {
        "body": "none",
        "date": "none",
        "tags": "none",
        "title": "none",
    },
}


@pytest.fixture()
def journal():
    j = Journal("test")
    j.config = JOURNAL_CONFIG
    j.entries = [
        Entry(
            j,
            date=datetime.datetime(2023, 5, 15, 9, 30),
            text="Hello world. This is a test entry.",
            starred=False,
        ),
        Entry(
            j,
            date=datetime.datetime(2023, 6, 20, 14, 45),
            text="Second entry with @tag1 and @tag2. More content here.",
            starred=True,
        ),
        Entry(
            j,
            date=datetime.datetime(2023, 6, 20, 18, 0),
            text="Third entry. @tag1 appears again.",
            starred=False,
        ),
    ]
    return j


def _read_baseline(name):
    path = os.path.join(BASELINE_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class TestTextExporterRegression:
    def test_export_journal_matches_baseline(self, journal):
        baseline = _read_baseline("text_journal.txt")
        assert TextExporter.export_journal(journal) == baseline

    def test_export_entry_matches_baseline(self, journal):
        baseline = _read_baseline("text_entry.txt")
        assert TextExporter.export_entry(journal.entries[1]) == baseline

    def test_get_exporter_returns_correct_class(self):
        for name in ("text", "txt"):
            assert get_exporter(name) is TextExporter

    def test_export_journal_via_registry_matches_direct(self, journal):
        direct = TextExporter.export_journal(journal)
        for name in ("text", "txt"):
            via_registry = get_exporter(name).export_journal(journal)
            assert via_registry == direct


class TestJSONExporterRegression:
    def test_export_journal_is_valid_json(self, journal):
        output = JSONExporter.export_journal(journal)
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_export_journal_structure(self, journal):
        output = JSONExporter.export_journal(journal)
        parsed = json.loads(output)
        assert "entries" in parsed
        assert "tags" in parsed
        assert len(parsed["entries"]) == 3
        assert set(parsed["tags"].keys()) == {"@tag1", "@tag2"}
        assert parsed["tags"]["@tag1"] == 2
        assert parsed["tags"]["@tag2"] == 1

    def test_export_journal_entries_content(self, journal):
        output = JSONExporter.export_journal(journal)
        parsed = json.loads(output)
        entry0 = parsed["entries"][0]
        assert entry0["title"] == "Hello world."
        assert entry0["body"] == "This is a test entry."
        assert entry0["date"] == "2023-05-15"
        assert entry0["time"] == "09:30"
        assert entry0["tags"] == []
        assert entry0["starred"] is False

        entry1 = parsed["entries"][1]
        assert entry1["title"] == "Second entry with @tag1 and @tag2."
        assert entry1["body"] == "More content here."
        assert entry1["date"] == "2023-06-20"
        assert entry1["time"] == "14:45"
        assert set(entry1["tags"]) == {"@tag1", "@tag2"}
        assert entry1["starred"] is True

        entry2 = parsed["entries"][2]
        assert entry2["title"] == "Third entry."
        assert entry2["body"] == "@tag1 appears again."
        assert entry2["date"] == "2023-06-20"
        assert entry2["time"] == "18:00"
        assert entry2["tags"] == ["@tag1"]
        assert entry2["starred"] is False

    def test_get_exporter_returns_correct_class(self):
        assert get_exporter("json") is JSONExporter

    def test_export_journal_via_registry_matches_direct(self, journal):
        direct = JSONExporter.export_journal(journal)
        via_registry = get_exporter("json").export_journal(journal)
        assert via_registry == direct


class TestMarkdownExporterRegression:
    def test_export_journal_matches_baseline(self, journal):
        baseline = _read_baseline("markdown_journal.md")
        assert MarkdownExporter.export_journal(journal) == baseline

    def test_get_exporter_returns_correct_class(self):
        for name in ("md", "markdown"):
            assert get_exporter(name) is MarkdownExporter

    def test_export_journal_via_registry_matches_direct(self, journal):
        direct = MarkdownExporter.export_journal(journal)
        for name in ("md", "markdown"):
            via_registry = get_exporter(name).export_journal(journal)
            assert via_registry == direct


class TestFancyExporterRegression:
    def test_export_journal_matches_baseline(self, journal):
        baseline = _read_baseline("fancy_journal.txt")
        assert FancyExporter.export_journal(journal) == baseline

    def test_get_exporter_returns_correct_class(self):
        for name in ("fancy", "boxed"):
            assert get_exporter(name) is FancyExporter

    def test_export_journal_via_registry_matches_direct(self, journal):
        direct = FancyExporter.export_journal(journal)
        for name in ("fancy", "boxed"):
            via_registry = get_exporter(name).export_journal(journal)
            assert via_registry == direct


class TestTagExporterRegression:
    def test_export_journal_structure(self, journal):
        output = TagExporter.export_journal(journal)
        lines = output.strip().split("\n")
        assert len(lines) == 2
        tag_counts = {}
        for line in lines:
            tag, count = line.rsplit(":", 1)
            tag_counts[tag.strip()] = int(count.strip())
        assert tag_counts == {"@tag1": 2, "@tag2": 1}

    def test_get_exporter_returns_correct_class(self):
        assert get_exporter("tags") is TagExporter

    def test_export_journal_via_registry_matches_direct(self, journal):
        direct = TagExporter.export_journal(journal)
        via_registry = get_exporter("tags").export_journal(journal)
        assert via_registry == direct


class TestDatesExporterRegression:
    def test_export_journal_matches_baseline(self, journal):
        baseline = _read_baseline("dates_journal.txt")
        assert DatesExporter.export_journal(journal) == baseline

    def test_get_exporter_returns_correct_class(self):
        assert get_exporter("dates") is DatesExporter

    def test_export_journal_via_registry_matches_direct(self, journal):
        direct = DatesExporter.export_journal(journal)
        via_registry = get_exporter("dates").export_journal(journal)
        assert via_registry == direct


class TestPrettyExporterRegression:
    def test_export_journal_matches_baseline(self, journal):
        baseline = _read_baseline("pretty_journal.txt")
        assert PrettyExporter.export_journal(journal) == baseline

    def test_export_journal_matches_journal_pprint(self, journal):
        assert PrettyExporter.export_journal(journal) == journal.pprint()

    def test_get_exporter_returns_correct_class(self):
        assert get_exporter("pretty") is PrettyExporter

    def test_export_journal_via_registry_matches_direct(self, journal):
        direct = PrettyExporter.export_journal(journal)
        via_registry = get_exporter("pretty").export_journal(journal)
        assert via_registry == direct


class TestShortExporterRegression:
    def test_export_journal_matches_baseline(self, journal):
        baseline = _read_baseline("short_journal.txt")
        assert ShortExporter.export_journal(journal) == baseline

    def test_export_journal_matches_journal_pprint_short(self, journal):
        assert ShortExporter.export_journal(journal) == journal.pprint(short=True)

    def test_get_exporter_returns_correct_class(self):
        assert get_exporter("short") is ShortExporter

    def test_export_journal_via_registry_matches_direct(self, journal):
        direct = ShortExporter.export_journal(journal)
        via_registry = get_exporter("short").export_journal(journal)
        assert via_registry == direct


class TestYAMLExporterRegression:
    def test_export_entry_structure(self, journal):
        output = YAMLExporter.export_entry(journal.entries[1])
        assert output.startswith("---\n")
        assert output.endswith("...")
        assert "title: Second entry with @tag1 and @tag2.\n" in output
        assert "date: 2023-06-20 14:45\n" in output
        assert "starred: True\n" in output
        assert "body:" in output
        assert "More content here." in output

    def test_export_entry_tags_are_present(self, journal):
        output = YAMLExporter.export_entry(journal.entries[1])
        assert "tags:" in output
        tags_line = [l for l in output.split("\n") if l.startswith("tags:")][0]
        tags_value = tags_line.split(":", 1)[1].strip()
        tags = {t.strip() for t in tags_value.split(",")}
        assert tags == {"tag1", "tag2"}

    def test_get_exporter_returns_correct_class(self):
        assert get_exporter("yaml") is YAMLExporter

    def test_export_entry_via_registry_matches_direct(self, journal):
        direct = YAMLExporter.export_entry(journal.entries[1])
        via_registry = get_exporter("yaml").export_entry(journal.entries[1])
        assert via_registry == direct


class TestXMLExporterRegression:
    def test_entry_to_xml_structure(self, journal):
        doc = minidom.Document()
        entry_el = XMLExporter.entry_to_xml(journal.entries[0], doc)
        doc.appendChild(entry_el)
        output = doc.toprettyxml()
        assert '<entry date="2023-05-15T09:30:00"' in output
        assert "Hello world. This is a test entry." in output
        assert "</entry>" in output

    def test_entry_to_xml_tag_elements(self, journal):
        doc = minidom.Document()
        entry_el = XMLExporter.entry_to_xml(journal.entries[1], doc)
        tag_els = entry_el.getElementsByTagName("tag")
        tag_names = {el.getAttribute("name") for el in tag_els}
        assert tag_names == {"@tag1", "@tag2"}

    def test_get_exporter_returns_correct_class(self):
        assert get_exporter("xml") is XMLExporter

    def test_entry_to_xml_via_registry_matches_direct(self, journal):
        doc_direct = minidom.Document()
        entry_el_direct = XMLExporter.entry_to_xml(journal.entries[0], doc_direct)
        doc_direct.appendChild(entry_el_direct)
        direct = doc_direct.toprettyxml()

        doc_registry = minidom.Document()
        exporter = get_exporter("xml")
        entry_el_registry = exporter.entry_to_xml(journal.entries[0], doc_registry)
        doc_registry.appendChild(entry_el_registry)
        via_registry = doc_registry.toprettyxml()

        assert via_registry == direct


class TestGetExporterRegistry:
    EXPECTED_FORMATS = [
        "boxed",
        "calendar",
        "dates",
        "fancy",
        "heatmap",
        "json",
        "markdown",
        "md",
        "pretty",
        "short",
        "tags",
        "text",
        "txt",
        "xml",
        "yaml",
    ]

    def test_all_expected_formats_are_registered(self):
        for fmt in self.EXPECTED_FORMATS:
            assert get_exporter(fmt) is not None, f"Format '{fmt}' not registered"

    def test_unknown_format_returns_none(self):
        assert get_exporter("nonexistent_format_xyz") is None
