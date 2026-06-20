# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

from unittest import mock

from jrnl.args import parse_args
from jrnl.commands import postconfig_check_config
from jrnl.config import apply_missing_defaults
from jrnl.config import check_config_integrity
from jrnl.config import format_missing_path
from jrnl.config import get_default_config


class TestCheckConfigIntegrity:
    def test_full_config_has_no_missing(self):
        config = get_default_config()
        missing = check_config_integrity(config)
        assert missing == []

    def test_missing_top_level_fields_detected(self):
        config = {"version": "1.0", "journals": {"default": {"journal": "/tmp/test"}}}
        missing = check_config_integrity(config)
        paths = [format_missing_path(m["path"]) for m in missing]
        assert "editor" in paths
        assert "encrypt" in paths
        assert "highlight" in paths
        assert "linewrap" in paths
        assert "tagsymbols" in paths

    def test_missing_nested_colors_detected(self):
        config = get_default_config()
        config["colors"] = {"body": "none"}
        missing = check_config_integrity(config)
        paths = [format_missing_path(m["path"]) for m in missing]
        assert "colors.date" in paths
        assert "colors.tags" in paths
        assert "colors.title" in paths
        assert "colors.body" not in paths

    def test_missing_colors_dict_entirely(self):
        config = get_default_config()
        del config["colors"]
        missing = check_config_integrity(config)
        paths = [format_missing_path(m["path"]) for m in missing]
        assert "colors" in paths

    def test_deeply_nested_missing_detected(self):
        from jrnl.config import _recursive_check_integrity

        default_node = {"a": {"b": {"c": {"d": 1, "e": 2}}}}
        config_node = {"a": {"b": {"c": {"d": 1}}}}
        result = []
        _recursive_check_integrity(default_node, config_node, (), result, set())
        paths = [format_missing_path(r["path"]) for r in result]
        assert "a.b.c.e" in paths

    def test_dynamic_journals_keys_are_skipped(self):
        config = {
            "version": "1.0",
            "journals": {"work": "/tmp/work", "personal": "/tmp/personal"},
        }
        missing = check_config_integrity(config)
        paths = [format_missing_path(m["path"]) for m in missing]
        assert not any(p.startswith("journals.") for p in paths)

    def test_skip_keys_parameter_controls_skipping(self):
        config = {"colors": {"body": "none"}}
        missing_without_skip = check_config_integrity(config, skip_keys=set())
        paths_no_skip = [format_missing_path(m["path"]) for m in missing_without_skip]
        assert "colors.date" in paths_no_skip
        assert "colors.tags" in paths_no_skip

    def test_default_values_included_in_result(self):
        config = {"version": "1.0", "journals": {}}
        missing = check_config_integrity(config)
        by_path = {format_missing_path(m["path"]): m["default_value"] for m in missing}
        assert by_path["encrypt"] is False
        assert by_path["highlight"] is True
        assert by_path["linewrap"] == 79

    def test_colors_default_values_nested(self):
        config = get_default_config()
        config["colors"] = {}
        missing = check_config_integrity(config)
        by_path = {format_missing_path(m["path"]): m["default_value"] for m in missing}
        assert by_path["colors.body"] == "none"
        assert by_path["colors.date"] == "none"
        assert by_path["colors.tags"] == "none"
        assert by_path["colors.title"] == "none"


class TestFormatMissingPath:
    def test_single_key(self):
        assert format_missing_path(("editor",)) == "editor"

    def test_two_keys(self):
        assert format_missing_path(("colors", "title")) == "colors.title"

    def test_three_keys(self):
        assert format_missing_path(("a", "b", "c")) == "a.b.c"

    def test_empty_tuple(self):
        assert format_missing_path(()) == ""


class TestApplyMissingDefaults:
    def test_fills_top_level_missing(self):
        config = {"version": "1.0", "journals": {}}
        missing = check_config_integrity(config)
        apply_missing_defaults(config, missing)
        missing_after = check_config_integrity(config)
        assert missing_after == []

    def test_fills_nested_missing(self):
        config = get_default_config()
        config["colors"] = {"body": "red"}
        missing = check_config_integrity(config)
        apply_missing_defaults(config, missing)
        assert config["colors"]["date"] == "none"
        assert config["colors"]["tags"] == "none"
        assert config["colors"]["title"] == "none"
        assert config["colors"]["body"] == "red"

    def test_creates_parent_dict_for_nested_missing(self):
        config = {"version": "1.0", "journals": {}}
        missing = check_config_integrity(config)
        apply_missing_defaults(config, missing)
        assert isinstance(config["colors"], dict)
        assert config["colors"]["body"] == "none"
        assert config["colors"]["date"] == "none"

    def test_preserves_existing_values(self):
        config = get_default_config()
        config["linewrap"] = 100
        config["colors"]["title"] = "magenta"
        missing = check_config_integrity(config)
        apply_missing_defaults(config, missing)
        assert config["linewrap"] == 100
        assert config["colors"]["title"] == "magenta"


class TestPostconfigCheckConfig:
    def test_returns_zero_when_config_complete(self):
        args = parse_args([])
        config = get_default_config()
        exit_code = postconfig_check_config(
            args=args, config=config, original_config=config.copy()
        )
        assert exit_code == 0

    def test_returns_nonzero_when_missing_fields(self):
        args = parse_args([])
        config = {"version": "1.0", "journals": {"default": {"journal": "/tmp"}}}
        exit_code = postconfig_check_config(
            args=args, config=config, original_config=config.copy()
        )
        assert exit_code == 1

    def test_returns_nonzero_when_nested_missing(self):
        args = parse_args([])
        config = get_default_config()
        config["colors"] = {"body": "none"}
        exit_code = postconfig_check_config(
            args=args, config=config, original_config=config.copy()
        )
        assert exit_code == 1

    @mock.patch("jrnl.commands.print_msg")
    def test_prints_all_present_message_when_no_missing(self, mock_print):
        args = parse_args([])
        config = get_default_config()
        exit_code = postconfig_check_config(
            args=args, config=config, original_config=config.copy()
        )
        assert exit_code == 0
        calls = [str(c.args[0].text) for c in mock_print.call_args_list]
        assert any("All configuration fields are present" in c for c in calls)


class TestCheckConfigCommandLineArg:
    def test_check_config_registers_postconfig_cmd(self):
        args = parse_args(["--check-config"])
        assert args.postconfig_cmd is postconfig_check_config
