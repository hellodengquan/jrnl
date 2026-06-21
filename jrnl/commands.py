# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

"""
Functions in this file are standalone commands. All standalone commands are split into
two categories depending on whether they require the config to be loaded to be able to
run.

1. "preconfig" commands don't require the config at all, and can be run before the
   config has been loaded.
2. "postconfig" commands require to config to have already been loaded, parsed, and
   scoped before they can be run.

Also, please note that all (non-builtin) imports should be scoped to each function to
avoid any possible overhead for these standalone commands.
"""

import argparse
import logging
import platform
import sys

from jrnl.config import cmd_requires_valid_journal_name
from jrnl.exception import JrnlException
from jrnl.messages import Message
from jrnl.messages import MsgStyle
from jrnl.messages import MsgText
from jrnl.output import print_msg


def preconfig_diagnostic(_) -> None:
    from jrnl import __title__
    from jrnl import __version__

    print(
        f"{__title__}: {__version__}\n"
        f"Python: {sys.version}\n"
        f"OS: {platform.system()} {platform.release()}"
    )


def preconfig_version(_) -> None:
    import textwrap

    from jrnl import __title__
    from jrnl import __version__

    output = f"""
    {__title__} {__version__}

    Copyright © 2012-2023 jrnl contributors

    This is free software, and you are welcome to redistribute it under certain
    conditions; for details, see: https://www.gnu.org/licenses/gpl-3.0.html
    """

    output = textwrap.dedent(output).strip()

    print(output)


def postconfig_list(args: argparse.Namespace, config: dict, **_) -> int:
    from jrnl.output import list_journals

    print(list_journals(config, args.export))

    return 0


@cmd_requires_valid_journal_name
def postconfig_formalize(
    args: argparse.Namespace, config: dict, **_
) -> int:
    """Standalone command: promote ALL drafts in the selected journal.

    Unlike ``--formalize`` / ``--archive`` (which act on filtered search
    results and require interactive confirmation), ``--formalize-drafts`` is
    a standalone postconfig command that:

      1. Opens the selected journal (scoped from args, default or named).
      2. Collects every entry where ``entry.draft is True`` - i.e. the full
         inbox collection, ignoring any search filters.
      3. Calls :meth:`Journal.formalize_entries` which clears draft status
         and marks entries as modified.
      4. Persists the change to disk via :meth:`Journal.write`.

    **Which journal do entries get archived to?**

    Entries are **always archived in-place in their source journal**.
    There is no "archive journal" — "archiving" is a status change, not a
    file move. In a multi-journal setup (e.g. ``work``, ``personal``,
    ``ideas``), ``jrnl work --formalize-drafts`` only touches the
    ``work`` journal; the ``personal`` and ``ideas`` journals are
    untouched.

    Concretely, the promoted entry stays in the same file(s) it was
    read from:

    *   For a plain Journal: the single text file at
        ``config['journal']`` (e.g. ``~/.local/share/jrnl/journal.txt``).
    *   For a Folder Journal: the per-day ``.txt`` files under
        ``<journal_dir>/YYYY/MM/DD.txt``.
    *   For a DayOne Journal: the ``.doentry`` plist files inside the
        DayOne bundle.

    The only difference is that the ``!`` draft suffix is no longer
    written to disk, so the entries will no longer appear in ``--draft``
    / ``--inbox`` views - that is what "archived" means in jrnl's model.
    """
    from jrnl.journals import open_journal

    journal = open_journal(args.journal_name, config)

    draft_entries = [e for e in journal.entries if e.draft]
    if not draft_entries:
        print_msg(Message(MsgText.NothingToFormalize, MsgStyle.WARNING))
        return 0

    journal.formalize_entries(draft_entries)
    journal.write()

    count = len(draft_entries)
    msg_text = (
        MsgText.EntryFormalizedSingular
        if count == 1
        else MsgText.EntryFormalizedPlural
    )
    print_msg(Message(msg_text, MsgStyle.NORMAL, {"num": count}))

    return 0


@cmd_requires_valid_journal_name
def postconfig_import(args: argparse.Namespace, config: dict, **_) -> int:
    from jrnl.journals import open_journal
    from jrnl.plugins import get_importer

    # Requires opening the journal
    journal = open_journal(args.journal_name, config)

    format = args.export if args.export else "jrnl"

    if (importer := get_importer(format)) is None:
        raise JrnlException(
            Message(
                MsgText.ImporterNotFound,
                MsgStyle.ERROR,
                {"format": format},
            )
        )

    importer.import_(journal, args.filename)

    return 0


@cmd_requires_valid_journal_name
def postconfig_encrypt(
    args: argparse.Namespace, config: dict, original_config: dict
) -> int:
    """
    Encrypt a journal in place, or optionally to a new file
    """
    from jrnl.config import update_config
    from jrnl.install import save_config
    from jrnl.journals import open_journal

    # Open the journal
    journal = open_journal(args.journal_name, config)

    if hasattr(journal, "can_be_encrypted") and not journal.can_be_encrypted:
        raise JrnlException(
            Message(
                MsgText.CannotEncryptJournalType,
                MsgStyle.ERROR,
                {
                    "journal_name": args.journal_name,
                    "journal_type": journal.__class__.__name__,
                },
            )
        )

    # If journal is encrypted, create new password
    logging.debug("Clearing encryption method...")

    if journal.config["encrypt"] is True:
        logging.debug("Journal already encrypted. Re-encrypting...")
        print(f"Journal {journal.name} is already encrypted. Create a new password.")
        journal.encryption_method.clear()
    else:
        journal.config["encrypt"] = True
        journal.encryption_method = None

    journal.write(args.filename)

    print_msg(
        Message(
            MsgText.JournalEncryptedTo,
            MsgStyle.NORMAL,
            {"path": args.filename or journal.config["journal"]},
        )
    )

    # Update the config, if we encrypted in place
    if not args.filename:
        update_config(
            original_config, {"encrypt": True}, args.journal_name, force_local=True
        )
        save_config(original_config)

    return 0


@cmd_requires_valid_journal_name
def postconfig_decrypt(
    args: argparse.Namespace, config: dict, original_config: dict
) -> int:
    """Decrypts to file. If filename is not set, we encrypt the journal file itself."""
    from jrnl.config import update_config
    from jrnl.install import save_config
    from jrnl.journals import open_journal

    journal = open_journal(args.journal_name, config)

    logging.debug("Clearing encryption method...")
    journal.config["encrypt"] = False
    journal.encryption_method = None

    journal.write(args.filename)
    print_msg(
        Message(
            MsgText.JournalDecryptedTo,
            MsgStyle.NORMAL,
            {"path": args.filename or journal.config["journal"]},
        )
    )

    # Update the config, if we decrypted in place
    if not args.filename:
        update_config(
            original_config, {"encrypt": False}, args.journal_name, force_local=True
        )
        save_config(original_config)

    return 0
