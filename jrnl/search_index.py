# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

"""In-memory search index for fast tag + keyword lookup.

Rebuilt lazily on first access, or explicitly when journal contents change
(e.g. after a tag rename). The index is used by Journal.filter() and by the
rename-tag scan phase.

Index structure:
    _tag_index:   {normalized_tag: set(entry_index)}
    _text_index:  {token: set(entry_index)}            (simple whitespace token)
    _date_index:  {date_iso_string: set(entry_index)}
"""

import logging
from collections import defaultdict
from typing import TYPE_CHECKING

from jrnl.messages import Message
from jrnl.messages import MsgStyle
from jrnl.messages import MsgText
from jrnl.normalization import normalize_tag
from jrnl.output import print_msg

if TYPE_CHECKING:
    from jrnl.journals import Journal


class JournalSearchIndex:
    def __init__(self, journal: "Journal") -> None:
        self.journal = journal
        self._tag_index: dict[str, set[int]] = defaultdict(set)
        self._text_index: dict[str, set[int]] = defaultdict(set)
        self._date_index: dict[str, set[int]] = defaultdict(set)
        self._dirty: bool = True
        self._entry_count_at_build: int = -1

    def mark_dirty(self) -> None:
        """Mark the index as needing a full rebuild (e.g. after bulk import)."""
        self._dirty = True

    def is_dirty(self) -> bool:
        return self._dirty or self._entry_count_at_build != len(self.journal.entries)

    def rebuild(self, verbose: bool = False) -> None:
        """Full rebuild of all index tables from journal.entries."""
        self._tag_index.clear()
        self._text_index.clear()
        self._date_index.clear()

        for idx, entry in enumerate(self.journal.entries):
            for raw_tag in entry.tags:
                norm = normalize_tag(raw_tag)
                self._tag_index[norm].add(idx)

            for token in self._tokenize(entry.title + " " + entry.body):
                if len(token) >= 2:
                    self._text_index[token.lower()].add(idx)

            iso_date = entry.date.strftime("%Y-%m-%d")
            self._date_index[iso_date].add(idx)

        self._dirty = False
        self._entry_count_at_build = len(self.journal.entries)

        if verbose:
            print_msg(
                Message(
                    MsgText.SearchIndexRebuilt,
                    MsgStyle.NORMAL,
                    {
                        "count": len(self.journal.entries),
                        "tags": len(self._tag_index),
                    },
                )
            )

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        import re

        return re.findall(r"\w+", text, flags=re.UNICODE)

    def _ensure_fresh(self) -> None:
        if self.is_dirty():
            self.rebuild()

    # ----- Tag index API ----- #

    def entries_with_tag(self, tag: str) -> set[int]:
        """Return set of entry indices containing the given tag (normalized)."""
        self._ensure_fresh()
        return set(self._tag_index.get(normalize_tag(tag), set()))

    def tag_exists(self, tag: str) -> bool:
        self._ensure_fresh()
        return normalize_tag(tag) in self._tag_index

    def all_tags(self) -> list[tuple[str, int]]:
        """Return [(normalized_tag, count)] sorted by count desc."""
        self._ensure_fresh()
        return sorted(
            ((t, len(indices)) for t, indices in self._tag_index.items()),
            key=lambda x: (-x[1], x[0]),
        )

    def rename_tag_in_index(self, from_tag: str, to_tag: str, affected_indices: set[int] | None = None, verbose: bool = False) -> int:
        """Update the tag index after a tag rename operation.

        If affected_indices is provided, only those entries are re-scanned for
        correctness; otherwise a full index rebuild is performed.

        Returns the number of index entries updated.
        """
        self._ensure_fresh()

        from_norm = normalize_tag(from_tag)
        to_norm = normalize_tag(to_tag)

        if from_norm == to_norm:
            return 0

        if affected_indices is None:
            affected_indices = self._tag_index.pop(from_norm, set())

        if not affected_indices:
            if from_norm in self._tag_index:
                del self._tag_index[from_norm]
            return 0

        count = len(affected_indices)

        if from_norm in self._tag_index:
            remaining = self._tag_index[from_norm] - affected_indices
            if remaining:
                self._tag_index[from_norm] = remaining
            else:
                del self._tag_index[from_norm]

        self._tag_index[to_norm].update(affected_indices)

        if verbose:
            print_msg(
                Message(
                    MsgText.SearchIndexUpdated,
                    MsgStyle.NORMAL,
                    {
                        "from_tag": from_tag,
                        "to_tag": to_tag,
                        "count": count,
                    },
                )
            )

        return count

    # ----- Text index API ----- #

    def entries_with_text(self, token: str) -> set[int]:
        self._ensure_fresh()
        return set(self._text_index.get(token.lower(), set()))

    # ----- Date index API ----- #

    def entries_on_date(self, iso_date: str) -> set[int]:
        self._ensure_fresh()
        return set(self._date_index.get(iso_date, set()))
