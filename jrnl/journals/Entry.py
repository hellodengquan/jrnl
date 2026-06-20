# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

from __future__ import annotations

import datetime
import logging
import os
import re
from typing import TYPE_CHECKING

from jrnl.color import colorize
from jrnl.color import highlight_references
from jrnl.color import highlight_tags_with_background_color
from jrnl.output import wrap_with_ansi_colors

if TYPE_CHECKING:
    from .Journal import Journal


class Entry:
    def __init__(
        self,
        journal: "Journal",
        date: datetime.datetime | None = None,
        text: str = "",
        starred: bool = False,
    ):
        self.journal = journal  # Reference to journal mainly to access its config
        self.date = date or datetime.datetime.now()
        self.text = text
        self._title = None
        self._body = None
        self._tags = None
        self._references = None
        self._backlinks = None
        self.starred = starred
        self.modified = False

    @property
    def fulltext(self) -> str:
        return self.title + " " + self.body

    def _parse_text(self):
        raw_text = self.text
        lines = raw_text.splitlines()
        if lines and lines[0].strip().endswith("*"):
            self.starred = True
            raw_text = lines[0].strip("\n *") + "\n" + "\n".join(lines[1:])
        self._title, self._body = split_title(raw_text)
        if self._tags is None:
            self._tags = list(self._parse_tags())
        if self._references is None:
            self._references = list(self._parse_references())

    @staticmethod
    def reference_regex() -> re.Pattern:
        pattern = r"\[\[([^\]]+)\]\]"
        return re.compile(pattern)

    def _parse_references(self) -> set[str]:
        return {
            ref.strip() for ref in re.findall(Entry.reference_regex(), self.text)
        }

    @property
    def title(self) -> str:
        if self._title is None:
            self._parse_text()
        return self._title

    @title.setter
    def title(self, x: str):
        self._title = x

    @property
    def body(self) -> str:
        if self._body is None:
            self._parse_text()
        return self._body

    @body.setter
    def body(self, x: str):
        self._body = x

    @property
    def tags(self) -> list[str]:
        if self._tags is None:
            self._parse_text()
        return self._tags

    @tags.setter
    def tags(self, x: list[str]):
        self._tags = x

    @property
    def references(self) -> list[str]:
        if self._references is None:
            self._parse_text()
        return self._references

    @references.setter
    def references(self, x: list[str]):
        self._references = x

    @property
    def backlinks(self) -> list["Entry"]:
        if self._backlinks is None:
            self._backlinks = []
        return self._backlinks

    @backlinks.setter
    def backlinks(self, x: list["Entry"]):
        self._backlinks = x

    @staticmethod
    def tag_regex(tagsymbols: str) -> re.Pattern:
        pattern = rf"(?<!\S)([{tagsymbols}][-+*#/\w]+)"
        return re.compile(pattern)

    def _parse_tags(self) -> set[str]:
        tagsymbols = self.journal.config["tagsymbols"]
        return {
            tag.lower() for tag in re.findall(Entry.tag_regex(tagsymbols), self.text)
        }

    def __str__(self):
        """Returns string representation of the entry to be written to journal file."""
        date_str = self.date.strftime(self.journal.config["timeformat"])
        title = "[{}] {}".format(date_str, self.title.rstrip("\n "))
        if self.starred:
            title += " *"
        return "{title}{sep}{body}\n".format(
            title=title,
            sep="\n" if self.body.rstrip("\n ") else "",
            body=self.body.rstrip("\n "),
        )

    def pprint(self, short: bool = False) -> str:
        """Returns a pretty-printed version of the entry.
        If short is true, only print the title."""
        # Handle indentation
        if self.journal.config["indent_character"]:
            indent = self.journal.config["indent_character"].rstrip() + " "
        else:
            indent = ""

        date_str = colorize(
            self.date.strftime(self.journal.config["timeformat"]),
            self.journal.config["colors"]["date"],
            bold=True,
        )

        # Get references display
        references_info = ""
        backlinks_info = ""
        display_references = self.journal.config.get("display_references", True)

        if not short and display_references:
            references_info = self._format_references()
            backlinks_info = self._format_backlinks()

        if not short and self.journal.config["linewrap"]:
            columns = self.journal.config["linewrap"]

            if columns == "auto":
                try:
                    columns = os.get_terminal_size().columns
                except OSError:
                    logging.debug(
                        "Can't determine terminal size automatically 'linewrap': '%s'",
                        self.journal.config["linewrap"],
                    )
                    columns = 79

            # Color date / title and bold title
            title_text = highlight_tags_with_background_color(
                self,
                self.title,
                self.journal.config["colors"]["title"],
                is_title=True,
            )
            title_text = highlight_references(
                self, title_text, self.journal.config["colors"]["title"], is_title=True
            )
            title = wrap_with_ansi_colors(date_str + " " + title_text, columns)

            body = highlight_tags_with_background_color(
                self, self.body.rstrip(" \n"), self.journal.config["colors"]["body"]
            )
            body = highlight_references(
                self, body, self.journal.config["colors"]["body"]
            )

            body = wrap_with_ansi_colors(body, columns - len(indent))
            if indent:
                # Without explicitly colorizing the indent character, it will lose its
                # color after a tag appears.
                body = "\n".join(
                    colorize(indent, self.journal.config["colors"]["body"]) + line
                    for line in body.splitlines()
                )

            body = colorize(body, self.journal.config["colors"]["body"])

            if references_info:
                references_info = wrap_with_ansi_colors(references_info, columns)
            if backlinks_info:
                backlinks_info = wrap_with_ansi_colors(backlinks_info, columns)
        else:
            title_text = highlight_tags_with_background_color(
                self,
                self.title.rstrip("\n"),
                self.journal.config["colors"]["title"],
                is_title=True,
            )
            title_text = highlight_references(
                self, title_text, self.journal.config["colors"]["title"], is_title=True
            )
            title = date_str + " " + title_text

            body = highlight_tags_with_background_color(
                self, self.body.rstrip("\n "), self.journal.config["colors"]["body"]
            )
            body = highlight_references(
                self, body, self.journal.config["colors"]["body"]
            )

        # Suppress bodies that are just blanks and new lines.
        has_body = len(self.body) > 20 or not all(
            char in (" ", "\n") for char in self.body
        )

        if short:
            return title
        else:
            result = "{title}{sep}{body}".format(
                title=title, sep="\n" if has_body else "", body=body if has_body else ""
            )
            if references_info:
                result += "\n" + references_info
            if backlinks_info:
                result += "\n" + backlinks_info
            return result + "\n"

    def _format_references(self, plain: bool = False) -> str:
        """Formats outgoing references for display.

        Args:
            plain: If True, return text without ANSI colors.
        """
        if not self.references:
            return ""

        ref_color = self.journal.config["colors"].get("references", "blue")
        resolved_refs = []
        for ref_text in self.references:
            target = self.journal.find_entry_by_reference(ref_text, self)
            if target:
                target_date = target.date.strftime(self.journal.config["timeformat"])
                target_title = target.title.strip()
                text = f"→ [{target_date}] {target_title}"
                label = text if plain else colorize(text, ref_color)
            else:
                text = f"→ [[{ref_text}]]"
                label = text if plain else colorize(text, "red")
            resolved_refs.append(label)

        if not resolved_refs:
            return ""

        indent_char = self.journal.config["indent_character"]
        indent = indent_char.rstrip() + " " if indent_char else ""
        header_text = "References:"
        header = header_text if plain else colorize(header_text, ref_color, bold=True)
        lines = [header] + [indent + ref for ref in resolved_refs]
        return "\n".join(lines)

    def _format_backlinks(self, plain: bool = False) -> str:
        """Formats incoming backlinks for display.

        Args:
            plain: If True, return text without ANSI colors.
        """
        if not self.backlinks:
            return ""

        backlink_color = self.journal.config["colors"].get("backlinks", "magenta")
        resolved_backlinks = []
        for source in self.backlinks:
            source_date = source.date.strftime(self.journal.config["timeformat"])
            source_title = source.title.strip()
            text = f"← [{source_date}] {source_title}"
            label = text if plain else colorize(text, backlink_color)
            resolved_backlinks.append(label)

        if not resolved_backlinks:
            return ""

        indent_char = self.journal.config["indent_character"]
        indent = indent_char.rstrip() + " " if indent_char else ""
        header_text = "Backlinks:"
        header = header_text if plain else colorize(
            header_text, backlink_color, bold=True
        )
        lines = [header] + [indent + bl for bl in resolved_backlinks]
        return "\n".join(lines)

    def __repr__(self):
        return "<Entry '{}' on {}>".format(
            self.title.strip(), self.date.strftime("%Y-%m-%d %H:%M")
        )

    def __hash__(self):
        return hash(self.__repr__())

    def __eq__(self, other: "Entry"):
        if (
            not isinstance(other, Entry)
            or self.title.strip() != other.title.strip()
            or self.body.rstrip() != other.body.rstrip()
            or self.date != other.date
            or self.starred != other.starred
        ):
            return False
        return True

    def __ne__(self, other: "Entry"):
        return not self.__eq__(other)


# Based on Segtok by Florian Leitner
# https://github.com/fnl/segtok
SENTENCE_SPLITTER = re.compile(
    r"""
    (
    [.!?\u2026\u203C\u203D\u2047\u2048\u2049\u22EF\uFE52\uFE57] # Sequence starting with a sentence terminal,
    [\'\u2019\"\u201D]? # an optional right quote,
    [\]\)]*             # optional closing bracket
    \s+                 # AND a sequence of required spaces.
    )
    |[\uFF01\uFF0E\uFF1F\uFF61\u3002] # CJK full/half width terminals usually do not have following spaces.
    """,  # noqa: E501
    re.VERBOSE,
)

SENTENCE_SPLITTER_ONLY_NEWLINE = re.compile("\n")


def split_title(text: str) -> tuple[str, str]:
    """Splits the first sentence off from a text."""
    sep = SENTENCE_SPLITTER_ONLY_NEWLINE.search(text.lstrip())
    if not sep:
        sep = SENTENCE_SPLITTER.search(text)
        if not sep:
            return text, ""
    return text[: sep.end()].strip(), text[sep.end() :].strip()
