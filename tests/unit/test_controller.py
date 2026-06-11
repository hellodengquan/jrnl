# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import datetime
import random
import string
from unittest import mock

import pytest

import jrnl
from jrnl.args import parse_args
from jrnl.config import get_default_colors
from jrnl.controller import _display_search_results
from jrnl.controller import _handle_similar_entries
from jrnl.controller import _prompt_merge_choice
from jrnl.journals import Journal


@pytest.fixture
def random_string():
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=25))


@pytest.mark.parametrize("export_format", ["pretty", "short"])
def test_display_search_results_pretty_short(export_format):
    mock_args = parse_args(["--format", export_format])

    test_journal = jrnl.journals.Journal()
    test_journal.new_entry("asdf")

    test_journal.pprint = mock.Mock()

    _display_search_results(mock_args, test_journal)

    test_journal.pprint.assert_called_once()


@pytest.mark.parametrize(
    "export_format", ["markdown", "json", "xml", "yaml", "fancy", "dates"]
)
@mock.patch("jrnl.plugins.get_exporter")
@mock.patch("builtins.print")
def test_display_search_results_builtin_plugins(
    mock_print, mock_exporter, export_format, random_string
):
    test_filename = random_string
    mock_args = parse_args(["--format", export_format, "--file", test_filename])

    test_journal = jrnl.journals.Journal()
    test_journal.new_entry("asdf")

    mock_export = mock.Mock()
    mock_exporter.return_value.export = mock_export

    _display_search_results(mock_args, test_journal)

    mock_exporter.assert_called_once_with(export_format)
    mock_export.assert_called_once_with(test_journal, test_filename)
    mock_print.assert_called_once_with(mock_export.return_value)


class TestSimilarityDetection:
    @pytest.fixture
    def journal_config(self):
        return {"colors": get_default_colors()}

    def test_compute_similarity_identical(self):
        text1 = "Hello world this is a test"
        text2 = "Hello world this is a test"
        score = Journal.compute_similarity(text1, text2)
        assert score == 1.0

    def test_compute_similarity_completely_different(self):
        text1 = "Hello world"
        text2 = "Goodbye moon"
        score = Journal.compute_similarity(text1, text2)
        assert score < 0.5

    def test_compute_similarity_partial(self):
        text1 = "I had breakfast with coffee and toast"
        text2 = "I had breakfast with coffee"
        score = Journal.compute_similarity(text1, text2)
        assert 0.5 < score < 1.0

    def test_compute_similarity_case_insensitive(self):
        text1 = "HELLO WORLD"
        text2 = "hello world"
        score = Journal.compute_similarity(text1, text2)
        assert score == 1.0

    def test_compute_similarity_punctuation_ignored(self):
        text1 = "Hello, world!"
        text2 = "Hello world"
        score = Journal.compute_similarity(text1, text2)
        assert score == 1.0

    def test_compute_similarity_empty(self):
        score = Journal.compute_similarity("", "test")
        assert score == 0.0

    def test_merge_texts_keep_unique_lines(self):
        original = "Line 1\nLine 2\nLine 3"
        new = "Line 2\nLine 3\nLine 4"
        merged = Journal.merge_texts(original, new)
        assert "Line 1" in merged
        assert "Line 2" in merged
        assert "Line 3" in merged
        assert "Line 4" in merged

    def test_merge_texts_no_duplicates(self):
        original = "Same line\nAnother line"
        new = "Same line\nAnother line"
        merged = Journal.merge_texts(original, new)
        assert merged.count("Same line") == 1
        assert merged.count("Another line") == 1

    def test_find_similar_entries_same_day(self, journal_config):
        journal = Journal(**journal_config)
        today = datetime.datetime.now()
        journal.new_entry("Ate breakfast with coffee and toast")
        journal.entries[0].date = today

        similar = journal.find_similar_entries("Ate breakfast with coffee", date=today)
        assert len(similar) == 1
        assert similar[0][1] >= Journal.SIMILARITY_THRESHOLD

    def test_find_similar_entries_different_day(self, journal_config):
        journal = Journal(**journal_config)
        yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
        today = datetime.datetime.now()
        journal.new_entry("Ate breakfast with coffee and toast")
        journal.entries[0].date = yesterday

        similar = journal.find_similar_entries("Ate breakfast with coffee", date=today)
        assert len(similar) == 0


class TestMergeChoices:
    @pytest.fixture
    def mock_args(self):
        return parse_args([])

    @pytest.fixture
    def journal_config(self):
        return {"colors": get_default_colors()}

    @pytest.fixture
    def setup_journal(self, journal_config):
        journal = Journal(**journal_config)
        today = datetime.datetime.now()
        original_text = "Ate breakfast with coffee and toast. It was delicious."
        journal.new_entry(original_text, date=today)
        original_entry_id = id(journal.entries[0])
        original_entry = journal.entries[0]
        original_entry.modified = False
        return journal, original_text, today, original_entry, original_entry_id

    def test_merge_choice_1_keep_both(self, setup_journal, mock_args):
        journal, original_text, today, original_entry, original_entry_id = setup_journal
        new_text = "Ate breakfast with coffee"

        similar = journal.find_similar_entries(new_text, date=today)
        assert len(similar) == 1

        with mock.patch(
            "jrnl.controller._prompt_merge_choice", return_value="1"
        ) as mock_prompt:
            _handle_similar_entries(journal, new_text, similar, mock_args)
            mock_prompt.assert_called_once()

        assert len(journal.entries) == 2

        found_original = [e for e in journal.entries if id(e) == original_entry_id]
        assert len(found_original) == 1
        assert found_original[0].text == original_text
        assert found_original[0].modified is False

        found_new = [e for e in journal.entries if id(e) != original_entry_id]
        assert len(found_new) == 1
        assert found_new[0].text == new_text

    def test_merge_choice_2_keep_original_only(self, setup_journal, mock_args):
        journal, original_text, today, original_entry, original_entry_id = setup_journal
        new_text = "Ate breakfast with coffee"

        similar = journal.find_similar_entries(new_text, date=today)
        assert len(similar) == 1

        with mock.patch(
            "jrnl.controller._prompt_merge_choice", return_value="2"
        ) as mock_prompt:
            _handle_similar_entries(journal, new_text, similar, mock_args)
            mock_prompt.assert_called_once()

        assert len(journal.entries) == 1
        assert id(journal.entries[0]) == original_entry_id
        assert journal.entries[0].text == original_text
        assert journal.entries[0].modified is False
        assert new_text not in [e.text for e in journal.entries]

    def test_merge_choice_3_keep_new_only(self, setup_journal, mock_args):
        journal, original_text, today, original_entry, original_entry_id = setup_journal
        new_text = "Ate breakfast with coffee"

        similar = journal.find_similar_entries(new_text, date=today)
        assert len(similar) == 1

        with mock.patch(
            "jrnl.controller._prompt_merge_choice", return_value="3"
        ) as mock_prompt:
            _handle_similar_entries(journal, new_text, similar, mock_args)
            mock_prompt.assert_called_once()

        assert len(journal.entries) == 1
        assert id(journal.entries[0]) != original_entry_id
        assert original_text not in [e.text for e in journal.entries]
        assert journal.entries[0].text == new_text
        assert journal.deleted_entry_count == 1

    def test_merge_choice_4_keep_merged(self, setup_journal, mock_args):
        journal, original_text, today, original_entry, original_entry_id = setup_journal
        new_text = "Ate breakfast with coffee and orange juice"

        similar = journal.find_similar_entries(new_text, date=today)
        assert len(similar) == 1

        expected_merged = Journal.merge_texts(original_text, new_text)

        with mock.patch(
            "jrnl.controller._prompt_merge_choice", return_value="4"
        ) as mock_prompt:
            _handle_similar_entries(journal, new_text, similar, mock_args)
            mock_prompt.assert_called_once()

        assert len(journal.entries) == 1
        assert id(journal.entries[0]) == original_entry_id
        assert journal.entries[0].modified is True
        assert journal.entries[0].text == expected_merged
        assert "toast" in journal.entries[0].text
        assert "orange juice" in journal.entries[0].text
        assert new_text not in [e.text for e in journal.entries]

    def test_prompt_merge_choice_invalid_input_returns_default(self, setup_journal, mock_args):
        journal, original_text, today, original_entry, original_entry_id = setup_journal
        new_text = "Ate breakfast with coffee"

        similar = journal.find_similar_entries(new_text, date=today)
        assert len(similar) == 1

        with mock.patch("jrnl.controller.print_msgs", return_value="invalid") as mock_print:
            with mock.patch("jrnl.controller.print_msg"):
                result = _prompt_merge_choice(journal, new_text, similar[0][0], similar[0][1])
                mock_print.assert_called()

        assert result == "2"

    def test_merge_invalid_choice_defaults_to_keep_original(self, setup_journal, mock_args):
        journal, original_text, today, original_entry, original_entry_id = setup_journal
        new_text = "Ate breakfast with coffee"

        similar = journal.find_similar_entries(new_text, date=today)
        assert len(similar) == 1

        with mock.patch(
            "jrnl.controller._prompt_merge_choice", return_value="2"
        ) as mock_prompt:
            _handle_similar_entries(journal, new_text, similar, mock_args)
            mock_prompt.assert_called_once()

        assert len(journal.entries) == 1
        assert id(journal.entries[0]) == original_entry_id
        assert journal.entries[0].text == original_text
        assert journal.entries[0].modified is False

    def test_merge_multiple_similar_entries(self, mock_args, journal_config):
        journal = Journal(**journal_config)
        today = datetime.datetime.now()

        entry1_text = "Had coffee and toast for breakfast this morning"
        entry2_text = "Did some exercise in the morning"
        new_text = "Had coffee for breakfast this morning"

        journal.new_entry(entry1_text, date=today)
        journal.new_entry(entry2_text, date=today)

        original_ids = [id(e) for e in journal.entries]
        original_texts = [e.text for e in journal.entries]

        for entry in journal.entries:
            entry.modified = False

        similar = journal.find_similar_entries(new_text, date=today)
        assert len(similar) >= 1

        with mock.patch(
            "jrnl.controller._prompt_merge_choice", return_value="1"
        ) as mock_prompt:
            _handle_similar_entries(journal, new_text, similar, mock_args)
            assert mock_prompt.call_count == len(similar)

        assert len(journal.entries) == 3

        original_entries = [e for e in journal.entries if id(e) in original_ids]
        assert len(original_entries) == 2
        for entry in original_entries:
            assert entry.text in original_texts
            assert entry.modified is False

        new_entries = [e for e in journal.entries if id(e) not in original_ids]
        assert len(new_entries) == 1
        assert new_entries[0].text == new_text

    def test_merge_choice_4_original_unchanged_if_not_in_journal(self, mock_args, journal_config):
        journal = Journal(**journal_config)
        today = datetime.datetime.now()
        new_text = "Ate breakfast with coffee"

        orphan_entry = jrnl.journals.Entry(journal, date=today, text="Ate breakfast with coffee and toast")
        similar = [(orphan_entry, 0.8)]

        original_text = orphan_entry.text
        original_entry_id = id(orphan_entry)

        with mock.patch(
            "jrnl.controller._prompt_merge_choice", return_value="4"
        ):
            _handle_similar_entries(journal, new_text, similar, mock_args)

        assert len(journal.entries) == 0
        assert original_text == orphan_entry.text
        assert id(orphan_entry) == original_entry_id

    def test_no_similar_entries_adds_new(self, mock_args, journal_config):
        journal = Journal(**journal_config)
        today = datetime.datetime.now()
        original_text = "Completely different topic about work"
        new_text = "Ate breakfast with coffee"

        journal.new_entry(original_text, date=today)
        original_entry_id = id(journal.entries[0])
        journal.entries[0].modified = False

        similar = journal.find_similar_entries(new_text, date=today)
        assert len(similar) == 0

        _handle_similar_entries(journal, new_text, similar, mock_args)

        assert len(journal.entries) == 2

        found_original = [e for e in journal.entries if id(e) == original_entry_id]
        assert len(found_original) == 1
        assert found_original[0].text == original_text
        assert found_original[0].modified is False

        found_new = [e for e in journal.entries if id(e) != original_entry_id]
        assert len(found_new) == 1
        assert found_new[0].text == new_text
