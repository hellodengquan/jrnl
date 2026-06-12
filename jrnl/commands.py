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
import os
import platform
import shutil
import sys

from jrnl.config import cmd_requires_valid_journal_name
from jrnl.exception import JrnlException
from jrnl.messages import Message
from jrnl.messages import MsgStyle
from jrnl.messages import MsgText
from jrnl.os_compat import split_args
from jrnl.output import print_msg
from jrnl.path import absolute_path
from jrnl.path import get_templates_path


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


def postconfig_doctor(args: argparse.Namespace, config: dict, **_) -> int:
    """
    Perform a health check on the jrnl configuration.
    Checks journal path, editor, encryption dependencies, and template configuration.
    """
    from rich.console import Console
    from rich.table import Table

    console = Console()

    ok_count = 0
    warning_count = 0
    error_count = 0

    console.print(f"\n[bold cyan]{MsgText.DoctorTitle.value}[/bold cyan]\n")

    # Check journal path
    table = Table(show_header=False, box=None, padding=(0, 1))
    console.print(f"[bold]{MsgText.DoctorSectionJournal.value}[/bold]")

    journal_path = absolute_path(config["journal"])
    path_ok, path_msg, path_suggestion = _check_journal_path(journal_path)

    if path_ok == "ok":
        ok_count += 1
        status = f"[green]{MsgText.DoctorOK.value}[/green]"
    elif path_ok == "warning":
        warning_count += 1
        status = f"[yellow]{MsgText.DoctorWarning.value}[/yellow]"
    else:
        error_count += 1
        status = f"[red]{MsgText.DoctorError.value}[/red]"

    table.add_row(status, path_msg)
    if path_suggestion:
        table.add_row("", f"[dim]{path_suggestion}[/dim]")
    console.print(table)

    # Check editor
    table = Table(show_header=False, box=None, padding=(0, 1))
    console.print(f"\n[bold]{MsgText.DoctorSectionEditor.value}[/bold]")

    editor = config.get("editor", "")
    editor_ok, editor_msg, editor_suggestion = _check_editor(editor)

    if editor_ok == "ok":
        ok_count += 1
        status = f"[green]{MsgText.DoctorOK.value}[/green]"
    elif editor_ok == "warning":
        warning_count += 1
        status = f"[yellow]{MsgText.DoctorWarning.value}[/yellow]"
    else:
        error_count += 1
        status = f"[red]{MsgText.DoctorError.value}[/red]"

    table.add_row(status, editor_msg)
    if editor_suggestion:
        table.add_row("", f"[dim]{editor_suggestion}[/dim]")
    console.print(table)

    # Check encryption dependencies
    table = Table(show_header=False, box=None, padding=(0, 1))
    console.print(f"\n[bold]{MsgText.DoctorSectionEncryption.value}[/bold]")

    encrypt_ok, encrypt_msg, encrypt_suggestion = _check_encryption_dependencies()

    if encrypt_ok == "ok":
        ok_count += 1
        status = f"[green]{MsgText.DoctorOK.value}[/green]"
    elif encrypt_ok == "warning":
        warning_count += 1
        status = f"[yellow]{MsgText.DoctorWarning.value}[/yellow]"
    else:
        error_count += 1
        status = f"[red]{MsgText.DoctorError.value}[/red]"

    table.add_row(status, encrypt_msg)
    if encrypt_suggestion:
        table.add_row("", f"[dim]{encrypt_suggestion}[/dim]")
    console.print(table)

    # Check template
    table = Table(show_header=False, box=None, padding=(0, 1))
    console.print(f"\n[bold]{MsgText.DoctorSectionTemplate.value}[/bold]")

    template = config.get("template", False)
    template_ok, template_msg, template_suggestion = _check_template(template)

    if template_ok == "ok":
        ok_count += 1
        status = f"[green]{MsgText.DoctorOK.value}[/green]"
    elif template_ok == "warning":
        warning_count += 1
        status = f"[yellow]{MsgText.DoctorWarning.value}[/yellow]"
    else:
        error_count += 1
        status = f"[red]{MsgText.DoctorError.value}[/red]"

    table.add_row(status, template_msg)
    if template_suggestion:
        table.add_row("", f"[dim]{template_suggestion}[/dim]")
    console.print(table)

    # Summary
    console.print("\n" + "=" * 50)
    summary = MsgText.DoctorSummary.value.format(
        ok=ok_count, warning=warning_count, error=error_count
    )
    if error_count > 0:
        console.print(f"[bold red]{summary}[/bold red]")
    elif warning_count > 0:
        console.print(f"[bold yellow]{summary}[/bold yellow]")
    else:
        console.print(f"[bold green]{summary}[/bold green]")
    console.print()

    return 0 if error_count == 0 else 1


def _check_journal_path(path: str) -> tuple[str, str, str]:
    """Check if the journal path exists and is writable."""
    if os.path.isdir(path):
        return (
            "error",
            MsgText.DoctorJournalPathIsDir.value.format(path=path),
            MsgText.DoctorJournalPathSuggestion.value,
        )

    if not os.path.exists(path):
        parent_dir = os.path.dirname(path)
        if parent_dir and not os.path.exists(parent_dir):
            return (
                "warning",
                MsgText.DoctorJournalPathNotFound.value.format(path=path),
                MsgText.DoctorJournalPathSuggestion.value
                + " The directory will be created when you first write to the journal.",
            )
        return (
            "ok",
            MsgText.DoctorJournalPathOK.value.format(path=path)
            + " (file will be created on first write)",
            "",
        )

    if not os.access(path, os.W_OK):
        return (
            "error",
            MsgText.DoctorJournalPathNotWritable.value.format(path=path),
            MsgText.DoctorJournalPathSuggestion.value,
        )

    return ("ok", MsgText.DoctorJournalPathOK.value.format(path=path), "")


def _check_editor(editor: str) -> tuple[str, str, str]:
    """Check if the editor is configured and available."""
    if not editor:
        return (
            "warning",
            MsgText.DoctorEditorNotSet.value,
            MsgText.DoctorEditorNotSetSuggestion.value,
        )

    editor_cmd = split_args(editor)[0]

    if editor_cmd.startswith(("/", "./", "../")):
        if not os.path.exists(editor_cmd):
            return (
                "error",
                MsgText.DoctorEditorNotFound.value.format(editor=editor),
                MsgText.DoctorEditorNotFoundSuggestion.value.format(editor=editor_cmd),
            )
        if not os.access(editor_cmd, os.X_OK):
            return (
                "error",
                MsgText.DoctorEditorNotFound.value.format(editor=editor),
                f"Suggestion: Make sure '{editor_cmd}' is executable.",
            )
    else:
        if shutil.which(editor_cmd) is None:
            return (
                "error",
                MsgText.DoctorEditorNotFound.value.format(editor=editor),
                MsgText.DoctorEditorNotFoundSuggestion.value.format(editor=editor_cmd),
            )

    return ("ok", MsgText.DoctorEditorOK.value.format(editor=editor), "")


def _check_encryption_dependencies() -> tuple[str, str, str]:
    """Check if encryption dependencies are available."""
    try:
        import cryptography  # noqa: F401
    except ImportError:
        return (
            "error",
            MsgText.DoctorEncryptionCryptographyMissing.value,
            MsgText.DoctorEncryptionSuggestion.value,
        )

    try:
        import keyring

        try:
            keyring.get_keyring()
        except keyring.errors.NoKeyringError:
            return (
                "warning",
                MsgText.DoctorEncryptionKeyringNoBackend.value,
                MsgText.DoctorEncryptionKeyringSuggestion.value,
            )
    except ImportError:
        return (
            "warning",
            MsgText.DoctorEncryptionKeyringMissing.value,
            MsgText.DoctorEncryptionSuggestion.value,
        )

    return ("ok", MsgText.DoctorEncryptionOK.value, "")


def _check_template(template: str | bool) -> tuple[str, str, str]:
    """Check if the template file exists and is readable."""
    if not template:
        return ("ok", MsgText.DoctorTemplateNotSet.value, "")

    from jrnl.editor import get_template_path

    jrnl_template_dir = get_templates_path()
    actual_template_path = get_template_path(str(template), jrnl_template_dir)

    if not os.path.exists(actual_template_path):
        return (
            "error",
            MsgText.DoctorTemplateNotFound.value.format(path=str(template)),
            MsgText.DoctorTemplateNotFoundSuggestion.value.format(
                path=actual_template_path
            ),
        )

    if not os.access(actual_template_path, os.R_OK):
        return (
            "error",
            MsgText.DoctorTemplateNotReadable.value.format(path=actual_template_path),
            MsgText.DoctorTemplateSuggestion.value,
        )

    return (
        "ok",
        MsgText.DoctorTemplateOK.value.format(path=actual_template_path),
        "",
    )
