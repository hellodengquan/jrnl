# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import os
from unittest.mock import patch

import pytest

from jrnl.config import ConfigValidator
from jrnl.config import validate_journal_name
from jrnl.config import verify_config_colors
from jrnl.exception import JrnlException
from jrnl.journals.Journal import Journal
from jrnl.messages import Message
from jrnl.messages import MsgStyle
from jrnl.messages import MsgText


class TestValidateAltConfigExists:
    """validate_alt_config_exists: 文件系统层校验 - 致命错误抛出 JrnlException"""

    def test_success_path_existing_file(self, request, tmp_path):
        """成功路径：文件存在时不抛出异常"""
        existing_file = tmp_path / "existing_config.yaml"
        existing_file.write_text("version: 1.0")
        ConfigValidator.validate_alt_config_exists(str(existing_file))

    def test_success_path_existing_directory(self, tmp_path):
        """成功路径：目录存在时也不抛出（路径存在即可，类型由上层检查）"""
        ConfigValidator.validate_alt_config_exists(str(tmp_path))

    def test_failure_path_nonexistent_file_raises(self, tmp_path):
        """失败路径：文件不存在时抛出 JrnlException"""
        nonexistent = tmp_path / "does_not_exist.yaml"
        with pytest.raises(JrnlException) as exc_info:
            ConfigValidator.validate_alt_config_exists(str(nonexistent))

        assert isinstance(exc_info.value, JrnlException)
        assert len(exc_info.value.messages) >= 1
        msg = exc_info.value.messages[0]
        assert msg.text == MsgText.AltConfigNotFound
        assert msg.style == MsgStyle.ERROR
        assert str(nonexistent) in msg.params["config_file"]

    def test_failure_path_empty_string_raises(self):
        """失败路径：空字符串路径抛出 JrnlException"""
        with pytest.raises(JrnlException) as exc_info:
            ConfigValidator.validate_alt_config_exists("")
        assert isinstance(exc_info.value, JrnlException)


class TestValidateConfigNotNone:
    """validate_config_not_none: 解析层校验 - 致命错误抛出 JrnlException"""

    def test_success_path_valid_dict(self):
        """成功路径：非空字典不抛出异常"""
        valid_config = {"version": "1.0", "journals": {"default": {}}}
        ConfigValidator.validate_config_not_none(valid_config, "/path/to/config.yaml")

    def test_success_path_empty_dict(self):
        """成功路径：空字典也不抛出（空字典!=None，结构校验由上层负责）"""
        ConfigValidator.validate_config_not_none({}, "/path/to/config.yaml")

    def test_success_path_list(self):
        """成功路径：非 None 的其他类型也通过（仅检查 None）"""
        ConfigValidator.validate_config_not_none([], "/path/to/config.yaml")

    def test_failure_path_none_raises(self, tmp_path):
        """失败路径：None 抛出 JrnlException（YAML 解析失败场景）"""
        config_path = tmp_path / "empty.yaml"
        with pytest.raises(JrnlException) as exc_info:
            ConfigValidator.validate_config_not_none(None, str(config_path))

        assert isinstance(exc_info.value, JrnlException)
        assert len(exc_info.value.messages) >= 1
        msg = exc_info.value.messages[0]
        assert msg.text == MsgText.CantParseConfigFile
        assert msg.style == MsgStyle.ERROR
        assert str(config_path) in msg.params["config_path"]


class TestValidateJournalName:
    """validate_journal_name: 业务层校验 - 致命错误抛出 JrnlException"""

    @pytest.fixture()
    def config_with_journals(self):
        return {
            "journals": {
                "default": {"journal": "/path/to/default.txt"},
                "work": {"journal": "/path/to/work.txt"},
                "personal": "/path/to/personal.txt",
            }
        }

    def test_success_path_default_journal(self, config_with_journals):
        """成功路径：default journal 存在"""
        ConfigValidator.validate_journal_name("default", config_with_journals)

    def test_success_path_named_journal(self, config_with_journals):
        """成功路径：已命名 journal 存在"""
        ConfigValidator.validate_journal_name("work", config_with_journals)
        ConfigValidator.validate_journal_name("personal", config_with_journals)

    def test_failure_path_missing_journal_raises(self, config_with_journals):
        """失败路径：未配置的 journal 名称抛出 JrnlException"""
        with pytest.raises(JrnlException) as exc_info:
            ConfigValidator.validate_journal_name("nonexistent", config_with_journals)

        assert isinstance(exc_info.value, JrnlException)
        assert len(exc_info.value.messages) >= 1
        msg = exc_info.value.messages[0]
        assert msg.text == MsgText.NoNamedJournal
        assert msg.style == MsgStyle.ERROR
        assert msg.params["journal_name"] == "nonexistent"
        assert "journals" in msg.params

    def test_failure_path_missing_journals_key_raises(self):
        """失败路径：配置缺少 journals 键时抛出"""
        bad_config = {"version": "1.0"}
        with pytest.raises(JrnlException):
            ConfigValidator.validate_journal_name("default", bad_config)


class TestValidateColors:
    """validate_colors: 结构层校验 - 返回警告 list[Message]，不抛出异常"""

    def test_success_path_all_valid_colors(self):
        """成功路径：所有颜色有效，返回空列表"""
        config = {
            "colors": {
                "body": "none",
                "date": "black",
                "tags": "yellow",
                "title": "cyan",
            }
        }
        warnings = ConfigValidator.validate_colors(config)
        assert isinstance(warnings, list)
        assert len(warnings) == 0

    def test_success_path_none_case_insensitive(self):
        """成功路径：NONE/none/None 都视为有效"""
        for none_val in ["NONE", "none", "None", "nOnE"]:
            config = {"colors": {"body": none_val, "date": none_val}}
            warnings = ConfigValidator.validate_colors(config)
            assert len(warnings) == 0

    def test_success_path_missing_colors_key_no_error(self):
        """成功路径：配置中缺少 colors 键时不报错，返回空列表"""
        config = {"version": "1.0", "journals": {}}
        warnings = ConfigValidator.validate_colors(config)
        assert isinstance(warnings, list)
        assert len(warnings) == 0

    def test_failure_path_invalid_color_returns_warnings(self):
        """失败路径：无效颜色返回非空 Message 列表，不抛出异常"""
        config = {
            "colors": {
                "body": "invalid_color_xyz",
                "date": "black",
            }
        }
        warnings = ConfigValidator.validate_colors(config)

        assert isinstance(warnings, list)
        assert len(warnings) == 1
        assert all(isinstance(w, Message) for w in warnings)

        warning = warnings[0]
        assert warning.text == MsgText.InvalidColor
        assert warning.style == MsgStyle.NORMAL
        assert warning.params["key"] == "body"
        assert warning.params["color"] == "invalid_color_xyz"

    def test_failure_path_multiple_invalid_colors(self):
        """失败路径：多个无效颜色全部收集到列表中"""
        config = {
            "colors": {
                "body": "bad1",
                "date": "bad2",
                "tags": "yellow",
                "title": "bad3",
            }
        }
        warnings = ConfigValidator.validate_colors(config)

        assert len(warnings) == 3
        bad_keys = {w.params["key"] for w in warnings}
        assert bad_keys == {"body", "date", "title"}

    def test_failure_path_no_exception_raised(self):
        """验证警告路径不抛出任何异常"""
        config = {"colors": {"body": "totally_bogus"}}
        try:
            result = ConfigValidator.validate_colors(config)
        except Exception as e:
            pytest.fail(f"validate_colors should not raise but got: {e}")
        assert len(result) > 0


class TestValidateJournalEncryptable:
    """validate_journal_encryptable: 业务层校验 - 致命错误抛出 JrnlException"""

    class NonEncryptableJournal:
        """模拟不支持加密的 journal 类型"""
        can_be_encrypted = False

    class EncryptableJournal:
        """模拟支持加密的 journal 类型"""
        can_be_encrypted = True

    class NoAttributeJournal:
        """没有 can_be_encrypted 属性的 journal 类型（默认视为可加密）"""
        pass

    def test_success_path_encryptable_journal(self):
        """成功路径：可加密 journal 不抛出异常"""
        config = {"encrypt": True}
        ConfigValidator.validate_journal_encryptable(
            "my_journal", self.EncryptableJournal, config
        )

    def test_success_path_no_can_be_encrypted_attribute(self):
        """成功路径：缺少 can_be_encrypted 属性时视为可加密（hasattr 检查）"""
        config = {"encrypt": True}
        ConfigValidator.validate_journal_encryptable(
            "my_journal", self.NoAttributeJournal, config
        )

    def test_success_path_real_journal_class(self):
        """成功路径：真实的 Journal 类通过校验"""
        config = {"encrypt": True}
        ConfigValidator.validate_journal_encryptable(
            "my_journal", Journal, config
        )

    def test_failure_path_nonencryptable_raises(self):
        """失败路径：不支持加密的 journal 类型抛出 JrnlException"""
        config = {"encrypt": True}
        with pytest.raises(JrnlException) as exc_info:
            ConfigValidator.validate_journal_encryptable(
                "my_journal", self.NonEncryptableJournal, config
            )

        assert isinstance(exc_info.value, JrnlException)
        assert len(exc_info.value.messages) >= 1
        msg = exc_info.value.messages[0]
        assert msg.text == MsgText.CannotEncryptJournalType
        assert msg.style == MsgStyle.ERROR
        assert msg.params["journal_name"] == "my_journal"
        assert msg.params["journal_type"] == "NonEncryptableJournal"


class TestValidateEditorConfigured:
    """validate_editor_configured: 业务层校验 - 致命错误抛出 JrnlException"""

    def test_success_path_editor_configured(self):
        """成功路径：editor 已配置字符串不抛出"""
        ConfigValidator.validate_editor_configured({"editor": "vim"})

    def test_success_path_editor_with_args(self):
        """成功路径：editor 配置为带参数的命令"""
        ConfigValidator.validate_editor_configured({"editor": "code --wait"})

    def test_failure_path_empty_editor_raises(self):
        """失败路径：editor 为空字符串抛出 JrnlException"""
        with pytest.raises(JrnlException) as exc_info:
            ConfigValidator.validate_editor_configured({"editor": ""})

        assert isinstance(exc_info.value, JrnlException)
        assert len(exc_info.value.messages) >= 1
        msg = exc_info.value.messages[0]
        assert msg.text == MsgText.EditorNotConfigured
        assert msg.style == MsgStyle.ERROR

    def test_failure_path_missing_editor_raises(self):
        """失败路径：配置中缺少 editor 键抛出 JrnlException"""
        with pytest.raises(JrnlException) as exc_info:
            ConfigValidator.validate_editor_configured({})
        assert isinstance(exc_info.value, JrnlException)

    def test_failure_path_none_editor_raises(self):
        """失败路径：editor 为 None 抛出 JrnlException"""
        with pytest.raises(JrnlException):
            ConfigValidator.validate_editor_configured({"editor": None})

    def test_failure_path_empty_dict_raises(self):
        """失败路径：空配置字典抛出"""
        with pytest.raises(JrnlException):
            ConfigValidator.validate_editor_configured({})


class TestValidateJournalEncryptionCompatibility:
    """validate_journal_encryption_compatibility: 业务层校验 - 返回警告，不抛出异常"""

    def test_success_path_file_with_encryption(self):
        """成功路径：文件路径 + 加密 = 兼容，无警告"""
        warnings = ConfigValidator.validate_journal_encryption_compatibility(
            "my_journal", is_dir=False, encrypt=True
        )
        assert isinstance(warnings, list)
        assert len(warnings) == 0

    def test_success_path_dir_without_encryption(self):
        """成功路径：目录路径 + 无加密 = 兼容，无警告"""
        warnings = ConfigValidator.validate_journal_encryption_compatibility(
            "my_journal", is_dir=True, encrypt=False
        )
        assert len(warnings) == 0

    def test_success_path_file_without_encryption(self):
        """成功路径：文件路径 + 无加密 = 兼容，无警告"""
        warnings = ConfigValidator.validate_journal_encryption_compatibility(
            "my_journal", is_dir=False, encrypt=False
        )
        assert len(warnings) == 0

    def test_failure_path_dir_with_encryption_returns_warning(self):
        """失败路径：目录路径 + 有加密 = 不兼容，返回警告 Message，不抛出"""
        warnings = ConfigValidator.validate_journal_encryption_compatibility(
            "folder_journal", is_dir=True, encrypt=True
        )

        assert isinstance(warnings, list)
        assert len(warnings) == 1
        assert all(isinstance(w, Message) for w in warnings)

        warning = warnings[0]
        assert warning.text == MsgText.ConfigEncryptedForUnencryptableJournalType
        assert warning.style == MsgStyle.WARNING
        assert warning.params["journal_name"] == "folder_journal"

    def test_failure_path_truthy_encrypt_value(self):
        """失败路径：encrypt 为真值（如非空字符串）也触发警告"""
        for truthy_val in ["jrnlv2", "password", 1, "true"]:
            warnings = ConfigValidator.validate_journal_encryption_compatibility(
                "my_journal", is_dir=True, encrypt=truthy_val
            )
            assert len(warnings) == 1, f"encrypt={truthy_val!r} should produce warning"

    def test_failure_path_no_exception_raised(self):
        """验证警告路径即使在不兼容时也不抛出异常"""
        try:
            result = ConfigValidator.validate_journal_encryption_compatibility(
                "test", is_dir=True, encrypt=True
            )
        except Exception as e:
            pytest.fail(
                f"validate_journal_encryption_compatibility should not raise but got: {e}"
            )
        assert len(result) > 0


class TestBackwardsCompatibilityDelegation:
    """验证顶层向后兼容函数正确委托给 ConfigValidator"""

    @patch.object(ConfigValidator, "validate_colors_and_print")
    def test_verify_config_colors_delegates(self, mock_validate):
        """verify_config_colors 调用 ConfigValidator.validate_colors_and_print"""
        mock_validate.return_value = True
        config = {"colors": {"body": "none"}}

        result = verify_config_colors(config)

        mock_validate.assert_called_once_with(config)
        assert result is True

    @patch.object(ConfigValidator, "validate_colors_and_print")
    def test_verify_config_colors_delegates_returns_false(self, mock_validate):
        """verify_config_colors 正确传递 False 返回值"""
        mock_validate.return_value = False
        config = {"colors": {"body": "bad_color"}}

        result = verify_config_colors(config)

        mock_validate.assert_called_once_with(config)
        assert result is False

    @patch.object(ConfigValidator, "validate_journal_name")
    def test_validate_journal_name_delegates(self, mock_validate):
        """顶层 validate_journal_name 调用 ConfigValidator.validate_journal_name"""
        config = {"journals": {"default": {}}}

        validate_journal_name("default", config)

        mock_validate.assert_called_once_with("default", config)

    @patch.object(ConfigValidator, "validate_journal_name")
    def test_validate_journal_name_delegates_exception(self, mock_validate):
        """顶层 validate_journal_name 正确传递 JrnlException"""
        mock_validate.side_effect = JrnlException(
            Message(MsgText.NoNamedJournal, MsgStyle.ERROR, {"journal_name": "x", "journals": ""})
        )
        config = {"journals": {"default": {}}}

        with pytest.raises(JrnlException):
            validate_journal_name("x", config)

        mock_validate.assert_called_once_with("x", config)
