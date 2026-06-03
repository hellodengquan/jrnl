# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import os
import tempfile
from argparse import Namespace
from pathlib import Path
from unittest import mock

import pytest

from jrnl.args import parse_args
from jrnl.config import DEFAULT_JOURNAL_KEY
from jrnl.config import get_default_config
from jrnl.config import get_journal_name
from jrnl.config import scope_config
from jrnl.controller import run
from jrnl.override import apply_overrides


@pytest.fixture
def isolated_config_dir():
    """Fixture to isolate user configuration by creating a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        home_dir = Path(tmpdir) / "home"
        home_dir.mkdir()
        config_dir = home_dir / ".config" / "jrnl"
        config_dir.mkdir(parents=True)

        with mock.patch.dict(os.environ, {"HOME": str(home_dir)}):
            with mock.patch("jrnl.path.get_config_path", return_value=str(config_dir / "jrnl.yaml")):
                yield {"config_dir": config_dir, "home_dir": home_dir}


@pytest.fixture
def multi_journal_config():
    """Fixture providing a multi-journal configuration dictionary."""
    base_config = get_default_config()
    base_config.update({
        "editor": "vim",
        "linewrap": 80,
        "timeformat": "%Y-%m-%d %H:%M",
    })
    base_config["journals"] = {
        "default": "/tmp/default.journal",
        "work": "/tmp/work.journal",
        "personal": {
            "journal": "/tmp/personal.journal",
            "editor": "nano",
            "linewrap": 100,
        },
    }
    return base_config


@pytest.fixture
def minimal_args():
    """Fixture providing minimal parsed arguments."""
    return Namespace(
        contains=None,
        debug=False,
        delete=False,
        edit=False,
        end_date=None,
        today_in_history=False,
        month=None,
        day=None,
        year=None,
        excluded=[],
        export=False,
        filename=None,
        limit=None,
        on_date=None,
        preconfig_cmd=None,
        postconfig_cmd=None,
        short=False,
        starred=False,
        start_date=None,
        strict=False,
        tags=False,
        text=[],
        config_override=[],
        config_file_path="",
        journal_name=None,
    )


class TestConfigOverrideFixture:
    """Tests for the isolated configuration fixture."""

    def test_isolated_config_dir_creates_temp_dir(self, isolated_config_dir):
        """Verify that the isolated config fixture creates a temporary directory."""
        assert isolated_config_dir["config_dir"].exists()
        assert isolated_config_dir["home_dir"].exists()
        assert "home" in str(isolated_config_dir["home_dir"])

    def test_isolated_config_dir_does_not_affect_real_config(self):
        """Verify that multiple test runs don't interfere with each other."""
        import os
        original_home = os.environ.get("HOME")
        with tempfile.TemporaryDirectory() as tmpdir:
            home_dir = Path(tmpdir) / "home"
            home_dir.mkdir()
            with mock.patch.dict(os.environ, {"HOME": str(home_dir)}):
                assert os.environ["HOME"] == str(home_dir)
        if original_home:
            assert os.environ.get("HOME") == original_home


class TestTemporaryOverride:
    """Tests for temporary config override functionality."""

    def test_override_editor_temporarily(self, multi_journal_config, minimal_args):
        """Override editor setting should only apply for this invocation."""
        assert multi_journal_config["editor"] == "vim"

        minimal_args.config_override = [["editor", "nano"]]
        result_config = apply_overrides(minimal_args, multi_journal_config.copy())

        assert result_config["editor"] == "nano"
        assert multi_journal_config["editor"] == "vim"

    def test_override_linewrap_with_integer(self, multi_journal_config, minimal_args):
        """Override linewrap with an integer value."""
        assert multi_journal_config["linewrap"] == 80

        minimal_args.config_override = [["linewrap", "120"]]
        result_config = apply_overrides(minimal_args, multi_journal_config.copy())

        assert result_config["linewrap"] == 120

    def test_override_nested_color_setting(self, multi_journal_config, minimal_args):
        """Override nested color configuration."""
        multi_journal_config["colors"] = {
            "body": "none",
            "date": "black",
            "tags": "yellow",
            "title": "cyan",
        }

        minimal_args.config_override = [["colors.body", "blue"]]
        result_config = apply_overrides(minimal_args, multi_journal_config.copy())

        assert result_config["colors"]["body"] == "blue"
        assert result_config["colors"]["date"] == "black"
        assert result_config["colors"]["tags"] == "yellow"

    def test_multiple_overrides_simultaneously(self, multi_journal_config, minimal_args):
        """Apply multiple configuration overrides at once."""
        multi_journal_config["colors"] = {
            "body": "none",
            "date": "black",
        }

        minimal_args.config_override = [
            ["editor", "emacs"],
            ["linewrap", "100"],
            ["colors.date", "green"],
        ]
        result_config = apply_overrides(minimal_args, multi_journal_config.copy())

        assert result_config["editor"] == "emacs"
        assert result_config["linewrap"] == 100
        assert result_config["colors"]["date"] == "green"

    def test_override_result_is_isolated_from_original(self, multi_journal_config, minimal_args):
        """Override result should be isolated when passing copy of original config."""
        config_to_modify = multi_journal_config.copy()
        original_editor = config_to_modify["editor"]
        original_linewrap = config_to_modify["linewrap"]

        minimal_args.config_override = [
            ["editor", "sublime"],
            ["linewrap", "200"],
        ]
        result = apply_overrides(minimal_args, config_to_modify)

        assert result["editor"] == "sublime"
        assert result["linewrap"] == 200
        assert original_editor == "vim"
        assert original_linewrap == 80

    def test_override_boolean_values(self, multi_journal_config, minimal_args):
        """Override boolean configuration values."""
        multi_journal_config["highlight"] = True

        minimal_args.config_override = [["highlight", "false"]]
        result_config = apply_overrides(minimal_args, multi_journal_config.copy())

        assert result_config["highlight"] is False

    def test_override_with_quoted_string_value(self, multi_journal_config, minimal_args):
        """Override with string values containing special characters."""
        minimal_args.config_override = [["timeformat", "\"%H:%M\""]]
        result_config = apply_overrides(minimal_args, multi_journal_config.copy())

        assert result_config["timeformat"] == "%H:%M"


class TestMultiJournalSelection:
    """Tests for multi-journal selection with overrides."""

    def test_default_journal_selected_by_default(self, multi_journal_config, minimal_args):
        """Default journal should be selected when no journal specified."""
        args = get_journal_name(minimal_args, multi_journal_config)

        assert args.journal_name == DEFAULT_JOURNAL_KEY

    def test_explicit_journal_selection(self, multi_journal_config):
        """Explicit journal name should be selected."""
        args = parse_args(["work", "some text"])
        args = get_journal_name(args, multi_journal_config)

        assert args.journal_name == "work"
        assert args.text == ["some text"]

    def test_journal_with_colon_syntax(self, multi_journal_config):
        """Journal name with colon suffix should be recognized."""
        args = parse_args(["work:", "entry text"])
        args = get_journal_name(args, multi_journal_config)

        assert args.journal_name == "work"
        assert args.text == ["entry text"]

    def test_journal_specific_config_applied(self, multi_journal_config):
        """Journal-specific configuration should be scoped properly."""
        args = parse_args(["personal"])
        args = get_journal_name(args, multi_journal_config)
        scoped_config = scope_config(multi_journal_config, args.journal_name)

        assert scoped_config["editor"] == "nano"
        assert scoped_config["linewrap"] == 100
        assert scoped_config["journal"] == "/tmp/personal.journal"

    def test_override_journal_path(self, multi_journal_config, minimal_args):
        """Override journal path through config override."""
        minimal_args.config_override = [["journals.default", "/tmp/override.journal"]]
        result_config = apply_overrides(minimal_args, multi_journal_config.copy())

        assert result_config["journals"]["default"] == "/tmp/override.journal"

    def test_override_new_journal(self, multi_journal_config, minimal_args):
        """Create a new journal through config override."""
        minimal_args.config_override = [["journals.temp", "/tmp/temp.journal"]]
        result_config = apply_overrides(minimal_args, multi_journal_config.copy())

        assert "temp" in result_config["journals"]
        assert result_config["journals"]["temp"] == "/tmp/temp.journal"

    def test_select_overridden_journal(self, multi_journal_config, minimal_args):
        """Select a journal that was added via override."""
        minimal_args.config_override = [["journals.temp", "/tmp/temp.journal"]]
        result_config = apply_overrides(minimal_args, multi_journal_config.copy())

        args = parse_args(["temp", "entry text"])
        args = get_journal_name(args, result_config)

        assert args.journal_name == "temp"
        assert args.text == ["entry text"]


class TestOverrideAndJournalIntegration:
    """Integration tests for overrides with journal selection."""

    def test_override_global_then_select_journal(self, multi_journal_config):
        """Override global setting and then select a specific journal."""
        args = parse_args(["personal", "--config-override", "editor", "emacs"])
        config = multi_journal_config.copy()
        config = apply_overrides(args, config)
        args = get_journal_name(args, config)
        scoped_config = scope_config(config, args.journal_name)

        assert scoped_config["editor"] == "nano"
        assert args.journal_name == "personal"

    def test_override_journal_specific_setting(self, multi_journal_config):
        """Override a journal-specific setting via dot notation."""
        args = parse_args(["--config-override", "journals.personal.editor", "sublime"])
        config = multi_journal_config.copy()
        config = apply_overrides(args, config)

        assert config["journals"]["personal"]["editor"] == "sublime"

    def test_select_work_journal_with_override(self, multi_journal_config):
        """Select work journal and apply override to it."""
        args = parse_args(["work", "--config-override", "linewrap", "150"])
        config = multi_journal_config.copy()
        config = apply_overrides(args, config)
        args = get_journal_name(args, config)

        assert args.journal_name == "work"
        assert config["linewrap"] == 150


class TestOutputContentAssertions:
    """Tests for output content assertions with overrides."""

    def test_output_with_linewrap_override(self):
        """Linewrap override should affect output formatting."""
        from io import StringIO

        import jrnl
        from jrnl.controller import _display_search_results

        args = parse_args(["--config-override", "linewrap", "40", "--format", "fancy"])
        config = get_default_config()
        config = apply_overrides(args, config)

        journal = jrnl.journals.Journal()
        journal.config = config
        journal.new_entry("2023-01-01: This is a long journal entry that should wrap at 40 characters")

        scoped_config = scope_config(config, DEFAULT_JOURNAL_KEY)

        with mock.patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            scoped_config["linewrap"] = 40
            _display_search_results(args, journal, config=scoped_config)
            output = mock_stdout.getvalue()

        assert "2023-01-01" in output
        assert "This is a long" in output
        assert "characters" in output

    def test_output_with_short_format_override(self):
        """Override display format to 'short'."""
        from io import StringIO

        import jrnl
        from jrnl.controller import _display_search_results

        args = parse_args(["--format", "short"])
        config = get_default_config()

        journal = jrnl.journals.Journal()
        journal.config = config
        journal.new_entry("2023-01-01: Test entry title\nBody text here")

        with mock.patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            _display_search_results(args, journal, config=config)
            output = mock_stdout.getvalue()

        assert "2023-01-01" in output
        assert "Test entry title" in output

    def test_output_with_timeformat_override(self):
        """Override timeformat should affect output dates."""
        from io import StringIO

        import jrnl
        from jrnl.controller import _display_search_results

        args = parse_args(["--config-override", "timeformat", "\"%H:%M\""])
        config = get_default_config()
        config = apply_overrides(args, config)

        journal = jrnl.journals.Journal()
        journal.config = config
        journal.new_entry("2023-01-01 14:30: Test entry")

        scoped_config = scope_config(config, DEFAULT_JOURNAL_KEY)

        with mock.patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            _display_search_results(args, journal, config=scoped_config)
            output = mock_stdout.getvalue()

        assert "14:30" in output

    def test_json_export_format(self):
        """JSON export format should produce valid JSON output."""
        from io import StringIO
        import json

        import jrnl
        from jrnl.controller import _display_search_results

        args = parse_args(["--format", "json"])
        config = get_default_config()

        journal = jrnl.journals.Journal()
        journal.config = config
        journal.new_entry("2023-01-01: JSON test entry")

        with mock.patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            _display_search_results(args, journal, config=config)
            output = mock_stdout.getvalue()

        parsed = json.loads(output)
        assert isinstance(parsed, dict)
        assert "entries" in parsed
        assert len(parsed["entries"]) > 0

    def test_tags_output_format(self):
        """Tags format should output tag statistics."""
        from io import StringIO

        import jrnl
        from jrnl.controller import _display_search_results

        args = parse_args(["--tags"])
        config = get_default_config()

        journal = jrnl.journals.Journal()
        journal.config = config
        journal.new_entry("2023-01-01: Entry with @test and @example")

        with mock.patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            _display_search_results(args, journal, config=config)
            output = mock_stdout.getvalue()

        assert "@test" in output or "@example" in output


class TestOverrideRegressionPrevention:
    """Regression tests to prevent override-related bugs."""

    def test_empty_override_does_nothing(self, multi_journal_config, minimal_args):
        """Empty override list should leave config unchanged."""
        original_config = multi_journal_config.copy()
        result_config = apply_overrides(minimal_args, multi_journal_config)

        assert result_config == original_config

    def test_override_nonexistent_key_creates_it(self, multi_journal_config, minimal_args):
        """Overriding a non-existent key should create it."""
        minimal_args.config_override = [["new_key", "new_value"]]
        result_config = apply_overrides(minimal_args, multi_journal_config.copy())

        assert "new_key" in result_config
        assert result_config["new_key"] == "new_value"

    def test_override_existing_nested_key(self, multi_journal_config, minimal_args):
        """Overriding existing nested key should work."""
        multi_journal_config["new_section"] = {"subkey": "old_value"}
        minimal_args.config_override = [["new_section.subkey", "new_value"]]
        result_config = apply_overrides(minimal_args, multi_journal_config.copy())

        assert result_config["new_section"]["subkey"] == "new_value"

    def test_journal_name_case_sensitive(self, multi_journal_config):
        """Journal names should be case-sensitive."""
        args = parse_args(["Work", "text"])
        args = get_journal_name(args, multi_journal_config)

        assert args.journal_name == DEFAULT_JOURNAL_KEY
        assert args.text == ["Work", "text"]

    def test_override_preserves_other_journals(self, multi_journal_config, minimal_args):
        """Override should not affect other journal configurations."""
        minimal_args.config_override = [["journals.work", "/tmp/new_work.journal"]]
        result_config = apply_overrides(minimal_args, multi_journal_config.copy())

        assert result_config["journals"]["work"] == "/tmp/new_work.journal"
        assert result_config["journals"]["default"] == "/tmp/default.journal"
        assert result_config["journals"]["personal"]["journal"] == "/tmp/personal.journal"

    def test_consecutive_overrides_independent(self, multi_journal_config, minimal_args):
        """Consecutive overrides should work independently."""
        config_copy = multi_journal_config.copy()

        minimal_args.config_override = [["editor", "nano"]]
        config1 = apply_overrides(minimal_args, config_copy.copy())

        minimal_args.config_override = [["editor", "emacs"]]
        config2 = apply_overrides(minimal_args, config_copy.copy())

        assert config1["editor"] == "nano"
        assert config2["editor"] == "emacs"
        assert config_copy["editor"] == "vim"
