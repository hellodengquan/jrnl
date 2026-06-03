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

All postconfig command functions accept a RuntimeContext, which carries both the parsed
CLI arguments and the runtime state (config, journal name, etc.). Preconfig commands
receive only ParsedArgs since no config has been loaded yet.

Also, please note that all (non-builtin) imports should be scoped to each function to
avoid any possible overhead for these standalone commands.
"""

from __future__ import annotations

import logging
import platform
import sys
from typing import TYPE_CHECKING

from jrnl.config import cmd_requires_valid_journal_name
from jrnl.exception import JrnlException
from jrnl.messages import Message
from jrnl.messages import MsgStyle
from jrnl.messages import MsgText
from jrnl.output import print_msg

if TYPE_CHECKING:
    from jrnl.args import ParsedArgs
    from jrnl.controller import RuntimeContext


def preconfig_diagnostic(parsed_args: ParsedArgs) -> None:
    from jrnl import __title__
    from jrnl import __version__

    print(
        f"{__title__}: {__version__}\n"
        f"Python: {sys.version}\n"
        f"OS: {platform.system()} {platform.release()}"
    )


def preconfig_version(parsed_args: ParsedArgs) -> None:
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


def postconfig_list(ctx: RuntimeContext) -> int:
    from jrnl.output import list_journals

    print(list_journals(ctx.config, ctx.args.export))

    return 0


@cmd_requires_valid_journal_name
def postconfig_import(ctx: RuntimeContext) -> int:
    from jrnl.journals import open_journal
    from jrnl.plugins import get_importer

    journal = open_journal(ctx.journal_name, ctx.config)

    format = ctx.args.export if ctx.args.export else "jrnl"

    if (importer := get_importer(format)) is None:
        raise JrnlException(
            Message(
                MsgText.ImporterNotFound,
                MsgStyle.ERROR,
                {"format": format},
            )
        )

    importer.import_(journal, ctx.args.filename)

    return 0


@cmd_requires_valid_journal_name
def postconfig_encrypt(ctx: RuntimeContext) -> int:
    """
    Encrypt a journal in place, or optionally to a new file
    """
    from jrnl.config import update_config
    from jrnl.install import save_config
    from jrnl.journals import open_journal

    journal = open_journal(ctx.journal_name, ctx.config)

    if hasattr(journal, "can_be_encrypted") and not journal.can_be_encrypted:
        raise JrnlException(
            Message(
                MsgText.CannotEncryptJournalType,
                MsgStyle.ERROR,
                {
                    "journal_name": ctx.journal_name,
                    "journal_type": journal.__class__.__name__,
                },
            )
        )

    logging.debug("Clearing encryption method...")

    if journal.config["encrypt"] is True:
        logging.debug("Journal already encrypted. Re-encrypting...")
        print(f"Journal {journal.name} is already encrypted. Create a new password.")
        journal.encryption_method.clear()
    else:
        journal.config["encrypt"] = True
        journal.encryption_method = None

    journal.write(ctx.args.filename)

    print_msg(
        Message(
            MsgText.JournalEncryptedTo,
            MsgStyle.NORMAL,
            {"path": ctx.args.filename or journal.config["journal"]},
        )
    )

    if not ctx.args.filename:
        update_config(
            ctx.original_config, {"encrypt": True}, ctx.journal_name, force_local=True
        )
        save_config(ctx.original_config)

    return 0


@cmd_requires_valid_journal_name
def postconfig_decrypt(ctx: RuntimeContext) -> int:
    """Decrypts to file. If filename is not set, we encrypt the journal file itself."""
    from jrnl.config import update_config
    from jrnl.install import save_config
    from jrnl.journals import open_journal

    journal = open_journal(ctx.journal_name, ctx.config)

    logging.debug("Clearing encryption method...")
    journal.config["encrypt"] = False
    journal.encryption_method = None

    journal.write(ctx.args.filename)
    print_msg(
        Message(
            MsgText.JournalDecryptedTo,
            MsgStyle.NORMAL,
            {"path": ctx.args.filename or journal.config["journal"]},
        )
    )

    if not ctx.args.filename:
        update_config(
            ctx.original_config, {"encrypt": False}, ctx.journal_name, force_local=True
        )
        save_config(ctx.original_config)

    return 0
