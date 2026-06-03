# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

_fields: list[str] = []


def register(dest: str) -> None:
    _fields.append(dest)


def get_search_fields() -> list[str]:
    return list(_fields)
