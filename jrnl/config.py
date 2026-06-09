# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import argparse
import logging
import os
from typing import Any
from typing import Callable

import colorama
from rich.pretty import pretty_repr
from ruamel.yaml import YAML
from ruamel.yaml import constructor

from jrnl import __version__
from jrnl.exception import JrnlException
from jrnl.messages import Message
from jrnl.messages import MsgStyle
from jrnl.messages import MsgText
from jrnl.output import list_journals
from jrnl.output import print_msg
from jrnl.output import print_msgs
from jrnl.path import get_config_path
from jrnl.path import get_default_journal_path

# Constants
DEFAULT_JOURNAL_KEY = "default"

YAML_SEPARATOR = ": "
YAML_FILE_ENCODING = "utf-8"


class ConfigValidator:
    """集中式配置校验器，统一管理所有配置相关的读取、校验和提示边界。

    职责分层：
    1. 文件系统层校验 - 配置文件路径、存在性、目录占用
    2. 解析层校验 - YAML格式、重复键、空配置
    3. 结构层校验 - 必需字段、颜色值合法性
    4. 业务层校验 - journal名称、加密兼容性、editor配置
    """

    @staticmethod
    def validate_alt_config_exists(alt_config_path: str) -> None:
        """校验替代配置文件路径是否存在。

        Raises:
            JrnlException: 当替代配置文件不存在时
        """
        if not os.path.exists(alt_config_path):
            raise JrnlException(
                Message(
                    MsgText.AltConfigNotFound,
                    MsgStyle.ERROR,
                    {"config_file": alt_config_path},
                )
            )

    @staticmethod
    def validate_config_not_none(config: Any, config_path: str) -> None:
        """校验加载后的配置不为空。

        Raises:
            JrnlException: 当配置为空无法解析时
        """
        if config is None:
            raise JrnlException(
                Message(
                    MsgText.CantParseConfigFile,
                    MsgStyle.ERROR,
                    {"config_path": config_path},
                )
            )

    @staticmethod
    def validate_colors(config: dict) -> list[Message]:
        """校验colors配置中的颜色值是否有效。

        Returns:
            list[Message]: 包含所有颜色校验错误的消息列表（空列表表示全部通过）
        """
        warnings: list[Message] = []
        if "colors" not in config:
            return warnings

        for key, color in config["colors"].items():
            upper_color = color.upper()
            if upper_color == "NONE":
                continue
            if not getattr(colorama.Fore, upper_color, None):
                warnings.append(
                    Message(
                        MsgText.InvalidColor,
                        MsgStyle.NORMAL,
                        {"key": key, "color": color},
                    )
                )
        return warnings

    @staticmethod
    def validate_colors_and_print(config: dict) -> bool:
        """校验颜色配置并打印所有警告信息。

        Returns:
            bool: True表示所有颜色有效，False表示存在无效颜色
        """
        warnings = ConfigValidator.validate_colors(config)
        if warnings:
            print_msgs(warnings)
            return False
        return True

    @staticmethod
    def validate_journal_name(journal_name: str, config: dict) -> None:
        """校验指定名称的journal是否在配置中存在。

        Raises:
            JrnlException: 当journal名称不存在于配置中，或配置缺少journals键时
        """
        if "journals" not in config or journal_name not in config["journals"]:
            raise JrnlException(
                Message(
                    MsgText.NoNamedJournal,
                    MsgStyle.ERROR,
                    {
                        "journal_name": journal_name,
                        "journals": list_journals(config) if "journals" in config else "",
                    },
                ),
            )

    @staticmethod
    def validate_editor_configured(config: dict) -> None:
        """校验是否已配置editor（用于--edit等需要编辑器的场景）。

        Raises:
            JrnlException: 当editor未配置时
        """
        if not config.get("editor"):
            raise JrnlException(
                Message(
                    MsgText.EditorNotConfigured,
                    MsgStyle.ERROR,
                    {"config_file": get_config_path()},
                )
            )

    @staticmethod
    def validate_journal_encryptable(
        journal_name: str, journal_type: type, config: dict
    ) -> None:
        """校验指定类型的journal是否支持加密。

        Raises:
            JrnlException: 当journal类型不支持加密时
        """
        if hasattr(journal_type, "can_be_encrypted") and not journal_type.can_be_encrypted:
            raise JrnlException(
                Message(
                    MsgText.CannotEncryptJournalType,
                    MsgStyle.ERROR,
                    {
                        "journal_name": journal_name,
                        "journal_type": journal_type.__name__,
                    },
                )
            )

    @staticmethod
    def validate_journal_encryption_compatibility(
        journal_name: str, is_dir: bool, encrypt: Any
    ) -> list[Message]:
        """校验journal路径与加密配置的兼容性。
        文件夹类型的journal无法加密，此检查生成警告消息。

        Returns:
            list[Message]: 兼容性警告消息列表
        """
        warnings: list[Message] = []
        if is_dir and encrypt:
            warnings.append(
                Message(
                    MsgText.ConfigEncryptedForUnencryptableJournalType,
                    MsgStyle.WARNING,
                    {"journal_name": journal_name},
                )
            )
        return warnings

    @staticmethod
    def validate_and_print_encryption_compatibility(
        journal_name: str, is_dir: bool, encrypt: Any
    ) -> None:
        """校验加密兼容性并打印警告。"""
        warnings = ConfigValidator.validate_journal_encryption_compatibility(
            journal_name, is_dir, encrypt
        )
        if warnings:
            print_msgs(warnings)

    @staticmethod
    def validate_all_global(config: dict) -> list[Message]:
        """执行所有全局配置校验（不依赖特定journal上下文）。

        包括：颜色校验等。未来可扩展更多全局校验。

        Returns:
            list[Message]: 所有警告/错误消息
        """
        all_warnings: list[Message] = []
        all_warnings.extend(ConfigValidator.validate_colors(config))
        return all_warnings

    @staticmethod
    def validate_all_global_and_print(config: dict) -> bool:
        """执行所有全局校验并打印结果。

        Returns:
            bool: True表示全部通过，False表示存在警告
        """
        warnings = ConfigValidator.validate_all_global(config)
        if warnings:
            print_msgs(warnings)
            return False
        return True


def make_yaml_valid_dict(input: list) -> dict:
    """

    Convert a two-element list of configuration key-value pair into a flat dict.

    The dict is created through the yaml loader, with the assumption that
    "input[0]: input[1]" is valid yaml.

    :param input: list of configuration keys in dot-notation and their respective values
    :type input: list
    :return: A single level dict of the configuration keys in dot-notation and their
        respective desired values
    :rtype: dict
    """

    assert len(input) == 2

    # yaml compatible strings are of the form Key:Value
    yamlstr = YAML_SEPARATOR.join(input)

    runtime_modifications = YAML(typ="safe").load(yamlstr)

    return runtime_modifications


def save_config(config: dict, alt_config_path: str | None = None) -> None:
    """Supply alt_config_path if using an alternate config through --config-file."""
    config["version"] = __version__

    yaml = YAML(typ="safe")
    yaml.default_flow_style = False  # prevents collapsing of tree structure

    with open(
        alt_config_path if alt_config_path else get_config_path(),
        "w",
        encoding=YAML_FILE_ENCODING,
    ) as f:
        yaml.dump(config, f)


def get_default_config() -> dict[str, Any]:
    return {
        "version": __version__,
        "journals": {"default": {"journal": get_default_journal_path()}},
        "editor": os.getenv("VISUAL") or os.getenv("EDITOR") or "",
        "encrypt": False,
        "template": False,
        "default_hour": 9,
        "default_minute": 0,
        "timeformat": "%F %r",
        "tagsymbols": "#@",
        "highlight": True,
        "linewrap": 79,
        "indent_character": "|",
        "colors": {
            "body": "none",
            "date": "none",
            "tags": "none",
            "title": "none",
        },
    }


def get_default_colors() -> dict[str, Any]:
    return {
        "body": "none",
        "date": "black",
        "tags": "yellow",
        "title": "cyan",
    }


def scope_config(config: dict, journal_name: str) -> dict:
    if journal_name not in config["journals"]:
        return config
    config = config.copy()
    journal_conf = config["journals"].get(journal_name)
    if isinstance(journal_conf, dict):
        # We can override the default config on a by-journal basis
        logging.debug(
            "Updating configuration with specific journal overrides:\n%s",
            pretty_repr(journal_conf),
        )
        config.update(journal_conf)
    else:
        # But also just give them a string to point to the journal file
        config["journal"] = journal_conf

    logging.debug("Scoped config:\n%s", pretty_repr(config))
    return config


def verify_config_colors(config: dict) -> bool:
    """
    Ensures the keys set for colors are valid colorama.Fore attributes, or "None"
    :return: True if all keys are set correctly, False otherwise

    保留此函数作为向后兼容的包装，实际逻辑委托给 ConfigValidator。
    """
    return ConfigValidator.validate_colors_and_print(config)


def load_config(config_path: str) -> dict:
    """Tries to load a config file from YAML."""
    try:
        with open(config_path, encoding=YAML_FILE_ENCODING) as f:
            yaml = YAML(typ="safe")
            yaml.allow_duplicate_keys = False
            return yaml.load(f)
    except constructor.DuplicateKeyError as e:
        print_msg(
            Message(
                MsgText.ConfigDoubleKeys,
                MsgStyle.WARNING,
                {
                    "error_message": e,
                },
            )
        )
        with open(config_path, encoding=YAML_FILE_ENCODING) as f:
            yaml = YAML(typ="safe")
            yaml.allow_duplicate_keys = True
            return yaml.load(f)


def is_config_json(config_path: str) -> bool:
    with open(config_path, "r", encoding="utf-8") as f:
        config_file = f.read()
    return config_file.strip().startswith("{")


def update_config(
    config: dict, new_config: dict, scope: str | None, force_local: bool = False
) -> None:
    """Updates a config dict with new values - either global if scope is None
    or config['journals'][scope] is just a string pointing to a journal file,
    or within the scope"""
    if scope and isinstance(config["journals"][scope], dict):
        config["journals"][scope].update(new_config)
    elif scope and force_local:  # Convert to dict
        config["journals"][scope] = {"journal": config["journals"][scope]}
        config["journals"][scope].update(new_config)
    else:
        config.update(new_config)


def get_journal_name(args: argparse.Namespace, config: dict) -> argparse.Namespace:
    args.journal_name = DEFAULT_JOURNAL_KEY

    # The first arg might be a journal name
    if args.text:
        potential_journal_name = args.text[0]
        if potential_journal_name[-1] == ":":
            potential_journal_name = potential_journal_name[0:-1]

        if potential_journal_name in config["journals"]:
            args.journal_name = potential_journal_name
            args.text = args.text[1:]

    logging.debug("Using journal name: %s", args.journal_name)
    return args


def cmd_requires_valid_journal_name(func: Callable) -> Callable:
    def wrapper(args: argparse.Namespace, config: dict, original_config: dict):
        validate_journal_name(args.journal_name, config)
        func(args=args, config=config, original_config=original_config)

    return wrapper


def validate_journal_name(journal_name: str, config: dict) -> None:
    """保留此函数作为向后兼容的包装，实际逻辑委托给 ConfigValidator。"""
    ConfigValidator.validate_journal_name(journal_name, config)
