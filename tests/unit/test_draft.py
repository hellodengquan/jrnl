# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import json
from xml.dom import minidom

import pytest

import jrnl
from jrnl.journals import Entry, Journal
from jrnl.plugins.json_exporter import JSONExporter
from jrnl.plugins.util import format_draft_marker, get_entry_draft_status
from jrnl.plugins.xml_exporter import XMLExporter
from jrnl.plugins.yaml_exporter import YAMLExporter


@pytest.fixture
def journal():
    j = Journal()
    j.new_entry("normal entry")
    j.new_entry("draft entry!", draft=True)
    j.new_entry("another normal")
    return j


class TestEntryDraftStatus:
    def test_entry_default_not_draft(self):
        j = Journal()
        e = Entry(j, text="hello")
        e._parse_text()
        assert e.draft is False

    def test_entry_draft_from_exclamation(self):
        j = Journal()
        e = Entry(j, text="hello!")
        e._parse_text()
        assert e.draft is True

    def test_entry_draft_constructor(self):
        j = Journal()
        e = Entry(j, text="hello", draft=True)
        assert e.draft is True

    def test_entry_str_includes_draft_marker(self):
        j = Journal()
        e = Entry(j, text="hello", draft=True)
        e._parse_text()
        s = str(e)
        assert " !" in s

    def test_entry_str_no_draft_marker_when_not_draft(self):
        j = Journal()
        e = Entry(j, text="hello")
        e._parse_text()
        s = str(e)
        assert " !" not in s

    def test_formalize_entries_removes_draft(self, journal):
        draft_entries = [e for e in journal.entries if e.draft]
        assert len(draft_entries) == 1
        journal.formalize_entries(draft_entries)
        for e in draft_entries:
            assert e.draft is False

    def test_new_entry_with_draft_flag(self):
        j = Journal()
        entry = j.new_entry("quick note", draft=True)
        assert entry.draft is True

    def test_new_entry_exclamation_mark_draft(self):
        j = Journal()
        entry = j.new_entry("!quick note")
        assert entry.draft is True

    def test_new_entry_date_prefix_exclamation(self):
        j = Journal()
        entry = j.new_entry("today!: my draft note")
        assert entry.draft is True


class TestJournalFilterDraft:
    def test_filter_draft_only(self, journal):
        journal.filter(draft=True)
        assert len(journal.entries) == 1
        assert journal.entries[0].draft is True

    def test_filter_exclude_draft(self, journal):
        journal.filter(exclude_draft=True)
        assert len(journal.entries) == 2
        assert all(e.draft is False for e in journal.entries)

    def test_filter_no_draft_args_returns_all(self, journal):
        count_before = len(journal.entries)
        journal.filter()
        assert len(journal.entries) == count_before

    def test_filter_draft_with_tag(self):
        j = Journal()
        j.new_entry("draft with @work tag", draft=True)
        j.new_entry("draft with @personal tag", draft=True)
        j.new_entry("normal with @work tag")
        j.filter(draft=True, tags=["@work"])
        assert len(j.entries) == 1
        assert j.entries[0].draft is True

    def test_filter_exclude_draft_with_date(self):
        j = Journal()
        j.new_entry("old draft", draft=True)
        j.new_entry("recent normal")
        j.filter(exclude_draft=True)
        assert all(e.draft is False for e in j.entries)


class TestDraftHelperFunctions:
    def test_get_entry_draft_status_true(self):
        j = Journal()
        e = Entry(j, text="test", draft=True)
        assert get_entry_draft_status(e) is True

    def test_get_entry_draft_status_false(self):
        j = Journal()
        e = Entry(j, text="test", draft=False)
        assert get_entry_draft_status(e) is False

    def test_format_draft_marker_true(self):
        j = Journal()
        e = Entry(j, text="test", draft=True)
        assert format_draft_marker(e) == "!"

    def test_format_draft_marker_false(self):
        j = Journal()
        e = Entry(j, text="test", draft=False)
        assert format_draft_marker(e) == ""


class TestExporterDraftOutput:
    def test_json_export_includes_draft(self):
        j = Journal()
        entry = j.new_entry("test draft", draft=True)
        result = JSONExporter.export_entry(entry)
        data = json.loads(result)
        assert data["draft"] is True

    def test_json_export_draft_false(self):
        j = Journal()
        entry = j.new_entry("test normal")
        result = JSONExporter.export_entry(entry)
        data = json.loads(result)
        assert data["draft"] is False

    def test_xml_export_includes_draft_attribute(self):
        j = Journal()
        entry = j.new_entry("test draft", draft=True)
        doc = minidom.Document()
        entry_el = XMLExporter.entry_to_xml(entry, doc)
        assert entry_el.getAttribute("draft") == "True"

    def test_xml_export_draft_false_attribute(self):
        j = Journal()
        entry = j.new_entry("test normal")
        doc = minidom.Document()
        entry_el = XMLExporter.entry_to_xml(entry, doc)
        assert entry_el.getAttribute("draft") == "False"

    def test_yaml_export_includes_draft(self):
        j = Journal()
        entry = j.new_entry("test draft", draft=True)
        result = YAMLExporter.export_entry(entry)
        assert "draft: True" in result

    def test_yaml_export_draft_false(self):
        j = Journal()
        entry = j.new_entry("test normal")
        result = YAMLExporter.export_entry(entry)
        assert "draft: False" in result


class TestArgsDraftParsing:
    def test_draft_flag(self):
        from jrnl.args import parse_args
        args = parse_args(["-draft"])
        assert args.draft is True

    def test_not_draft_flag(self):
        from jrnl.args import parse_args
        args = parse_args(["-not", "-draft"])
        assert args.exclude_draft is True
        assert args.draft is False

    def test_inbox_flag_sets_draft(self):
        from jrnl.args import parse_args
        args = parse_args(["--inbox"])
        assert args.inbox is True

    def test_write_draft_flag(self):
        from jrnl.args import parse_args
        args = parse_args(["--write-draft", "my note"])
        assert args.write_draft is True

    def test_formalize_flag(self):
        from jrnl.args import parse_args
        args = parse_args(["--formalize"])
        assert args.formalize is True

    def test_archive_alias_for_formalize(self):
        from jrnl.args import parse_args
        args = parse_args(["--archive"])
        assert args.formalize is True
