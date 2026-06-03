# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import logging
import os
from typing import Any

from jrnl.config import save_config
from jrnl.exception import JrnlException
from jrnl.messages import Message
from jrnl.messages import MsgStyle
from jrnl.messages import MsgText


EXPORT_PROFILES_KEY = "export_profiles"


def get_profiles(config: dict) -> dict:
    return config.get(EXPORT_PROFILES_KEY, {})


def get_profile(original_config: dict, profile_name: str) -> dict:
    profiles = get_profiles(original_config)
    if profile_name not in profiles:
        raise JrnlException(
            Message(
                MsgText.ExportProfileNotFound,
                MsgStyle.ERROR,
                {
                    "profile_name": profile_name,
                    "available_profiles": ", ".join(profiles.keys()) or "none",
                },
            )
        )
    return profiles[profile_name]


def list_profiles(config: dict) -> str:
    profiles = get_profiles(config)
    if not profiles:
        return "No export profiles configured."
    
    result = []
    for name, profile in sorted(profiles.items()):
        result.append(f"\n{name}:")
        for key, value in sorted(profile.items()):
            result.append(f"  {key}: {value}")
    return "\n".join(result)


def save_profile(
    original_config: dict,
    config: dict,
    profile_name: str,
    export_format: str | None = None,
    filename: str | None = None,
    template: str | None = None,
) -> None:
    profile = {}
    
    if export_format:
        profile["format"] = export_format
    if filename:
        profile["filename"] = filename
    if template:
        profile["template"] = template
    
    if not profile:
        raise JrnlException(
            Message(
                MsgText.ExportProfileEmpty,
                MsgStyle.ERROR,
            )
        )
    
    if EXPORT_PROFILES_KEY not in original_config:
        original_config[EXPORT_PROFILES_KEY] = {}
    
    original_config[EXPORT_PROFILES_KEY][profile_name] = profile
    save_config(original_config)
    
    logging.info(f"Saved export profile '{profile_name}': {profile}")


def delete_profile(original_config: dict, config: dict, profile_name: str) -> None:
    profiles = get_profiles(original_config)
    if profile_name not in profiles:
        raise JrnlException(
            Message(
                MsgText.ExportProfileNotFound,
                MsgStyle.ERROR,
                {
                    "profile_name": profile_name,
                    "available_profiles": ", ".join(profiles.keys()) or "none",
                },
            )
        )
    
    del original_config[EXPORT_PROFILES_KEY][profile_name]
    if not original_config[EXPORT_PROFILES_KEY]:
        del original_config[EXPORT_PROFILES_KEY]
    save_config(original_config)
    
    logging.info(f"Deleted export profile '{profile_name}'")


def apply_profile(
    original_config: dict,
    profile_name: str,
    args_export: str | None = None,
    args_filename: str | None = None,
    args_template: str | None = None,
) -> dict[str, Any]:
    profile = get_profile(original_config, profile_name)
    
    result = {
        "export": args_export or profile.get("format"),
        "filename": args_filename or profile.get("filename"),
        "template": args_template or profile.get("template"),
    }
    
    logging.debug(
        f"Applied export profile '{profile_name}': "
        f"format={result['export']}, filename={result['filename']}, template={result['template']}"
    )
    
    return result


def check_path_conflict(path: str) -> None:
    if not path:
        return
    
    if os.path.exists(path):
        if os.path.isdir(path):
            if os.listdir(path):
                raise JrnlException(
                    Message(
                        MsgText.ExportPathConflict,
                        MsgStyle.WARNING,
                        {"path": path},
                    )
                )
        else:
            raise JrnlException(
                Message(
                    MsgText.ExportPathConflict,
                    MsgStyle.WARNING,
                    {"path": path},
                )
            )
