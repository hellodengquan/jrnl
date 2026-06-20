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


def _validate_tag_format(tag: str, tagsymbols: str) -> bool:
    """Check if tag starts with a valid tag symbol."""
    return len(tag) > 1 and tag[0] in tagsymbols


def _backup_journal_file(journal_path: str) -> str | None:
    """Create a backup copy of the journal file before modification."""
    import shutil

    backup_path = journal_path + ".bak"
    try:
        if os.path.exists(journal_path):
            shutil.copy2(journal_path, backup_path)
            return backup_path
    except Exception as e:
        logging.warning(f"Failed to create backup for {journal_path}: {e}")
    return None


def _restore_from_backup(backup_path: str, journal_path: str) -> bool:
    """Restore journal from backup file."""
    import shutil

    try:
        if backup_path and os.path.exists(backup_path):
            shutil.copy2(backup_path, journal_path)
            os.remove(backup_path)
            return True
    except Exception as e:
        logging.error(f"Failed to restore backup for {journal_path}: {e}")
    return False


def postconfig_rename_tag(
    args: argparse.Namespace, config: dict, original_config: dict
) -> int:
    """
    Rename a tag across entries in one or multiple journals.
    Supports:
    - Preview scanning with sample entries
    - Encrypted journal protection
    - Destination tag existence warning
    - Transactional rollback on write failure
    """
    import os
    import shutil

    from jrnl.config import scope_config
    from jrnl.config import validate_journal_name
    from jrnl.journals import open_journal
    from jrnl.prompt import yesno

    if not args.from_tag or not args.to_tag:
        raise JrnlException(
            Message(MsgText.RenameTagMissingArgs, MsgStyle.ERROR)
        )

    from_tag = args.from_tag.strip()
    to_tag = args.to_tag.strip()
    tagsymbols = config.get("tagsymbols", "@")

    if from_tag.lower() == to_tag.lower():
        raise JrnlException(
            Message(
                MsgText.RenameTagSameSourceDest,
                MsgStyle.WARNING,
                {"from_tag": from_tag, "to_tag": to_tag},
            )
        )

    if not _validate_tag_format(from_tag, tagsymbols):
        raise JrnlException(
            Message(
                MsgText.RenameTagInvalidFormat,
                MsgStyle.ERROR,
                {"tag": from_tag, "tagsymbols": tagsymbols},
            )
        )
    if not _validate_tag_format(to_tag, tagsymbols):
        raise JrnlException(
            Message(
                MsgText.RenameTagInvalidFormat,
                MsgStyle.ERROR,
                {"tag": to_tag, "tagsymbols": tagsymbols},
            )
        )

    journal_names = []
    if args.all_journals:
        journal_names = list(original_config["journals"].keys())
    else:
        validate_journal_name(args.journal_name, original_config)
        journal_names = [args.journal_name]

    print_msg(
        Message(
            MsgText.RenameTagScanHeader,
            MsgStyle.NORMAL,
            {"from_tag": from_tag, "to_tag": to_tag},
        )
    )

    scan_results = {}
    skipped_journals = []
    total_entries = 0

    for journal_name in journal_names:
        j_config = scope_config(original_config.copy(), journal_name)

        if j_config.get("encrypt", False):
            print_msg(
                Message(
                    MsgText.RenameTagJournalEncrypted,
                    MsgStyle.WARNING,
                    {"journal_name": journal_name},
                )
            )
            skipped_journals.append(journal_name)
            continue

        try:
            journal = open_journal(journal_name, j_config)
        except JrnlException:
            skipped_journals.append(journal_name)
            continue

        matching_entries = journal.find_entries_with_tag(from_tag)
        count = len(matching_entries)
        dest_count = journal.count_tag_occurrences(to_tag)

        scan_results[journal_name] = {
            "journal": journal,
            "config": j_config,
            "count": count,
            "dest_count": dest_count,
            "sample_entries": matching_entries[:3],
        }

        total_entries += count

        print_msg(
            Message(
                MsgText.RenameTagJournalSummary,
                MsgStyle.NORMAL,
                {"journal_name": journal_name, "count": count},
            )
        )

        if dest_count > 0:
            print_msg(
                Message(
                    MsgText.RenameTagDestExists,
                    MsgStyle.WARNING,
                    {"to_tag": to_tag, "journal_name": journal_name, "count": dest_count},
                )
            )

        sample_limit = min(3, count)
        for i in range(sample_limit):
            entry = matching_entries[i]
            date_str = entry.date.strftime(journal.config["timeformat"])
            print_msg(
                Message(
                    MsgText.RenameTagSampleEntry,
                    MsgStyle.NORMAL,
                    {"date": date_str, "title": entry.title.strip()[:80]},
                )
            )

    if total_entries == 0:
        print_msg(
            Message(
                MsgText.RenameTagNoEntriesFound,
                MsgStyle.WARNING,
                {"from_tag": from_tag},
            )
        )
        return 0

    if args.dry_run:
        print_msg(Message(MsgText.RenameTagDryRunComplete, MsgStyle.NORMAL))
        return 0

    journal_count = len(scan_results)
    if not yesno(
        Message(
            MsgText.RenameTagConfirmPrompt,
            params={
                "from_tag": from_tag,
                "to_tag": to_tag,
                "total_entries": total_entries,
                "journal_count": journal_count,
            },
        ),
        default=False,
    ):
        print_msg(Message(MsgText.RenameTagAborted, MsgStyle.NORMAL))
        return 0

    processed_journals = []
    backups = {}
    error_occurred = False

    try:
        for journal_name, result in scan_results.items():
            if result["count"] == 0:
                continue

            journal = result["journal"]
            j_config = result["config"]
            journal_path = j_config.get("journal")

            backup_path = _backup_journal_file(journal_path)
            backups[journal_name] = (backup_path, journal_path)

            modified_count, rollback_data = journal.rename_tag(from_tag, to_tag)

            try:
                journal.write()
            except Exception as e:
                logging.error(f"Failed to write journal {journal_name}: {e}")
                error_occurred = e
                break

            processed_journals.append((journal_name, rollback_data, modified_count))

            print_msg(
                Message(
                    MsgText.RenameTagSuccessJournal,
                    MsgStyle.NORMAL,
                    {"journal_name": journal_name, "count": modified_count},
                )
            )

        if error_occurred:
            raise JrnlException(
                Message(
                    MsgText.RenameTagError,
                    MsgStyle.ERROR,
                    {"error": str(error_occurred)},
                )
            )

    except Exception as e:
        print_msg(Message(MsgText.RenameTagError, MsgStyle.ERROR, {"error": str(e)}))

        for journal_name in reversed(list(backups.keys())):
            backup_path, journal_path = backups[journal_name]
            print_msg(
                Message(
                    MsgText.RenameTagRollbackJournal,
                    MsgStyle.WARNING,
                    {"journal_name": journal_name},
                )
            )

            restored = False
            if backup_path and os.path.exists(backup_path):
                restored = _restore_from_backup(backup_path, journal_path)

            if restored:
                print_msg(
                    Message(
                        MsgText.RenameTagRollbackSuccess,
                        MsgStyle.NORMAL,
                        {"journal_name": journal_name},
                    )
                )
            else:
                print_msg(
                    Message(
                        MsgText.RenameTagRollbackFailed,
                        MsgStyle.ERROR,
                        {"journal_name": journal_name},
                    )
                )

        return 1

    for backup_path, _ in backups.values():
        if backup_path and os.path.exists(backup_path):
            try:
                os.remove(backup_path)
            except Exception:
                pass

    print_msg(
        Message(
            MsgText.RenameTagComplete,
            MsgStyle.NORMAL,
            {"total_entries": total_entries, "journal_count": journal_count},
        )
    )

    return 0
