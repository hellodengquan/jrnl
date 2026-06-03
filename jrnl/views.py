# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import os
from argparse import Namespace
from pathlib import Path

import xdg.BaseDirectory
from ruamel.yaml import YAML

from jrnl.exception import JrnlException
from jrnl.messages import Message
from jrnl.messages import MsgStyle
from jrnl.messages import MsgText

VIEWS_FILE = "views.yaml"
XDG_RESOURCE = "jrnl"

SEARCH_FIELDS = [
    "contains",
    "tagged",
    "excluded",
    "exclude_starred",
    "exclude_tagged",
    "end_date",
    "today_in_history",
    "month",
    "day",
    "year",
    "limit",
    "on_date",
    "starred",
    "start_date",
    "strict",
    "text",
]


def get_views_path() -> str:
    views_data_path = xdg.BaseDirectory.save_data_path(XDG_RESOURCE)
    return os.path.join(views_data_path, VIEWS_FILE)


def load_views() -> dict:
    views_path = get_views_path()
    if not os.path.exists(views_path):
        return {}
    try:
        with open(views_path, "r", encoding="utf-8") as f:
            yaml = YAML(typ="safe")
            data = yaml.load(f)
            return data if isinstance(data, dict) else {}
    except Exception as e:
        raise JrnlException(
            Message(
                MsgText.ViewsFileCorrupted,
                MsgStyle.ERROR,
                {"error": str(e)},
            )
        )


def save_views(views: dict) -> None:
    views_path = get_views_path()
    yaml = YAML(typ="safe")
    yaml.default_flow_style = False
    with open(views_path, "w", encoding="utf-8") as f:
        yaml.dump(views, f)


def save_view(name: str, args: Namespace) -> None:
    views = load_views()
    filters = extract_search_filters(args)

    if not filters:
        raise JrnlException(
            Message(
                MsgText.EmptyViewNotAllowed,
                MsgStyle.ERROR,
            )
        )

    views[name] = filters
    save_views(views)


def delete_view(name: str) -> None:
    views = load_views()
    if name not in views:
        raise JrnlException(
            Message(
                MsgText.ViewNotFound,
                MsgStyle.ERROR,
                {"name": name, "available_views": list_views_str(views)},
            )
        )
    del views[name]
    save_views(views)


def apply_view(name: str, args: Namespace) -> None:
    views = load_views()
    if name not in views:
        raise JrnlException(
            Message(
                MsgText.ViewNotFound,
                MsgStyle.ERROR,
                {"name": name, "available_views": list_views_str(views)},
            )
        )

    view_filters = views[name]
    if not view_filters:
        raise JrnlException(
            Message(
                MsgText.InvalidView,
                MsgStyle.ERROR,
                {"name": name},
            )
        )

    for key, value in view_filters.items():
        if value is not None and value is not False:
            setattr(args, key, value)


def extract_search_filters(args: Namespace) -> dict:
    filters = {}
    for field in SEARCH_FIELDS:
        value = getattr(args, field, None)
        if value is not None and value is not False and value != []:
            filters[field] = value
    return filters


def list_views() -> dict:
    return load_views()


def list_views_str(views: dict) -> str:
    if not views:
        return "  (no views saved)"
    return "\n".join(f"  {name}" for name in sorted(views.keys()))
