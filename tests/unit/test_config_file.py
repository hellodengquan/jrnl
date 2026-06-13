# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import os
from unittest import mock

import pytest

import jrnl
from jrnl.args import parse_args
from jrnl.config import DEFAULT_JOURNAL_KEY
from jrnl.config import expand_config_paths
from jrnl.config import resolve_display_format
from jrnl.config import resolve_journal_name
from jrnl.config import resolve_runtime_config
from jrnl.config import validate_journal_name
from jrnl.controller import _display_search_results
from jrnl.exception import JrnlException
from jrnl.install import find_alt_config


def test_find_alt_config(request):
    work_config_path = os.path.join(
        request.fspath.dirname, "..", "data", "configs", "basic_onefile.yaml"
    )
    found_alt_config = find_alt_config(work_config_path)
    assert found_alt_config == work_config_path


def test_find_alt_config_not_exist(request):
    bad_config_path = os.path.join(
        request.fspath.dirname, "..", "data", "configs", "does-not-exist.yaml"
    )
    with pytest.raises(JrnlException) as ex:
        found_alt_config = find_alt_config(bad_config_path)
        assert found_alt_config is not None
    assert isinstance(ex.value, JrnlException)


class TestExpandConfigPaths:
    def test_expand_top_level_journal_path(self):
        config = {"journal": "~/journal.txt"}
        result = expand_config_paths(config)
        assert result["journal"] == os.path.expanduser("~/journal.txt")
        assert config["journal"] == "~/journal.txt"

    def test_expand_top_level_template_path(self):
        config = {"template": "~/template.txt"}
        result = expand_config_paths(config)
        assert result["template"] == os.path.expanduser("~/template.txt")

    def test_expand_journals_dict_journal_path(self):
        config = {
            "journals": {
                "default": {"journal": "~/default.txt"},
                "work": {"journal": "~/work.txt"},
            }
        }
        result = expand_config_paths(config)
        assert result["journals"]["default"]["journal"] == os.path.expanduser(
            "~/default.txt"
        )
        assert result["journals"]["work"]["journal"] == os.path.expanduser("~/work.txt")

    def test_expand_journals_dict_template_path(self):
        config = {
            "journals": {
                "default": {"journal": "~/default.txt", "template": "~/tmpl.txt"},
            }
        }
        result = expand_config_paths(config)
        assert result["journals"]["default"]["template"] == os.path.expanduser(
            "~/tmpl.txt"
        )

    def test_expand_journals_string_path(self):
        config = {"journals": {"default": "~/journal.txt", "work": "~/work.txt"}}
        result = expand_config_paths(config)
        assert result["journals"]["default"] == os.path.expanduser("~/journal.txt")
        assert result["journals"]["work"] == os.path.expanduser("~/work.txt")

    def test_non_string_paths_unchanged(self):
        config = {
            "journal": None,
            "template": False,
            "journals": {"default": {"journal": None, "encrypt": True}},
        }
        result = expand_config_paths(config)
        assert result["journal"] is None
        assert result["template"] is False
        assert result["journals"]["default"]["journal"] is None
        assert result["journals"]["default"]["encrypt"] is True

    @mock.patch.dict(os.environ, {"TEST_JRNL_PATH": "/tmp/test"})
    def test_expand_environment_variables(self):
        config = {"journal": "$TEST_JRNL_PATH/journal.txt"}
        result = expand_config_paths(config)
        assert result["journal"] == "/tmp/test/journal.txt"

    def test_empty_config_no_error(self):
        result = expand_config_paths({})
        assert result == {}


class TestResolveJournalName:
    def test_default_when_no_text(self):
        args = parse_args([])
        config = {"journals": {"default": {}}}
        result = resolve_journal_name(args, config)
        assert result.journal_name == DEFAULT_JOURNAL_KEY
        assert result.text == []

    def test_text_first_arg_is_journal_name_no_colon(self):
        args = parse_args(["work", "some", "text"])
        config = {"journals": {"default": {}, "work": {}}}
        result = resolve_journal_name(args, config)
        assert result.journal_name == "work"
        assert result.text == ["some", "text"]

    def test_text_first_arg_is_journal_name_with_colon(self):
        args = parse_args(["work:", "some", "text"])
        config = {"journals": {"default": {}, "work": {}}}
        result = resolve_journal_name(args, config)
        assert result.journal_name == "work"
        assert result.text == ["some", "text"]

    def test_text_first_arg_not_journal_name(self):
        args = parse_args(["unknown:", "some", "text"])
        config = {"journals": {"default": {}, "work": {}}}
        result = resolve_journal_name(args, config)
        assert result.journal_name == DEFAULT_JOURNAL_KEY
        assert result.text == ["unknown:", "some", "text"]

    def test_colon_inside_text_not_journal_name(self):
        args = parse_args(["hello:world"])
        config = {"journals": {"default": {}}}
        result = resolve_journal_name(args, config)
        assert result.journal_name == DEFAULT_JOURNAL_KEY
        assert result.text == ["hello:world"]


class TestResolveDisplayFormat:
    def test_cli_format_overrides_config(self):
        args = parse_args(["--format", "markdown"])
        config = {"display_format": "json"}
        result = resolve_display_format(args, config)
        assert result.export == "markdown"

    def test_tags_flag_sets_tags_format(self):
        args = parse_args(["--tags"])
        config = {}
        result = resolve_display_format(args, config)
        assert result.export == "tags"

    def test_tags_with_explicit_format_keeps_format(self):
        args = parse_args(["--tags", "--format", "json"])
        config = {}
        result = resolve_display_format(args, config)
        assert result.export == "json"

    def test_config_display_format_used_when_no_cli(self):
        args = parse_args([])
        config = {"display_format": "markdown"}
        result = resolve_display_format(args, config)
        assert result.export == "markdown"

    def test_no_format_returns_false(self):
        args = parse_args([])
        config = {}
        result = resolve_display_format(args, config)
        assert result.export is False

    def test_short_flag_not_affected(self):
        args = parse_args(["--short"])
        config = {"display_format": "markdown"}
        result = resolve_display_format(args, config)
        assert result.export == "markdown"
        assert result.short is True


class TestResolveRuntimeConfig:
    def _make_config(self):
        return {
            "journals": {
                "default": {"journal": "~/default.txt", "linewrap": 80},
                "work": {
                    "journal": "~/work.txt",
                    "linewrap": 100,
                    "display_format": "markdown",
                },
            },
            "linewrap": 80,
            "display_format": "json",
        }

    def test_full_resolution_default_journal(self):
        args = parse_args([])
        config = self._make_config()
        result_args, result_config = resolve_runtime_config(args, config)

        assert result_args.journal_name == DEFAULT_JOURNAL_KEY
        assert result_config["journal"] == os.path.expanduser("~/default.txt")
        assert result_config["linewrap"] == 80
        assert result_args.export == "json"

    def test_full_resolution_named_journal(self):
        args = parse_args(["work"])
        config = self._make_config()
        result_args, result_config = resolve_runtime_config(args, config)

        assert result_args.journal_name == "work"
        assert result_args.text == []
        assert result_config["journal"] == os.path.expanduser("~/work.txt")
        assert result_config["linewrap"] == 100
        assert result_args.export == "markdown"

    def test_journal_specific_overrides_global(self):
        args = parse_args(["work"])
        config = self._make_config()
        result_args, result_config = resolve_runtime_config(args, config)

        assert result_config["display_format"] == "markdown"
        assert result_args.export == "markdown"

    def test_cli_format_overrides_journal_config(self):
        args = parse_args(["work", "--format", "yaml"])
        config = self._make_config()
        result_args, result_config = resolve_runtime_config(args, config)

        assert result_args.export == "yaml"

    def test_no_journal_resolution_for_list_cmd(self):
        args = parse_args(["--list"])
        config = self._make_config()
        result_args, result_config = resolve_runtime_config(
            args, config, resolve_journal=False, scope=False, resolve_display=False
        )

        assert "journal" not in result_config
        assert result_config["journals"]["default"]["journal"] == os.path.expanduser(
            "~/default.txt"
        )
        assert result_args.export is False

    def test_two_phase_path_expansion(self):
        config = {
            "journals": {
                "default": {"journal": "~/outer.txt", "template": "~/outer_tmpl.txt"},
            },
            "template": "~/global_tmpl.txt",
        }
        args = parse_args([])

        result_args, result_config = resolve_runtime_config(args, config)

        assert result_config["journals"]["default"]["journal"] == os.path.expanduser(
            "~/outer.txt"
        )
        assert result_config["journal"] == os.path.expanduser("~/outer.txt")
        assert result_config["template"] == os.path.expanduser("~/outer_tmpl.txt")

    def test_scope_false_keeps_global_config(self):
        args = parse_args(["work"])
        config = self._make_config()
        result_args, result_config = resolve_runtime_config(
            args, config, scope=False
        )

        assert result_args.journal_name == "work"
        assert "journal" not in result_config
        assert result_config["linewrap"] == 80
        assert result_config["display_format"] == "json"

    def test_resolve_display_false_keeps_cli_format(self):
        args = parse_args(["--format", "xml"])
        config = self._make_config()
        result_args, result_config = resolve_runtime_config(
            args, config, resolve_display=False
        )

        assert result_args.export == "xml"

    def test_invalid_journal_name_raises(self):
        args = parse_args([])
        config = {"journals": {"work": "~/work.txt"}}
        with pytest.raises(JrnlException):
            resolve_runtime_config(args, config)

    def test_validate_journal_name_invalid_raises(self):
        config = {"journals": {"default": "~/default.txt"}}
        with pytest.raises(JrnlException):
            validate_journal_name("invalid", config)

    def test_validate_journal_name_valid_passes(self):
        config = {"journals": {"default": "~/default.txt", "work": "~/work.txt"}}
        validate_journal_name("work", config)
        validate_journal_name("default", config)

    def test_colon_journal_name_works(self):
        args = parse_args(["work:"])
        config = self._make_config()
        result_args, result_config = resolve_runtime_config(args, config)

        assert result_args.journal_name == "work"
        assert result_args.text == []


class TestExpandConfigPathsDeepcopy:
    def test_original_config_journals_dict_not_mutated(self):
        original = {
            "journals": {
                "default": {"journal": "~/journal.txt", "template": "~/tmpl.txt"},
            }
        }
        original_inner_ref = original["journals"]["default"]
        expand_config_paths(original)
        assert original["journals"]["default"] is original_inner_ref
        assert original["journals"]["default"]["journal"] == "~/journal.txt"
        assert original["journals"]["default"]["template"] == "~/tmpl.txt"

    def test_original_config_journals_string_not_mutated(self):
        original = {"journals": {"default": "~/journal.txt"}}
        expand_config_paths(original)
        assert original["journals"]["default"] == "~/journal.txt"

    def test_original_config_top_level_not_mutated(self):
        original = {"journal": "~/journal.txt", "template": "~/tmpl.txt"}
        expand_config_paths(original)
        assert original["journal"] == "~/journal.txt"
        assert original["template"] == "~/tmpl.txt"


class TestExpandConfigPathsEdgeCases:
    def test_tilde_with_application_support_path(self):
        config = {
            "journals": {
                "default": {
                    "journal": "~/Library/Application Support/jrnl/journal.txt"
                },
            }
        }
        result = expand_config_paths(config)
        expected = os.path.expanduser(
            "~/Library/Application Support/jrnl/journal.txt"
        )
        assert result["journals"]["default"]["journal"] == expected
        assert " " in expected

    @mock.patch.dict(os.environ, {"JRNL_HOME": "/home/user"})
    def test_dollar_var_with_nested_path(self):
        config = {
            "journals": {
                "notes": {"journal": "$JRNL_HOME/notes/journal.txt"},
            }
        }
        result = expand_config_paths(config)
        assert result["journals"]["notes"]["journal"] == "/home/user/notes/journal.txt"

    @mock.patch.dict(os.environ, {"JRNL_DATA": "/tmp/my data"})
    def test_dollar_var_path_with_spaces(self):
        config = {
            "journals": {
                "default": {"journal": "$JRNL_DATA/journal.txt"},
            }
        }
        result = expand_config_paths(config)
        assert result["journals"]["default"]["journal"] == "/tmp/my data/journal.txt"

    def test_tilde_plus_space_in_path(self):
        config = {
            "journals": {
                "default": {
                    "journal": "~/My Documents/jrnl/journal.txt"
                },
            }
        }
        result = expand_config_paths(config)
        expected = os.path.expanduser("~/My Documents/jrnl/journal.txt")
        assert result["journals"]["default"]["journal"] == expected
        assert " " in expected

    @mock.patch.dict(os.environ, {"HOME": "/home/test user"})
    def test_tilde_expand_with_env_home_containing_space(self):
        config = {
            "journals": {
                "default": {"journal": "~/notes/journal.txt"},
            }
        }
        result = expand_config_paths(config)
        assert (
            result["journals"]["default"]["journal"]
            == "/home/test user/notes/journal.txt"
        )

    def test_top_level_journal_with_spaces(self):
        config = {"journal": "~/Library/Application Support/jrnl/journal.txt"}
        result = expand_config_paths(config)
        assert result["journal"] == os.path.expanduser(
            "~/Library/Application Support/jrnl/journal.txt"
        )

    def test_template_path_with_spaces(self):
        config = {"template": "~/My Templates/jrnl template.txt"}
        result = expand_config_paths(config)
        assert result["template"] == os.path.expanduser(
            "~/My Templates/jrnl template.txt"
        )

    def test_mixed_tilde_and_env_var_in_journals(self):
        with mock.patch.dict(os.environ, {"JRNL_WORK": "/work/path"}):
            config = {
                "journals": {
                    "personal": {"journal": "~/personal/journal.txt"},
                    "work": {"journal": "$JRNL_WORK/journal.txt"},
                }
            }
            result = expand_config_paths(config)
            assert result["journals"]["personal"]["journal"] == os.path.expanduser(
                "~/personal/journal.txt"
            )
            assert result["journals"]["work"]["journal"] == "/work/path/journal.txt"

    def test_string_journal_with_spaces(self):
        config = {"journals": {"default": "~/My Journal Folder/journal.txt"}}
        result = expand_config_paths(config)
        assert result["journals"]["default"] == os.path.expanduser(
            "~/My Journal Folder/journal.txt"
        )


class TestTwoPhasePathExpansionRegression:
    def test_first_phase_expands_journals_section(self):
        config = {
            "journals": {
                "default": {"journal": "~/default.txt"},
                "work": {"journal": "$HOME/work.txt"},
            },
        }
        args = parse_args([])
        result_args, result_config = resolve_runtime_config(
            args, config, scope=False
        )
        assert result_config["journals"]["default"]["journal"] == os.path.expanduser(
            "~/default.txt"
        )
        assert result_config["journals"]["work"]["journal"] == os.path.expandvars(
            "$HOME/work.txt"
        )

    def test_second_phase_expands_scoped_journal_path(self):
        config = {
            "journals": {
                "default": {"journal": "~/default.txt"},
            },
        }
        args = parse_args([])
        result_args, result_config = resolve_runtime_config(args, config)
        assert result_config["journal"] == os.path.expanduser("~/default.txt")

    def test_second_phase_expands_scoped_template(self):
        config = {
            "journals": {
                "default": {"journal": "~/default.txt", "template": "~/tmpl.txt"},
            },
        }
        args = parse_args([])
        result_args, result_config = resolve_runtime_config(args, config)
        assert result_config["template"] == os.path.expanduser("~/tmpl.txt")

    @mock.patch.dict(os.environ, {"JRNL_WORK": "/work/dir"})
    def test_scoped_env_var_path_expanded_after_scope(self):
        config = {
            "journals": {
                "work": {"journal": "$JRNL_WORK/journal.txt"},
            },
        }
        args = parse_args(["work"])
        result_args, result_config = resolve_runtime_config(args, config)
        assert result_config["journal"] == "/work/dir/journal.txt"

    def test_scoped_path_with_spaces_after_scope(self):
        config = {
            "journals": {
                "default": {
                    "journal": "~/Library/Application Support/jrnl/journal.txt"
                },
            },
        }
        args = parse_args([])
        result_args, result_config = resolve_runtime_config(args, config)
        assert result_config["journal"] == os.path.expanduser(
            "~/Library/Application Support/jrnl/journal.txt"
        )
        assert " " in result_config["journal"]

    def test_global_template_overridden_by_journal_template(self):
        config = {
            "journals": {
                "default": {"journal": "~/default.txt", "template": "~/local.txt"},
            },
            "template": "~/global.txt",
        }
        args = parse_args([])
        result_args, result_config = resolve_runtime_config(args, config)
        assert result_config["template"] == os.path.expanduser("~/local.txt")

    def test_original_config_not_mutated_by_two_phase(self):
        config = {
            "journals": {
                "default": {"journal": "~/default.txt", "template": "~/tmpl.txt"},
            },
            "template": "~/global.txt",
        }
        import copy

        original = copy.deepcopy(config)
        resolve_runtime_config(parse_args([]), config)
        assert config == original


class TestCliE2eDisplaySearchResults:
    def _make_journal_with_entry(self):
        journal = jrnl.journals.Journal()
        journal.new_entry("test entry for e2e")
        return journal

    def test_format_markdown_produces_markdown_output(self):
        args = parse_args(["--format", "markdown"])
        journal = self._make_journal_with_entry()

        with mock.patch("builtins.print") as mock_print:
            _display_search_results(args, journal)
            mock_print.assert_called_once()
            output = mock_print.call_args[0][0]
            assert isinstance(output, str)

    def test_format_json_produces_json_output(self):
        import json

        args = parse_args(["--format", "json"])
        journal = self._make_journal_with_entry()

        with mock.patch("builtins.print") as mock_print:
            _display_search_results(args, journal)
            mock_print.assert_called_once()
            output = mock_print.call_args[0][0]
            parsed = json.loads(output)
            assert "entries" in parsed

    def test_format_yaml_produces_yaml_output(self):
        args = parse_args(["--format", "yaml"])
        journal = self._make_journal_with_entry()

        with mock.patch("jrnl.plugins.get_exporter") as mock_get_exporter, \
             mock.patch("builtins.print"):
            mock_exporter = mock.Mock()
            mock_exporter.export = mock.Mock(return_value="entries: []")
            mock_get_exporter.return_value = mock_exporter

            _display_search_results(args, journal)
            mock_get_exporter.assert_called_once_with("yaml")
            mock_exporter.export.assert_called_once()

    def test_format_tags_produces_tag_output(self):
        args = parse_args(["--tags"])
        journal = self._make_journal_with_entry()

        with mock.patch("builtins.print") as mock_print:
            _display_search_results(args, journal)
            mock_print.assert_called_once()

    def test_format_short_uses_pprint_short(self):
        args = parse_args(["--short"])
        journal = self._make_journal_with_entry()
        journal.pprint = mock.Mock(return_value="short output")

        _display_search_results(args, journal)
        journal.pprint.assert_called_once_with(short=True)

    def test_no_format_defaults_to_pretty(self):
        args = parse_args([])
        args.export = False
        journal = self._make_journal_with_entry()
        journal.pprint = mock.Mock(return_value="pretty output")

        _display_search_results(args, journal)
        journal.pprint.assert_called_once_with()

    def test_empty_journal_returns_early(self):
        args = parse_args(["--format", "markdown"])
        journal = jrnl.journals.Journal()

        with mock.patch("builtins.print") as mock_print:
            _display_search_results(args, journal)
            mock_print.assert_not_called()


class TestCliE2eResolveThenDisplay:
    def _make_config(self):
        return {
            "journals": {
                "default": {"journal": "~/default.txt"},
            },
            "linewrap": 80,
            "display_format": "json",
        }

    def test_config_display_format_flows_to_display(self):
        args = parse_args([])
        config = self._make_config()
        args, config = resolve_runtime_config(args, config)

        assert args.export == "json"

        journal = jrnl.journals.Journal()
        journal.new_entry("e2e test entry")

        with mock.patch("builtins.print") as mock_print:
            _display_search_results(args, journal)
            mock_print.assert_called_once()

    def test_cli_format_overrides_config_display_format_e2e(self):
        args = parse_args(["--format", "markdown"])
        config = self._make_config()
        args, config = resolve_runtime_config(args, config)

        assert args.export == "markdown"

        journal = jrnl.journals.Journal()
        journal.new_entry("e2e test entry")

        with mock.patch("builtins.print") as mock_print:
            _display_search_results(args, journal)
            mock_print.assert_called_once()

    def test_journal_specific_display_format_e2e(self):
        config = {
            "journals": {
                "default": {"journal": "~/default.txt"},
                "work": {
                    "journal": "~/work.txt",
                    "display_format": "yaml",
                },
            },
            "display_format": "json",
        }
        args = parse_args(["work"])
        args, config = resolve_runtime_config(args, config)

        assert args.export == "yaml"

        journal = jrnl.journals.Journal()
        journal.new_entry("e2e work entry")

        with mock.patch("jrnl.plugins.get_exporter") as mock_get_exporter, \
             mock.patch("builtins.print"):
            mock_exporter = mock.Mock()
            mock_exporter.export = mock.Mock(return_value="entries: []")
            mock_get_exporter.return_value = mock_exporter

            _display_search_results(args, journal)
            mock_get_exporter.assert_called_once_with("yaml")

    def test_tags_flag_e2e(self):
        config = self._make_config()
        args = parse_args(["--tags"])
        args, config = resolve_runtime_config(args, config)

        assert args.export == "tags"

        journal = jrnl.journals.Journal()
        journal.new_entry("e2e test entry")

        with mock.patch("builtins.print") as mock_print:
            _display_search_results(args, journal)
            mock_print.assert_called_once()

    def test_no_display_format_e2e_defaults_pretty(self):
        config = {
            "journals": {
                "default": {"journal": "~/default.txt"},
            },
            "linewrap": 80,
        }
        args = parse_args([])
        args, config = resolve_runtime_config(args, config)

        assert args.export is False

        journal = jrnl.journals.Journal()
        journal.new_entry("e2e test entry")
        journal.pprint = mock.Mock(return_value="pretty output")

        _display_search_results(args, journal)
        journal.pprint.assert_called_once_with()

    def test_short_flag_e2e(self):
        config = self._make_config()
        args = parse_args(["--short"])
        args, config = resolve_runtime_config(args, config)

        assert args.short is True
        assert args.export == "json"

        journal = jrnl.journals.Journal()
        journal.new_entry("e2e test entry")
        journal.pprint = mock.Mock(return_value="short output")

        _display_search_results(args, journal)
        journal.pprint.assert_called_once_with(short=True)
