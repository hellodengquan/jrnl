# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import json
import os
import subprocess
import sys
import tempfile
import time as time_mod
from unittest import mock

import pytest
from ruamel.yaml import YAML

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


class TestSubprocessCliSmoke:
    @pytest.fixture
    def tmp_jrnl_env(self, monkeypatch):
        tmpdir = tempfile.mkdtemp(prefix="jrnl_smoke_")
        config_path = os.path.join(tmpdir, "jrnl.yaml")
        journal_path = os.path.join(tmpdir, "journal.txt")

        config_content = {
            "journals": {"default": journal_path},
            "linewrap": 80,
        }

        yaml = YAML(typ="safe")
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config_content, f)

        with open(journal_path, "w", encoding="utf-8") as f:
            f.write("2023-01-15 10:00 Title One\n\nBody of first entry.\n\n")
            f.write("2023-02-20 14:30 Title Two @tag\n\nSecond body.\n\n")

        monkeypatch.delenv("JRNL_CONFIG", raising=False)
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)

        return {
            "tmpdir": tmpdir,
            "config_path": config_path,
            "journal_path": journal_path,
            "env": os.environ.copy(),
        }

    def _run_cli(self, tmp_env, cli_args):
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        env = tmp_env["env"].copy()
        env["PYTHONPATH"] = (
            project_root + os.pathsep + env.get("PYTHONPATH", "")
        )

        cmd = [
            sys.executable,
            "-m",
            "jrnl",
            "--config-file",
            tmp_env["config_path"],
        ] + cli_args

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            cwd=tmp_env["tmpdir"],
            timeout=30,
        )
        return result

    def test_cli_format_markdown_smoke(self, tmp_jrnl_env):
        result = self._run_cli(tmp_jrnl_env, ["--format", "markdown"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "# " in result.stdout or "## " in result.stdout or result.stdout

    def test_cli_format_json_smoke(self, tmp_jrnl_env):
        result = self._run_cli(tmp_jrnl_env, ["--format", "json"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        parsed = json.loads(result.stdout)
        assert "entries" in parsed
        assert len(parsed["entries"]) >= 1

    def test_cli_tags_flag_smoke(self, tmp_jrnl_env):
        result = self._run_cli(tmp_jrnl_env, ["--tags"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "@tag" in result.stdout

    def test_cli_no_format_pretty_smoke(self, tmp_jrnl_env):
        result = self._run_cli(tmp_jrnl_env, ["-contains", "Title"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "Title One" in result.stdout or result.stdout


class TestFormatTagsAlternationRegression:
    def _make_config(self):
        return {
            "journals": {
                "default": {"journal": "~/default.txt"},
            },
            "linewrap": 80,
            "display_format": None,
        }

    def _make_journal(self):
        journal = jrnl.journals.Journal()
        journal.new_entry("entry one @alpha @beta")
        journal.new_entry("entry two @alpha")
        return journal

    @mock.patch("builtins.print")
    def test_format_then_tags_no_pollution(self, mock_print):
        config = self._make_config()
        journal = self._make_journal()

        args1, cfg1 = resolve_runtime_config(
            parse_args(["--format", "json"]), config
        )
        _display_search_results(args1, journal)

        args2, cfg2 = resolve_runtime_config(parse_args(["--tags"]), config)
        assert args2.export == "tags"
        assert cfg2.get("display_format") is None or not cfg2.get("display_format")

        with mock.patch("jrnl.plugins.get_exporter") as mock_get_exp:
            mock_exp = mock.Mock()
            mock_exp.export = mock.Mock(return_value="tag list")
            mock_get_exp.return_value = mock_exp
            _display_search_results(args2, journal)
            mock_get_exp.assert_called_once_with("tags")

    @mock.patch("builtins.print")
    def test_tags_then_format_no_pollution(self, mock_print):
        config = self._make_config()
        journal = self._make_journal()

        args1, _ = resolve_runtime_config(parse_args(["--tags"]), config)
        _display_search_results(args1, journal)

        args2, _ = resolve_runtime_config(
            parse_args(["--format", "markdown"]), config
        )
        assert args2.export == "markdown"

    @mock.patch("builtins.print")
    def test_format_json_format_markdown_no_cross_contamination(self, mock_print):
        config = {"journals": {"default": {"journal": "~/j.txt"}}}
        journal = self._make_journal()

        args1, _ = resolve_runtime_config(
            parse_args(["--format", "json"]), config
        )
        assert args1.export == "json"
        _display_search_results(args1, journal)

        args2, _ = resolve_runtime_config(
            parse_args(["--format", "markdown"]), config
        )
        assert args2.export == "markdown"

        args3, _ = resolve_runtime_config(
            parse_args(["--tags"]), config
        )
        assert args3.export == "tags"

    @mock.patch("builtins.print")
    def test_five_round_trip_alternation_no_state_leak(self, mock_print):
        config = {"journals": {"default": {"journal": "~/j.txt"}}}
        expected_sequence = [
            (["--format", "json"], "json"),
            (["--tags"], "tags"),
            (["--format", "markdown"], "markdown"),
            (["--tags"], "tags"),
            (["--format", "yaml"], "yaml"),
        ]
        for cli_args, expected_format in expected_sequence:
            args, _ = resolve_runtime_config(parse_args(cli_args), config)
            assert args.export == expected_format


class TestResolveRuntimeConfigBenchmark:
    NUM_JOURNALS = 50
    SAMPLE_ITERATIONS = 100

    def _make_large_config(self, num_journals=NUM_JOURNALS):
        journals = {}
        for i in range(num_journals):
            journals[f"journal_{i:03d}"] = {
                "journal": f"~/journals/j_{i:03d}/journal.txt",
                "template": f"~/templates/tpl_{i:03d}.txt",
                "linewrap": 80 + i % 10,
                "editor": "vim" if i % 2 == 0 else "nano",
                "tagsymbols": "@",
                "display_format": ["markdown", "json", "yaml", None][i % 4],
                "encrypt": i % 7 == 0,
            }
        return {
            "journals": journals,
            "linewrap": 80,
            "tagsymbols": "@",
            "display_format": "markdown",
            "editor": None,
            "template": "~/global_template.txt",
        }

    def _select_journal_args(self, idx):
        return parse_args([f"journal_{idx:03d}"])

    def test_50_journals_resolve_is_snappy(self):
        config = self._make_large_config(50)
        args_list = [self._select_journal_args(i % 50) for i in range(50)]

        start = time_mod.perf_counter()
        for args in args_list:
            resolve_runtime_config(args, config)
        elapsed = time_mod.perf_counter() - start

        assert elapsed < 1.0, (
            f"Resolving 50 journal configs took {elapsed:.3f}s, expected <1s"
        )

    def test_large_config_100_iterations_benchmark(self):
        config = self._make_large_config(self.NUM_JOURNALS)
        args_seq = [
            self._select_journal_args(i % self.NUM_JOURNALS)
            for i in range(self.SAMPLE_ITERATIONS)
        ]

        start = time_mod.perf_counter()
        for args in args_seq:
            resolve_runtime_config(args, config)
        total = time_mod.perf_counter() - start
        per_call_avg = total / self.SAMPLE_ITERATIONS

        assert per_call_avg < 0.020, (
            f"Avg per-call {per_call_avg:.5f}s exceeds 20ms budget; "
            f"total {total:.3f}s over {self.SAMPLE_ITERATIONS} calls"
        )

    def test_scoped_paths_all_expanded(self):
        config = self._make_large_config(self.NUM_JOURNALS)

        for i in range(self.NUM_JOURNALS):
            args = self._select_journal_args(i)
            resolved_args, scoped = resolve_runtime_config(args, config)

            assert resolved_args.journal_name == f"journal_{i:03d}"
            assert scoped["journal"] == os.path.expanduser(
                f"~/journals/j_{i:03d}/journal.txt"
            )
            assert scoped["template"] == os.path.expanduser(
                f"~/templates/tpl_{i:03d}.txt"
            )

    def test_original_large_config_immutable(self):
        import copy

        config = self._make_large_config(self.NUM_JOURNALS)
        snapshot = copy.deepcopy(config)

        for i in range(10):
            resolve_runtime_config(self._select_journal_args(i), config)

        assert config == snapshot, (
            "resolve_runtime_config mutated the original large config reference"
        )


class TestSubprocessMultiPythonEnv:
    """
    Verifies that subprocess CLI smoke tests are robust against
    pyenv / venv / system Python interpreter mismatches.
    """

    def _run_python_subprocess(self, extra_env=None):
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)
        env["PYTHONPATH"] = project_root + os.pathsep + env.get("PYTHONPATH", "")

        tmpdir = tempfile.mkdtemp(prefix="jrnl_subp_")
        script_path = os.path.join(tmpdir, "check_env.py")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(
                "import sys\n"
                "import json\n"
                "try:\n"
                "    import jrnl\n"
                "    jrnl_ver = jrnl.__version__\n"
                "except Exception:\n"
                "    jrnl_ver = None\n"
                "print(json.dumps({\n"
                "    'executable': sys.executable,\n"
                "    'version': sys.version,\n"
                "    'version_info': list(sys.version_info[:3]),\n"
                "    'has_jrnl': jrnl_ver,\n"
                "}))\n"
            )

        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
        return result

    def test_subprocess_uses_same_executable_as_parent(self):
        result = self._run_python_subprocess()
        assert result.returncode == 0, f"stderr: {result.stderr}"
        info = json.loads(result.stdout)
        assert info["executable"] == sys.executable, (
            f"Subprocess interpreter {info['executable']} != "
            f"parent {sys.executable}"
        )

    def test_subprocess_python_version_matches_parent(self):
        result = self._run_python_subprocess()
        assert result.returncode == 0, f"stderr: {result.stderr}"
        info = json.loads(result.stdout)
        assert tuple(info["version_info"]) == sys.version_info[:3]

    def test_subprocess_can_import_jrnl(self):
        result = self._run_python_subprocess()
        assert result.returncode == 0, f"stderr: {result.stderr}"
        info = json.loads(result.stdout)
        assert info["has_jrnl"] is not None, "jrnl failed to import in subprocess"

    def test_subprocess_pythonpath_injection_works(self):
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        env = os.environ.copy()
        env["PYTHONPATH"] = project_root + os.pathsep + env.get("PYTHONPATH", "")

        result = subprocess.run(
            [sys.executable, "-c", "import jrnl; print(jrnl.__version__)"],
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert result.stdout.strip()

    def test_cli_smoke_with_virtualenv_style_env(self):
        """Simulate a venv-style environment (VIRTUAL_ENV set) and verify CLI works."""
        tmpdir = tempfile.mkdtemp(prefix="jrnl_venvtest_")
        config_path = os.path.join(tmpdir, "jrnl.yaml")
        journal_path = os.path.join(tmpdir, "journal.txt")

        yaml = YAML(typ="safe")
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump({"journals": {"default": journal_path}}, f)

        with open(journal_path, "w", encoding="utf-8") as f:
            f.write("2023-01-01 10:00 Title\n\nBody.\n\n")

        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        env = os.environ.copy()
        env["VIRTUAL_ENV"] = os.path.dirname(sys.executable)
        env["PYTHONPATH"] = project_root + os.pathsep + env.get("PYTHONPATH", "")

        cmd = [
            sys.executable,
            "-m",
            "jrnl",
            "--config-file",
            config_path,
            "--format",
            "json",
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, env=env, cwd=tmpdir, timeout=30
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        parsed = json.loads(result.stdout)
        assert "entries" in parsed


class TestBenchmarkExtendedThresholds:
    """
    Stricter performance assertions to catch performance regressions.
    Uses percentile-based and worst-case checks rather than just averages.
    """

    NUM_JOURNALS = 50
    SAMPLE_ITERATIONS = 200
    WORST_CASE_MS_THRESHOLD = 100.0
    P95_MS_THRESHOLD = 50.0
    DEFAULT_JOURNAL_FAST_PATH_MS = 20.0

    def _make_large_config(self):
        journals = {
            "default": {
                "journal": "~/journals/default/journal.txt",
                "template": "~/templates/default_tpl.txt",
                "linewrap": 80,
                "editor": "vim",
                "tagsymbols": "@",
                "display_format": "markdown",
                "encrypt": False,
            }
        }
        for i in range(self.NUM_JOURNALS):
            journals[f"journal_{i:03d}"] = {
                "journal": f"~/journals/j_{i:03d}/journal.txt",
                "template": f"~/templates/tpl_{i:03d}.txt",
                "linewrap": 80 + i % 10,
                "editor": "vim" if i % 2 == 0 else "nano",
                "tagsymbols": "@",
                "display_format": ["markdown", "json", "yaml", None][i % 4],
                "encrypt": i % 7 == 0,
            }
        return {
            "journals": journals,
            "linewrap": 80,
            "tagsymbols": "@",
            "display_format": "markdown",
            "editor": None,
            "template": "~/global_template.txt",
        }

    def test_worst_case_latency_under_threshold(self):
        config = self._make_large_config()
        times = []

        for i in range(self.SAMPLE_ITERATIONS):
            args = parse_args([f"journal_{i % self.NUM_JOURNALS:03d}"])
            start = time_mod.perf_counter()
            resolve_runtime_config(args, config)
            elapsed_ms = (time_mod.perf_counter() - start) * 1000
            times.append(elapsed_ms)

        worst = max(times)
        assert worst < self.WORST_CASE_MS_THRESHOLD, (
            f"Worst-case resolve took {worst:.2f}ms, "
            f"threshold {self.WORST_CASE_MS_THRESHOLD}ms"
        )

    def test_p95_latency_under_threshold(self):
        config = self._make_large_config()
        times = []

        for i in range(self.SAMPLE_ITERATIONS):
            args = parse_args([f"journal_{i % self.NUM_JOURNALS:03d}"])
            start = time_mod.perf_counter()
            resolve_runtime_config(args, config)
            elapsed_ms = (time_mod.perf_counter() - start) * 1000
            times.append(elapsed_ms)

        sorted_times = sorted(times)
        p95_idx = int(len(sorted_times) * 0.95)
        p95 = sorted_times[min(p95_idx, len(sorted_times) - 1)]
        assert p95 < self.P95_MS_THRESHOLD, (
            f"P95 resolve took {p95:.2f}ms, "
            f"threshold {self.P95_MS_THRESHOLD}ms"
        )

    def test_default_journal_fast_path_performance(self):
        config = self._make_large_config()
        args = parse_args([])

        times = []
        for _ in range(100):
            start = time_mod.perf_counter()
            resolve_runtime_config(args, config)
            elapsed_ms = (time_mod.perf_counter() - start) * 1000
            times.append(elapsed_ms)

        avg = sum(times) / len(times)
        assert avg < self.DEFAULT_JOURNAL_FAST_PATH_MS, (
            f"Default journal avg {avg:.2f}ms exceeds "
            f"{self.DEFAULT_JOURNAL_FAST_PATH_MS}ms fast-path budget"
        )

    def test_first_call_no_standalone_slowdown(self):
        """Regression: first call shouldn't be 10x slower due to lazy init."""
        config = self._make_large_config()

        first_start = time_mod.perf_counter()
        resolve_runtime_config(parse_args(["journal_025"]), config)
        first_ms = (time_mod.perf_counter() - first_start) * 1000

        rest_times = []
        for i in range(1, 50):
            args = parse_args([f"journal_{i % self.NUM_JOURNALS:03d}"])
            start = time_mod.perf_counter()
            resolve_runtime_config(args, config)
            rest_times.append((time_mod.perf_counter() - start) * 1000)

        avg_rest = sum(rest_times) / len(rest_times)
        ratio = first_ms / avg_rest if avg_rest > 0 else 999

        assert ratio < 5.0, (
            f"First call ({first_ms:.2f}ms) is {ratio:.1f}x slower than "
            f"avg rest ({avg_rest:.2f}ms) — possible lazy-init regression"
        )


class TestConfigErrorFallbackPaths:
    """
    Tests for graceful handling of broken / malformed configurations.
    Covers YAML parse errors and missing environment variables.
    """

    def test_yaml_syntax_error_raises_during_load(self):
        tmpdir = tempfile.mkdtemp(prefix="jrnl_broken_yaml_")
        config_path = os.path.join(tmpdir, "broken.yaml")

        with open(config_path, "w", encoding="utf-8") as f:
            f.write("journals:\n  default: ~/j.txt\n  invalid: [unclosed\n")

        from jrnl.config import load_config

        with pytest.raises(Exception):
            load_config(config_path)

    def test_yaml_empty_file_loads_as_none(self):
        tmpdir = tempfile.mkdtemp(prefix="jrnl_empty_yaml_")
        config_path = os.path.join(tmpdir, "empty.yaml")

        with open(config_path, "w", encoding="utf-8") as f:
            f.write("")

        from jrnl.config import load_config

        result = load_config(config_path)
        assert result is None or result == {}

    def test_yaml_not_a_dict_returns_raw(self):
        tmpdir = tempfile.mkdtemp(prefix="jrnl_scalar_yaml_")
        config_path = os.path.join(tmpdir, "scalar.yaml")

        with open(config_path, "w", encoding="utf-8") as f:
            f.write("just a string\n")

        from jrnl.config import load_config

        result = load_config(config_path)
        assert isinstance(result, str) or result is None

    def test_expand_path_missing_env_var_preserved(self):
        """Missing env vars are kept as-is by os.path.expandvars (not an error)."""
        config = {
            "journals": {
                "default": {"journal": "$NONEXISTENT_VAR_12345/journal.txt"},
            }
        }
        result = expand_config_paths(config)
        assert "$NONEXISTENT_VAR_12345" in result["journals"]["default"]["journal"]

    def test_expand_path_mixed_existing_and_missing_vars(self):
        with mock.patch.dict(os.environ, {"EXISTING_VAR": "/existing/path"}):
            config = {
                "journals": {
                    "default": {
                        "journal": "$EXISTING_VAR/$MISSING_VAR/journal.txt"
                    },
                }
            }
            result = expand_config_paths(config)
            path = result["journals"]["default"]["journal"]
            assert "/existing/path" in path
            assert "$MISSING_VAR" in path

    def test_expand_path_nonexistent_tilde_user(self):
        """~nonexistentuser/path should be preserved by expanduser."""
        import pwd

        try:
            pwd.getpwnam("definitely_no_such_user_xyz")
            user_exists = True
        except KeyError:
            user_exists = False

        if user_exists:
            pytest.skip("Test user unexpectedly exists on this system")

        config = {
            "journals": {
                "default": {"journal": "~definitely_no_such_user_xyz/journal.txt"},
            }
        }
        result = expand_config_paths(config)
        path = result["journals"]["default"]["journal"]
        assert "~definitely_no_such_user_xyz" in path

    def test_resolve_runtime_with_invalid_journal_still_expands_paths(self):
        """Path expansion runs before journal validation."""
        config = {
            "journals": {
                "work": {"journal": "~/work.txt"},
                "notes": {"journal": "$MISSING_VAR/notes.txt"},
            }
        }

        expanded = expand_config_paths(config)
        assert expanded["journals"]["work"]["journal"] == os.path.expanduser(
            "~/work.txt"
        )
        assert "$MISSING_VAR" in expanded["journals"]["notes"]["journal"]

        args = parse_args([])
        with pytest.raises(JrnlException):
            resolve_runtime_config(args, config)

    def test_duplicate_keys_warning_fallback(self):
        """Duplicate YAML keys trigger warning but still load successfully."""
        from jrnl.config import load_config

        tmpdir = tempfile.mkdtemp(prefix="jrnl_dupkeys_")
        config_path = os.path.join(tmpdir, "dupkeys.yaml")

        with open(config_path, "w", encoding="utf-8") as f:
            f.write(
                "journals:\n"
                "  default: ~/first.txt\n"
                "  default: ~/second.txt\n"
            )

        with mock.patch("jrnl.config.print_msg") as mock_print:
            result = load_config(config_path)
            mock_print.assert_called_once()
            assert result is not None
            assert "default" in result["journals"]
