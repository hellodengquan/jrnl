# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import os
from unittest import mock

import pytest

from jrnl.args import parse_args
from jrnl.config import DEFAULT_JOURNAL_KEY
from jrnl.config import expand_config_paths
from jrnl.config import resolve_display_format
from jrnl.config import resolve_journal_name
from jrnl.config import resolve_runtime_config
from jrnl.config import validate_journal_name
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
