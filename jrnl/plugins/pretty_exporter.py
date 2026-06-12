# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

from typing import TYPE_CHECKING

from jrnl.plugins.text_exporter import TextExporter

if TYPE_CHECKING:
    from jrnl.journals import Entry
    from jrnl.journals import Journal


class PrettyExporter(TextExporter):
    """This Exporter can convert entries and journals into pretty printed text."""

    names = ["pretty"]
    extension = "txt"

    @classmethod
    def export_entry(cls, entry: "Entry") -> str:
        """Returns a pretty printed representation of a single entry."""
        return entry.pprint()

    @classmethod
    def export_journal(cls, journal: "Journal") -> str:
        """Returns a pretty printed representation of an entire journal."""
        return journal.pprint()


class ShortExporter(TextExporter):
    """This Exporter can convert entries and journals into short format text."""

    names = ["short"]
    extension = "txt"

    @classmethod
    def export_entry(cls, entry: "Entry") -> str:
        """Returns a short representation of a single entry (title only)."""
        return entry.pprint(short=True)

    @classmethod
    def export_journal(cls, journal: "Journal") -> str:
        """Returns a short representation of an entire journal."""
        return journal.pprint(short=True)
