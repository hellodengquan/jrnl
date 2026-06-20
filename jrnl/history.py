# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

"""Undo/redo history for journal operations.

Every mutating journal operation (tag rename, entry edit, import, delete...)
should record a HistoryEntry that can undo/redo the change.
"""

import logging
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import Callable
from typing import Optional

from jrnl.messages import Message
from jrnl.messages import MsgStyle
from jrnl.messages import MsgText
from jrnl.output import print_msg


@dataclass
class HistoryEntry:
    """A single undoable/redoable operation on a journal."""

    operation: str
    description: str
    entry_count: int

    undo_fn: Callable[[], None]
    redo_fn: Callable[[], None]

    metadata: dict[str, Any] = field(default_factory=dict)

    def undo(self) -> None:
        logging.debug(f"Undo: {self.operation} ({self.entry_count} entries)")
        self.undo_fn()
        print_msg(
            Message(
                MsgText.UndoOperation,
                MsgStyle.NORMAL,
                {"operation": self.description, "entries": self.entry_count},
            )
        )

    def redo(self) -> None:
        logging.debug(f"Redo: {self.operation} ({self.entry_count} entries)")
        self.redo_fn()
        print_msg(
            Message(
                MsgText.RedoOperation,
                MsgStyle.NORMAL,
                {"operation": self.description, "entries": self.entry_count},
            )
        )


class JournalHistory:
    """Dual-stack undo/redo manager bound to a single Journal instance.

    - undo_stack: list of HistoryEntry ready to be undone (oldest first)
    - redo_stack: list of HistoryEntry ready to be redone (oldest first)
    - New pushes to undo_stack clear redo_stack (divergent history)
    """

    DEFAULT_MAX_UNDO = 50

    def __init__(self, max_undo: int = DEFAULT_MAX_UNDO) -> None:
        self._undo_stack: list[HistoryEntry] = []
        self._redo_stack: list[HistoryEntry] = []
        self._max_undo = max_undo

    @property
    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    @property
    def undo_count(self) -> int:
        return len(self._undo_stack)

    @property
    def redo_count(self) -> int:
        return len(self._redo_stack)

    def push(self, entry: HistoryEntry) -> None:
        """Record a new operation. Clears any redo history (standard UX)."""
        while len(self._undo_stack) >= self._max_undo:
            discarded = self._undo_stack.pop(0)
            logging.debug(
                f"Undo stack full, discarding oldest: {discarded.operation}"
            )
            print_msg(
                Message(
                    MsgText.UndoStackFull,
                    MsgStyle.WARNING,
                    {"max_undo": self._max_undo},
                )
            )
        self._undo_stack.append(entry)
        self._redo_stack.clear()

    def undo(self) -> bool:
        """Pop latest undo, apply it, push onto redo stack."""
        if not self._undo_stack:
            print_msg(Message(MsgText.UndoStackEmpty, MsgStyle.WARNING))
            return False

        entry = self._undo_stack.pop()
        try:
            entry.undo()
        except Exception as e:
            logging.error(f"Undo failed for {entry.operation}: {e}")
            self._undo_stack.append(entry)
            raise
        self._redo_stack.append(entry)
        return True

    def redo(self) -> bool:
        """Pop latest redo, apply it, push onto undo stack."""
        if not self._redo_stack:
            print_msg(Message(MsgText.RedoStackEmpty, MsgStyle.WARNING))
            return False

        entry = self._redo_stack.pop()
        try:
            entry.redo()
        except Exception as e:
            logging.error(f"Redo failed for {entry.operation}: {e}")
            self._redo_stack.append(entry)
            raise
        self._undo_stack.append(entry)
        return True

    def peek_undo(self) -> Optional[HistoryEntry]:
        return self._undo_stack[-1] if self._undo_stack else None

    def peek_redo(self) -> Optional[HistoryEntry]:
        return self._redo_stack[-1] if self._redo_stack else None

    def pop_last(self, n: int = 1) -> int:
        """Discard the last n entries from the undo stack *without* applying
        their undo functions. Used when a mutation happened in-memory but
        was rolled back (or failed to write), so the corresponding history
        entries must not remain.

        Returns the number of entries actually removed.
        """
        if n <= 0:
            return 0
        n = min(n, len(self._undo_stack))
        if n == 0:
            return 0
        removed = self._undo_stack[-n:]
        self._undo_stack[-n:] = []
        # Pop invalidates redo (caller is effectively rewriting the tail of
        # history); stay consistent with push() semantics.
        self._redo_stack.clear()
        logging.debug(
            f"Popped {n} history entries (ops: "
            f"{', '.join(e.operation for e in removed)})"
        )
        return n

    def clear(self) -> None:
        self._undo_stack.clear()
        self._redo_stack.clear()
        print_msg(Message(MsgText.UndoHistoryPurged, MsgStyle.NORMAL))

    def __len__(self) -> int:
        return len(self._undo_stack)

    def __repr__(self) -> str:
        return (
            f"JournalHistory(undo={len(self._undo_stack)}, "
            f"redo={len(self._redo_stack)}, max={self._max_undo})"
        )
