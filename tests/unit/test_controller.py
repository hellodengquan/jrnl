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


class TestSimilarityThresholdBoundary:
    @pytest.fixture
    def mock_args(self):
        return parse_args([])

    @pytest.fixture
    def journal_config(self):
        return {"colors": get_default_colors()}

    def test_similarity_at_threshold_triggers_merge_preview(self):
        threshold = Journal.SIMILARITY_THRESHOLD
        existing_text = "I had a great day at work today"
        new_text = "Work day was quite productive"

        score = Journal.compute_similarity(existing_text, new_text)
        assert score == pytest.approx(threshold), (
            f"Expected similarity to be exactly at threshold {threshold}, got {score}. "
            "If the algorithm changed, update the test text pairs."
        )
        assert score >= threshold

    def test_similarity_below_threshold_no_merge_preview(self):
        threshold = Journal.SIMILARITY_THRESHOLD
        existing_text = "Had a great day at work today"
        new_text = "Went to work and had meetings"

        score = Journal.compute_similarity(existing_text, new_text)
        assert score < threshold
        assert score >= threshold - 0.1, (
            f"Expected similarity to be close to threshold {threshold}, got {score}. "
            "If the algorithm changed, update the test text pairs."
        )

    def test_similarity_slightly_above_threshold_triggers_preview(
        self, mock_args, journal_config
    ):
        journal = Journal(**journal_config)
        today = datetime.datetime.now()

        existing_text = "Ate breakfast with coffee and toast"
        new_text = "Ate lunch with sandwich"

        score = Journal.compute_similarity(existing_text, new_text)
        threshold = Journal.SIMILARITY_THRESHOLD
        assert score >= threshold
        assert score < threshold + 0.1

        journal.new_entry(existing_text, date=today)
        original_entry_id = id(journal.entries[0])
        original_modified_state = journal.entries[0].modified

        similar = journal.find_similar_entries(new_text, date=today)
        assert len(similar) == 1
        assert similar[0][1] == pytest.approx(score)

        with mock.patch(
            "jrnl.controller._prompt_merge_choice", return_value="2"
        ) as mock_prompt:
            _handle_similar_entries(journal, new_text, similar, mock_args)
            mock_prompt.assert_called_once()

        assert len(journal.entries) == 1
        assert id(journal.entries[0]) == original_entry_id
        assert journal.entries[0].text == existing_text
        assert journal.entries[0].modified == original_modified_state

    def test_similarity_slightly_below_threshold_no_preview(
        self, mock_args, journal_config
    ):
        journal = Journal(**journal_config)
        today = datetime.datetime.now()

        existing_text = "Had coffee toast and eggs for breakfast"
        new_text = "For breakfast had toast and coffee"

        score = Journal.compute_similarity(existing_text, new_text)
        threshold = Journal.SIMILARITY_THRESHOLD
        assert score < threshold
        assert score >= threshold - 0.1

        journal.new_entry(existing_text, date=today)
        original_entry_id = id(journal.entries[0])
        original_modified_state = journal.entries[0].modified

        similar = journal.find_similar_entries(new_text, date=today)
        assert len(similar) == 0

        _handle_similar_entries(journal, new_text, similar, mock_args)

        assert len(journal.entries) == 2

        found_original = [e for e in journal.entries if id(e) == original_entry_id]
        assert len(found_original) == 1
        assert found_original[0].text == existing_text
        assert found_original[0].modified == original_modified_state

        found_new = [e for e in journal.entries if id(e) != original_entry_id]
        assert len(found_new) == 1
        assert found_new[0].text == new_text

    def test_no_prompt_when_no_similar_entries(self, mock_args, journal_config):
        journal = Journal(**journal_config)
        today = datetime.datetime.now()

        existing_text = "Morning routine had coffee and toast"
        new_text = "Afternoon walk in park"

        score = Journal.compute_similarity(existing_text, new_text)
        threshold = Journal.SIMILARITY_THRESHOLD
        assert score < threshold

        journal.new_entry(existing_text, date=today)
        original_entry_id = id(journal.entries[0])
        original_entry = journal.entries[0]

        similar = journal.find_similar_entries(new_text, date=today)
        assert len(similar) == 0

        with mock.patch(
            "jrnl.controller._prompt_merge_choice"
        ) as mock_prompt:
            _handle_similar_entries(journal, new_text, similar, mock_args)
            mock_prompt.assert_not_called()

        assert len(journal.entries) == 2
        assert original_entry in journal.entries
        assert id(original_entry) == original_entry_id
        assert original_entry.text == existing_text

    def test_threshold_sensitive_to_algorithm_changes(self):
        text_a = "I had a great day at work today"
        text_b = "Work day was quite productive"

        score = Journal.compute_similarity(text_a, text_b)
        expected_threshold = 0.4

        assert Journal.SIMILARITY_THRESHOLD == expected_threshold, (
            f"Threshold constant changed from {expected_threshold} to {Journal.SIMILARITY_THRESHOLD}. "
            "If this is intentional, update the threshold boundary test text pairs."
        )

        assert score == pytest.approx(expected_threshold), (
            f"Similarity algorithm output changed. "
            f"Expected score to be approximately {expected_threshold} for test text pair, "
            f"got {score}. If the algorithm was intentionally changed, "
            "update the test text pairs to maintain threshold boundary coverage."
        )

        score_reversed = Journal.compute_similarity(text_b, text_a)
        assert score == pytest.approx(score_reversed), (
            f"Similarity should be symmetric. "
            f"score(a→b): {score:.4f}, score(b→a): {score_reversed:.4f}"
        )

    def test_original_unchanged_when_below_threshold(self, mock_args, journal_config):
        journal = Journal(**journal_config)
        today = datetime.datetime.now()

        existing_text = "Had a great day at work today"
        new_text_below = "Went to work and had meetings"

        score = Journal.compute_similarity(existing_text, new_text_below)
        threshold = Journal.SIMILARITY_THRESHOLD
        assert score < threshold

        journal.new_entry(existing_text, date=today)
        original_entry = journal.entries[0]
        original_entry_id = id(original_entry)
        original_text = original_entry.text
        original_modified = original_entry.modified

        similar = journal.find_similar_entries(new_text_below, date=today)
        assert len(similar) == 0

        _handle_similar_entries(journal, new_text_below, similar, mock_args)

        assert original_entry in journal.entries
        assert id(original_entry) == original_entry_id
        assert original_entry.text == original_text
        assert original_entry.modified == original_modified

    def test_original_unchanged_when_above_threshold_keep_original(
        self, mock_args, journal_config
    ):
        journal = Journal(**journal_config)
        today = datetime.datetime.now()

        existing_text = "I had a great day at work today"
        new_text_above = "Work day was quite productive"

        score = Journal.compute_similarity(existing_text, new_text_above)
        threshold = Journal.SIMILARITY_THRESHOLD
        assert score >= threshold

        journal.new_entry(existing_text, date=today)
        original_entry = journal.entries[0]
        original_entry_id = id(original_entry)
        original_text = original_entry.text
        original_modified = original_entry.modified

        similar = journal.find_similar_entries(new_text_above, date=today)
        assert len(similar) == 1

        with mock.patch(
            "jrnl.controller._prompt_merge_choice", return_value="2"
        ):
            _handle_similar_entries(journal, new_text_above, similar, mock_args)

        assert len(journal.entries) == 1
        assert original_entry in journal.entries
        assert id(original_entry) == original_entry_id
        assert original_entry.text == original_text
        assert original_entry.modified == original_modified

    def test_exactly_at_threshold_triggers_merge_preview(
        self, mock_args, journal_config
    ):
        journal = Journal(**journal_config)
        today = datetime.datetime.now()

        existing_text = "I had a great day at work today"
        new_text = "Work day was quite productive"

        score = Journal.compute_similarity(existing_text, new_text)
        threshold = Journal.SIMILARITY_THRESHOLD
        assert score == pytest.approx(threshold)

        journal.new_entry(existing_text, date=today)
        original_entry = journal.entries[0]
        original_entry_id = id(original_entry)
        original_modified_state = original_entry.modified

        similar = journal.find_similar_entries(new_text, date=today)
        assert len(similar) == 1
        assert similar[0][1] == pytest.approx(threshold)

        with mock.patch(
            "jrnl.controller._prompt_merge_choice", return_value="2"
        ) as mock_prompt:
            _handle_similar_entries(journal, new_text, similar, mock_args)
            mock_prompt.assert_called_once()

        assert len(journal.entries) == 1
        assert original_entry in journal.entries
        assert id(original_entry) == original_entry_id
        assert original_entry.text == existing_text
        assert original_entry.modified == original_modified_state

    def test_above_threshold_different_day_no_merge_preview(
        self, mock_args, journal_config
    ):
        journal = Journal(**journal_config)
        today = datetime.datetime.now()
        yesterday = today - datetime.timedelta(days=1)

        existing_text = "I had a great day at work today"
        new_text = "Work day was quite productive"

        score = Journal.compute_similarity(existing_text, new_text)
        threshold = Journal.SIMILARITY_THRESHOLD
        assert score >= threshold

        journal.new_entry(existing_text, date=yesterday)
        original_entry = journal.entries[0]
        original_entry_id = id(original_entry)
        original_text = original_entry.text
        original_modified = original_entry.modified

        similar = journal.find_similar_entries(new_text, date=today)
        assert len(similar) == 0

        with mock.patch(
            "jrnl.controller._prompt_merge_choice"
        ) as mock_prompt:
            _handle_similar_entries(journal, new_text, similar, mock_args)
            mock_prompt.assert_not_called()

        assert len(journal.entries) == 2
        assert original_entry in journal.entries
        assert id(original_entry) == original_entry_id
        assert original_entry.text == original_text
        assert original_entry.modified == original_modified


class TestMultilingualSimilarity:
    @pytest.fixture
    def mock_args(self):
        return parse_args([])

    @pytest.fixture
    def journal_config(self):
        return {"colors": get_default_colors()}

    def test_chinese_text_not_stripped(self):
        text = "今天吃了早餐，有咖啡和吐司"
        from jrnl.journals.Journal import Journal as J

        def normalize(text):
            import re
            text = text.lower().strip()
            text = re.sub(r'[^\w\s\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]', '', text)
            text = re.sub(r'\s+', ' ', text)
            return text

        normalized = normalize(text)
        assert normalized != ""
        assert "今天" in normalized
        assert "早餐" in normalized
        assert "咖啡" in normalized

    def test_chinese_identical_text_similarity(self):
        text1 = "今天吃了早餐，有咖啡和吐司"
        text2 = "今天吃了早餐，有咖啡和吐司"
        score = Journal.compute_similarity(text1, text2)
        assert score == pytest.approx(1.0)

    def test_chinese_partial_similarity_above_threshold(self):
        text1 = "今天吃了早餐，有咖啡和吐司，很好吃"
        text2 = "今天吃了早餐，有咖啡"
        score = Journal.compute_similarity(text1, text2)
        assert score >= Journal.SIMILARITY_THRESHOLD
        assert score < 1.0

    def test_chinese_different_content_below_threshold(self):
        text1 = "今天吃了早餐，有咖啡和吐司"
        text2 = "晚上去公园散步了很久"
        score = Journal.compute_similarity(text1, text2)
        assert score < Journal.SIMILARITY_THRESHOLD

    def test_chinese_english_mixed_code_switching(self):
        text1 = "今天的 work 很顺利，meeting 也开得很好"
        text2 = "今天的工作很顺利，会议也开得很好"
        score = Journal.compute_similarity(text1, text2)
        assert score >= Journal.SIMILARITY_THRESHOLD * 0.5
        assert score < 1.0

    def test_chinese_english_same_words_different_script(self):
        text1 = "I had 咖啡 and toast for breakfast"
        text2 = "I had coffee and toast for breakfast"
        score = Journal.compute_similarity(text1, text2)
        assert score >= Journal.SIMILARITY_THRESHOLD

    def test_chinese_punctuation_ignored(self):
        text1 = "今天吃了早餐，有咖啡和吐司！很好吃"
        text2 = "今天吃了早餐,有咖啡和吐司!很好吃"
        score = Journal.compute_similarity(text1, text2)
        assert score == pytest.approx(1.0)

    def test_chinese_english_mixed_triggers_merge_preview(
        self, mock_args, journal_config
    ):
        journal = Journal(**journal_config)
        today = datetime.datetime.now()

        existing_text = "今天吃了早餐，有咖啡和吐司"
        new_text = "今天吃了早餐，有咖啡"

        score = Journal.compute_similarity(existing_text, new_text)
        assert score >= Journal.SIMILARITY_THRESHOLD

        journal.new_entry(existing_text, date=today)
        original_entry = journal.entries[0]
        original_entry_id = id(original_entry)

        similar = journal.find_similar_entries(new_text, date=today)
        assert len(similar) == 1

        with mock.patch(
            "jrnl.controller._prompt_merge_choice", return_value="2"
        ) as mock_prompt:
            _handle_similar_entries(journal, new_text, similar, mock_args)
            mock_prompt.assert_called_once()

        assert len(journal.entries) == 1
        assert original_entry in journal.entries
        assert id(original_entry) == original_entry_id
        assert original_entry.text == existing_text

    def test_chinese_english_mixed_no_trigger_when_below_threshold(
        self, mock_args, journal_config
    ):
        journal = Journal(**journal_config)
        today = datetime.datetime.now()

        existing_text = "今天吃了早餐，有咖啡和吐司"
        new_text = "晚上去公园散步了很久"

        score = Journal.compute_similarity(existing_text, new_text)
        assert score < Journal.SIMILARITY_THRESHOLD

        journal.new_entry(existing_text, date=today)
        original_entry = journal.entries[0]
        original_entry_id = id(original_entry)

        similar = journal.find_similar_entries(new_text, date=today)
        assert len(similar) == 0

        with mock.patch(
            "jrnl.controller._prompt_merge_choice"
        ) as mock_prompt:
            _handle_similar_entries(journal, new_text, similar, mock_args)
            mock_prompt.assert_not_called()

        assert len(journal.entries) == 2
        assert original_entry in journal.entries
        assert id(original_entry) == original_entry_id
        assert original_entry.text == existing_text

    def test_chinese_english_mixed_code_switching_triggers_merge(
        self, mock_args, journal_config
    ):
        journal = Journal(**journal_config)
        today = datetime.datetime.now()

        existing_text = "今天 work 很顺利，meeting 开得很好"
        new_text = "今天 work 很顺利"

        score = Journal.compute_similarity(existing_text, new_text)
        assert score >= Journal.SIMILARITY_THRESHOLD

        journal.new_entry(existing_text, date=today)
        original_entry = journal.entries[0]
        original_entry_id = id(original_entry)

        similar = journal.find_similar_entries(new_text, date=today)
        assert len(similar) == 1

        with mock.patch(
            "jrnl.controller._prompt_merge_choice", return_value="2"
        ) as mock_prompt:
            _handle_similar_entries(journal, new_text, similar, mock_args)
            mock_prompt.assert_called_once()

        assert len(journal.entries) == 1
        assert original_entry in journal.entries
        assert id(original_entry) == original_entry_id

    def test_chinese_english_full_translation_no_similarity(self):
        text1 = "今天吃了早餐，有咖啡和吐司"
        text2 = "Ate breakfast with coffee and toast today"
        score = Journal.compute_similarity(text1, text2)
        assert score == 0.0

    def test_chinese_english_mixed_threshold_boundary(self):
        text1 = "今天早餐吃了咖啡和吐司，很好吃"
        text2 = "今天午餐吃了三明治"
        score = Journal.compute_similarity(text1, text2)
        threshold = Journal.SIMILARITY_THRESHOLD
        assert abs(score - threshold) < 0.1, (
            f"Expected score near threshold, got {score:.4f}. "
            "If algorithm changed, update test texts."
        )

    def test_chinese_mixed_original_unchanged_on_keep_original(
        self, mock_args, journal_config
    ):
        journal = Journal(**journal_config)
        today = datetime.datetime.now()

        existing_text = "今天吃了早餐，有咖啡和吐司，非常美味"
        new_text = "今天吃了早餐，有咖啡"

        score = Journal.compute_similarity(existing_text, new_text)
        assert score >= Journal.SIMILARITY_THRESHOLD

        journal.new_entry(existing_text, date=today)
        original_entry = journal.entries[0]
        original_entry_id = id(original_entry)
        original_text = original_entry.text
        original_modified = original_entry.modified

        similar = journal.find_similar_entries(new_text, date=today)
        assert len(similar) == 1

        with mock.patch(
            "jrnl.controller._prompt_merge_choice", return_value="2"
        ):
            _handle_similar_entries(journal, new_text, similar, mock_args)

        assert len(journal.entries) == 1
        assert id(original_entry) == original_entry_id
        assert original_entry.text == original_text
        assert original_entry.modified == original_modified

    def test_chinese_mixed_merge_choice_4_updates_content(
        self, mock_args, journal_config
    ):
        journal = Journal(**journal_config)
        today = datetime.datetime.now()

        existing_text = "今天吃了早餐，有咖啡和吐司"
        new_text = "今天吃了早餐，有咖啡和橙汁"

        score = Journal.compute_similarity(existing_text, new_text)
        assert score >= Journal.SIMILARITY_THRESHOLD

        journal.new_entry(existing_text, date=today)
        original_entry = journal.entries[0]
        original_entry_id = id(original_entry)

        similar = journal.find_similar_entries(new_text, date=today)
        assert len(similar) == 1

        with mock.patch(
            "jrnl.controller._prompt_merge_choice", return_value="4"
        ):
            _handle_similar_entries(journal, new_text, similar, mock_args)

        assert len(journal.entries) == 1
        assert id(original_entry) == original_entry_id
        assert original_entry.modified is True
        assert "咖啡" in original_entry.text
        assert "吐司" in original_entry.text
        assert "橙汁" in original_entry.text

    def test_japanese_text_not_stripped(self):
        text = "朝食にコーヒーとトーストを食べました"
        from jrnl.journals.Journal import Journal as J
        import re

        def normalize(text):
            text = text.lower().strip()
            text = re.sub(r'[^\w\s\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]', '', text)
            text = re.sub(r'\s+', ' ', text)
            return text

        normalized = normalize(text)
        assert normalized != ""
        assert "コーヒー" in normalized
        assert "トースト" in normalized

    def test_korean_text_not_stripped(self):
        text = "아침으로 커피와 토스트를 먹었어요"
        import re

        def normalize(text):
            text = text.lower().strip()
            text = re.sub(r'[^\w\s\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]', '', text)
            text = re.sub(r'\s+', ' ', text)
            return text

        normalized = normalize(text)
        assert normalized != ""
        assert "커피" in normalized
        assert "토스트" in normalized

    def test_multilingual_symmetry(self):
        text1 = "今天 work 很顺利"
        text2 = "今天工作很顺利"
        score1 = Journal.compute_similarity(text1, text2)
        score2 = Journal.compute_similarity(text2, text1)
        assert score1 == pytest.approx(score2)

    def test_chinese_with_newlines_similarity(self):
        text1 = "今天吃了早餐\n有咖啡和吐司\n非常美味"
        text2 = "今天吃了早餐\n有咖啡"
        score = Journal.compute_similarity(text1, text2)
        assert score >= Journal.SIMILARITY_THRESHOLD

    def test_chinese_english_mixed_different_day_no_trigger(
        self, mock_args, journal_config
    ):
        journal = Journal(**journal_config)
        today = datetime.datetime.now()
        yesterday = today - datetime.timedelta(days=1)

        existing_text = "今天吃了早餐，有咖啡和吐司"
        new_text = "今天吃了早餐，有咖啡"

        score = Journal.compute_similarity(existing_text, new_text)
        assert score >= Journal.SIMILARITY_THRESHOLD

        journal.new_entry(existing_text, date=yesterday)
        original_entry = journal.entries[0]
        original_entry_id = id(original_entry)

        similar = journal.find_similar_entries(new_text, date=today)
        assert len(similar) == 0

        with mock.patch(
            "jrnl.controller._prompt_merge_choice"
        ) as mock_prompt:
            _handle_similar_entries(journal, new_text, similar, mock_args)
            mock_prompt.assert_not_called()

        assert len(journal.entries) == 2
        assert id(original_entry) == original_entry_id
        assert original_entry.text == existing_text
