# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import argparse
import os
from argparse import Namespace

import xdg.BaseDirectory
from ruamel.yaml import YAML

from jrnl.exception import JrnlException
from jrnl.messages import Message
from jrnl.messages import MsgStyle
from jrnl.messages import MsgText
from jrnl.output import print_msg
from jrnl.prompt import yesno
from jrnl.search_fields import get_search_fields

VIEWS_FILE = "views.yaml"
XDG_RESOURCE = "jrnl"


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


def save_view(name: str, args: Namespace) -> bool:
    views = load_views()
    filters = extract_search_filters(args)

    if not filters:
        raise JrnlException(
            Message(
                MsgText.EmptyViewNotAllowed,
                MsgStyle.ERROR,
            )
        )

    if name in views:
        if not yesno(
            Message(
                MsgText.OverwriteViewQuestion,
                MsgStyle.PROMPT,
                {"name": name},
            ),
            default=False,
        ):
            return False

    views[name] = filters
    save_views(views)
    return True


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
    for field in get_search_fields():
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


def postconfig_save_view(args: argparse.Namespace, config: dict, **_) -> int:
    saved = save_view(args.save_view, args)
    if saved:
        print_msg(
            Message(
                MsgText.ViewSaved,
                MsgStyle.NORMAL,
                {"name": args.save_view},
            )
        )
    else:
        print_msg(
            Message(
                MsgText.ViewSaveCancelled,
                MsgStyle.NORMAL,
                {"name": args.save_view},
            )
        )
    return 0


def postconfig_delete_view(args: argparse.Namespace, **kwargs) -> int:
    delete_view(args.delete_view)
    print_msg(
        Message(
            MsgText.ViewDeleted,
            MsgStyle.NORMAL,
            {"name": args.delete_view},
        )
    )
    return 0


def postconfig_list_views(args: argparse.Namespace, **kwargs) -> int:
    views = list_views()
    print_msg(Message(MsgText.ViewsListHeader, MsgStyle.NORMAL))

    if not views:
        print("  (no views saved)")
        return 0

    for name in sorted(views.keys()):
        filters = views[name]
        filters_str = ", ".join(f"{k}={v}" for k, v in filters.items())
        print_msg(
            Message(
                MsgText.ViewDetails,
                MsgStyle.NORMAL,
                {"name": name, "filters": filters_str},
            )
        )
    return 0
