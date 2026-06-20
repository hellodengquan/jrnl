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
import concurrent.futures
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
    return len(tag) > 1 and tag[0] in tagsymbols


def _backup_journal_file(journal_path: str) -> str | None:
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
    import shutil

    try:
        if backup_path and os.path.exists(backup_path):
            shutil.copy2(backup_path, journal_path)
            os.remove(backup_path)
            return True
    except Exception as e:
        logging.error(f"Failed to restore backup for {journal_path}: {e}")
    return False


def _scan_single_journal(
    journal_name: str, j_config: dict, from_tag: str, to_tag: str
) -> dict | None:
    from jrnl.journals import open_journal

    try:
        journal = open_journal(journal_name, j_config)
    except JrnlException:
        return None

    matching_entries = journal.find_entries_with_tag(from_tag)
    count = len(matching_entries)
    dest_count = journal.count_tag_occurrences(to_tag)

    return {
        "journal": journal,
        "config": j_config,
        "count": count,
        "dest_count": dest_count,
        "sample_entries": matching_entries[:3],
    }


def _apply_conflict_strategy(
    journal_name: str,
    result: dict,
    from_tag: str,
    to_tag: str,
    on_conflict: str,
) -> bool:
    """Handle destination tag conflict based on strategy.
    Returns True if the journal should be kept, False if it should be removed.
    """
    dest_count = result.get("dest_count", 0)
    if dest_count == 0:
        return True

    print_msg(
        Message(
            MsgText.RenameTagDestExists,
            MsgStyle.WARNING,
            {"to_tag": to_tag, "journal_name": journal_name, "count": dest_count},
        )
    )

    if on_conflict == "skip":
        print_msg(
            Message(
                MsgText.RenameTagDestExistsSkip,
                MsgStyle.WARNING,
                {"journal_name": journal_name, "to_tag": to_tag},
            )
        )
        return False
    elif on_conflict == "merge":
        print_msg(
            Message(
                MsgText.RenameTagDestExistsMerge,
                MsgStyle.NORMAL,
                {"from_tag": from_tag, "to_tag": to_tag},
            )
        )
        return True
    else:
        raise JrnlException(
            Message(
                MsgText.RenameTagDestExistsAbort,
                MsgStyle.ERROR,
                {"to_tag": to_tag, "journal_name": journal_name},
            )
        )


def _render_dry_run_diff(
    scan_results: dict,
    from_tag: str,
    to_tag: str,
    sample_limit_per_journal: int = 5,
) -> None:
    """Render BEFORE/AFTER diff for a sample of entries in each journal."""
    import copy
    import re

    from jrnl.color import colorize
    from jrnl.journals.Entry import Entry as EntryCls

    for journal_name, result in scan_results.items():
        journal = result["journal"]
        matching = journal.find_entries_with_tag(from_tag)
        if not matching:
            continue

        print_msg(
            Message(
                MsgText.RenameTagDryRunDiffHeader,
                MsgStyle.NORMAL,
                {"journal_name": journal_name},
            )
        )

        tagsymbols = journal.config["tagsymbols"]
        tag_re = EntryCls.tag_regex(tagsymbols)
        from_lower = from_tag.lower()

        sample_entries = matching[:sample_limit_per_journal]
        total_sample = len(sample_entries)

        for idx, entry in enumerate(sample_entries, 1):
            date_str = entry.date.strftime(journal.config["timeformat"])

            print_msg(
                Message(
                    MsgText.RenameTagDryRunDiffEntryHeader,
                    MsgStyle.NORMAL,
                    {"date": date_str, "index": idx, "total": total_sample},
                )
            )

            original_text = (str(entry)).rstrip()

            def _recolor(match: re.Match) -> str:
                t = match.group(1)
                if t.lower() == from_lower:
                    return t
                return t

            before_text = ""
            pos = 0
            for m in tag_re.finditer(original_text):
                before_text += original_text[pos : m.start()]
                t = m.group(1)
                if t.lower() == from_lower:
                    before_text += colorize(t, "red", bold=True)
                else:
                    before_text += t
                pos = m.end()
            before_text += original_text[pos:]

            def _do_rename(match: re.Match) -> str:
                t = match.group(1)
                if t.lower() == from_lower:
                    prefix = t[0]
                    body = to_tag[1:] if to_tag[0] in tagsymbols else to_tag
                    return prefix + body
                return t

            renamed_text = tag_re.sub(_do_rename, original_text)

            to_lower = to_tag.lower()
            after_text = ""
            pos = 0
            for m in tag_re.finditer(renamed_text):
                after_text += renamed_text[pos : m.start()]
                t = m.group(1)
                if t.lower() == to_lower:
                    after_text += colorize(t, "green", bold=True)
                else:
                    after_text += t
                pos = m.end()
            after_text += renamed_text[pos:]

            before_lines = before_text.splitlines()[:4]
            after_lines = after_text.splitlines()[:4]

            for line in before_lines:
                print_msg(
                    Message(
                        MsgText.RenameTagDryRunDiffBefore,
                        MsgStyle.NORMAL,
                        {"text": line[:120]},
                    )
                )
            for line in after_lines:
                print_msg(
                    Message(
                        MsgText.RenameTagDryRunDiffAfter,
                        MsgStyle.NORMAL,
                        {"text": line[:120]},
                    )
                )

        print_msg(Message(MsgText.RenameTagDryRunDiffSeparator, MsgStyle.NORMAL))



def _perform_rollback(
    backups: dict,
    processed_journals: list,
    scan_results: dict,
) -> dict:
    """Attempt rollback with multi-layer recovery.
    Returns a dict summarizing recovery status per journal:
      {name: {"backup_restored": bool, "memory_reverted": bool, "verified": bool, "backup_path": str|None}}
    """
    import shutil

    from jrnl.journals import open_journal

    recovery_status = {}

    for journal_name in reversed(list(backups.keys())):
        backup_path, journal_path = backups[journal_name]

        print_msg(
            Message(
                MsgText.RenameTagRollbackJournal,
                MsgStyle.WARNING,
                {"journal_name": journal_name},
            )
        )

        backup_restored = False
        memory_reverted = False
        verified = False

        if backup_path and os.path.exists(backup_path):
            backup_restored = _restore_from_backup(backup_path, journal_path)

        if not backup_restored:
            for proc_name, rollback_data, _ in reversed(processed_journals):
                if proc_name == journal_name and rollback_data:
                    journal = scan_results[journal_name]["journal"]
                    journal.rollback_tag_rename(rollback_data)
                    try:
                        journal.write()
                        memory_reverted = True
                    except Exception as write_err:
                        logging.error(
                            f"Failed to write in-memory rollback for {journal_name}: {write_err}"
                        )
                    break

        if backup_restored or memory_reverted:
            j_config = scan_results[journal_name]["config"]
            try:
                verify_journal = open_journal(journal_name, j_config)
                if len(verify_journal.entries) > 0:
                    verified = True
            except Exception as verify_err:
                logging.error(
                    f"Verification failed for {journal_name}: {verify_err}"
                )

        retained_backup = None
        if not verified and backup_path and os.path.exists(backup_path):
            retained_backup = backup_path
        elif not verified:
            try:
                retained_backup = _backup_journal_file(journal_path)
            except Exception:
                pass

        recovery_status[journal_name] = {
            "backup_restored": backup_restored,
            "memory_reverted": memory_reverted,
            "verified": verified,
            "backup_path": retained_backup,
        }

        print_msg(
            Message(
                MsgText.RenameTagRollbackPartialState,
                MsgStyle.WARNING if not verified else MsgStyle.NORMAL,
                {
                    "journal_name": journal_name,
                    "backup_path": retained_backup or "N/A",
                    "backup_restored": str(backup_restored),
                    "memory_reverted": str(memory_reverted),
                    "verified": str(verified),
                },
            )
        )

    return recovery_status


def postconfig_rename_tag(
    args: argparse.Namespace, config: dict, original_config: dict
) -> int:
    """
    Rename a tag across entries in one or multiple journals.
    Supports:
    - Concurrent scanning with progress feedback across multiple journals
    - Encrypted journal protection
    - Destination tag conflict handling (merge / skip / abort)
    - Multi-layer rollback: file backup -> in-memory revert -> re-read verification
    """
    import concurrent.futures
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
    on_conflict = getattr(args, "on_conflict", "abort")
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

    total_journals = len(journal_names)

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
    scanned_count = 0

    scan_futures = {}
    encrypted_set = set()

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
            encrypted_set.add(journal_name)
            continue

        print_msg(
            Message(
                MsgText.RenameTagScanProgress,
                MsgStyle.NORMAL,
                {
                    "current": journal_names.index(journal_name) + 1 - len(encrypted_set),
                    "total": total_journals - len(encrypted_set),
                    "journal_name": journal_name,
                },
            )
        )

        future = _SCAN_EXECUTOR.submit(
            _scan_single_journal, journal_name, j_config, from_tag, to_tag
        )
        scan_futures[future] = journal_name

    for future in concurrent.futures.as_completed(scan_futures):
        journal_name = scan_futures[future]
        scanned_count += 1

        try:
            result = future.result()
        except Exception as e:
            logging.error(f"Scan failed for journal {journal_name}: {e}")
            skipped_journals.append(journal_name)
            continue

        if result is None:
            skipped_journals.append(journal_name)
            continue

        scan_results[journal_name] = result
        count = result["count"]
        total_entries += count

        print_msg(
            Message(
                MsgText.RenameTagJournalSummary,
                MsgStyle.NORMAL,
                {"journal_name": journal_name, "count": count},
            )
        )

        if result["dest_count"] > 0:
            print_msg(
                Message(
                    MsgText.RenameTagDestExists,
                    MsgStyle.WARNING,
                    {
                        "to_tag": to_tag,
                        "journal_name": journal_name,
                        "count": result["dest_count"],
                    },
                )
            )

        sample_limit = min(3, count)
        for i in range(sample_limit):
            entry = result["sample_entries"][i]
            date_str = entry.date.strftime(result["journal"].config["timeformat"])
            print_msg(
                Message(
                    MsgText.RenameTagSampleEntry,
                    MsgStyle.NORMAL,
                    {"date": date_str, "title": entry.title.strip()[:80]},
                )
            )

    print_msg(
        Message(
            MsgText.RenameTagScanComplete,
            MsgStyle.NORMAL,
            {
                "scanned": scanned_count,
                "skipped": len(skipped_journals),
                "matched": total_entries,
            },
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

    scan_results_before_conflict = dict(scan_results)
    for journal_name, result in list(scan_results.items()):
        should_keep = _apply_conflict_strategy(
            journal_name, result, from_tag, to_tag, on_conflict
        )
        if not should_keep:
            total_entries -= result["count"]
            del scan_results[journal_name]

    if total_entries == 0:
        print_msg(
            Message(
                MsgText.RenameTagNoEntriesFound,
                MsgStyle.WARNING,
                {"from_tag": from_tag},
            )
        )
        return 0

    _render_dry_run_diff(scan_results, from_tag, to_tag)

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

            if os.path.isdir(journal_path):
                backup_path = None
            else:
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

        all_results = {**scan_results_before_conflict, **scan_results}
        recovery_status = _perform_rollback(
            backups, processed_journals, all_results
        )

        recovered = 0
        failed = 0
        partial = 0
        retained_backups = []

        for jname, status in recovery_status.items():
            if status["verified"]:
                recovered += 1
            elif status["memory_reverted"] or status["backup_restored"]:
                partial += 1
            else:
                failed += 1

            if status["backup_path"] and os.path.exists(status["backup_path"]):
                retained_backups.append(status["backup_path"])

        for journal_name, result in scan_results.items():
            if journal_name not in recovery_status:
                continue
            bp = backups.get(journal_name, (None, None))[0]
            if bp and os.path.exists(bp):
                try:
                    os.remove(bp)
                except Exception:
                    pass

        print_msg(
            Message(
                MsgText.RenameTagRollbackSummary,
                MsgStyle.WARNING,
                {
                    "recovered": recovered,
                    "failed": failed,
                    "partial": partial,
                    "backup_list": "\n".join(f"  - {p}" for p in retained_backups) if retained_backups else "  (none)",
                },
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


_SCAN_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=4)
