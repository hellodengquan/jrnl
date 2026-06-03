# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import logging
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from jrnl import install
from jrnl import plugins
from jrnl import time
from jrnl.args import DEPRECATED_ALIASES
from jrnl.args import ParsedArgs
from jrnl.commands import postconfig_decrypt
from jrnl.commands import postconfig_encrypt
from jrnl.commands import postconfig_import
from jrnl.commands import postconfig_list
from jrnl.commands import preconfig_diagnostic
from jrnl.commands import preconfig_version
from jrnl.config import DEFAULT_JOURNAL_KEY
from jrnl.config import get_journal_name
from jrnl.config import scope_config
from jrnl.editor import get_text_from_editor
from jrnl.editor import get_text_from_stdin
from jrnl.editor import read_template_file
from jrnl.exception import JrnlException
from jrnl.journals import open_journal
from jrnl.messages import Message
from jrnl.messages import MsgStyle
from jrnl.messages import MsgText
from jrnl.output import deprecated_cmd
from jrnl.output import print_msg
from jrnl.output import print_msgs
from jrnl.override import apply_overrides

if TYPE_CHECKING:
    from jrnl.journals import Entry
    from jrnl.journals import Journal


@dataclass
class RuntimeContext:
    args: ParsedArgs
    config: dict
    original_config: dict
    journal_name: str = DEFAULT_JOURNAL_KEY
    effective_text: list[str] = field(default_factory=list)
    journal: "Journal | None" = None
    old_entries: list["Entry"] = field(default_factory=list)


_PRECONFIG_DISPATCH = {
    "version": preconfig_version,
    "diagnostic": preconfig_diagnostic,
}

_POSTCONFIG_DISPATCH = {
    "list": postconfig_list,
    "encrypt": postconfig_encrypt,
    "decrypt": postconfig_decrypt,
    "import": postconfig_import,
}


def _dispatch_preconfig(command: str, parsed_args: ParsedArgs):
    handler = _PRECONFIG_DISPATCH.get(command)
    if handler is None:
        raise JrnlException(
            Message(
                MsgText.UncaughtException,
                MsgStyle.ERROR,
                {"name": "UnknownCommand", "exception": f"Unknown preconfig command: {command}"},
            )
        )
    return handler(parsed_args)


def _dispatch_postconfig(command: str, ctx: RuntimeContext):
    effective = command
    if command in DEPRECATED_ALIASES:
        _, old_alias, new_alias = DEPRECATED_ALIASES[command]
        deprecated_cmd(old_alias, new_alias)
        effective = DEPRECATED_ALIASES[command][0]

    handler = _POSTCONFIG_DISPATCH.get(effective)
    if handler is None:
        raise JrnlException(
            Message(
                MsgText.UncaughtException,
                MsgStyle.ERROR,
                {"name": "UnknownCommand", "exception": f"Unknown postconfig command: {effective}"},
            )
        )
    return handler(ctx)


def run(parsed_args: ParsedArgs):
    """
    Flow:
    1. Run standalone command if it doesn't need config (help, version, etc), then exit
    2. Load config
    3. Run standalone command if it does need config (encrypt, decrypt, etc), then exit
    4. Load specified journal
    5. Start append mode, or search mode
    6. Perform actions with results from search mode (if needed)
    7. Profit
    """

    if parsed_args.is_preconfig_command:
        return _dispatch_preconfig(parsed_args.command, parsed_args)

    config = install.load_or_install_jrnl(parsed_args.config_file_path)
    original_config = config.copy()

    config = apply_overrides(parsed_args, config)

    journal_name, effective_text = get_journal_name(parsed_args, config)
    config = scope_config(config, journal_name)

    if parsed_args.is_postconfig_command:
        ctx = RuntimeContext(
            args=parsed_args,
            config=config,
            original_config=original_config,
            journal_name=journal_name,
            effective_text=effective_text,
        )
        return _dispatch_postconfig(parsed_args.command, ctx)

    journal = open_journal(journal_name, config)

    ctx = RuntimeContext(
        args=parsed_args,
        config=config,
        original_config=original_config,
        journal_name=journal_name,
        effective_text=effective_text,
        journal=journal,
        old_entries=journal.entries,
    )

    if _is_append_mode(ctx):
        append_mode(ctx)
        return

    search_mode(ctx)
    entries_found_count = len(journal)
    _print_entries_found_count(entries_found_count, ctx.args)

    _perform_actions_on_search_results(ctx)

    if entries_found_count != 0 and _has_action_args(ctx.args):
        _print_changed_counts(journal)
    else:
        _display_search_results(ctx)


def _perform_actions_on_search_results(ctx: RuntimeContext):
    args = ctx.args

    if args.change_time:
        _change_time_search_results(ctx)

    if args.delete:
        _delete_search_results(ctx)

    if args.edit:
        _edit_search_results(ctx)


def _is_append_mode(ctx: RuntimeContext) -> bool:
    """Determines if we are in append mode (as opposed to search mode)"""
    args = ctx.args
    config = ctx.config

    append_mode = (
        not _has_search_args(args)
        and not _has_action_args(args)
        and not _has_display_args(args)
    )

    if args.edit and ctx.effective_text:
        append_mode = True

    if append_mode and ctx.effective_text and _has_only_tags(config["tagsymbols"], ctx.effective_text):
        append_mode = False

    return append_mode


def append_mode(ctx: RuntimeContext) -> None:
    """
    Gets input from the user to write to the journal
    0. Check for a template passed as an argument, or in the global config
    1. Check for input from cli
    2. Check input being piped in
    3. Open editor if configured (prepopulated with template if available)
    4. Use stdin.read as last resort
    6. Write any found text to journal, or exit
    """
    logging.debug("Append mode: starting")

    args = ctx.args
    config = ctx.config
    journal = ctx.journal

    template_text = _get_template(args, config)

    if ctx.effective_text:
        logging.debug(f"Append mode: cli text detected: {ctx.effective_text}")
        raw = " ".join(ctx.effective_text).strip()
        if args.edit:
            raw = _write_in_editor(config, raw)
    elif not sys.stdin.isatty():
        logging.debug("Append mode: receiving piped text")
        raw = sys.stdin.read()
    else:
        raw = _write_in_editor(config, template_text)

    if template_text is not None and raw == template_text:
        logging.error("Append mode: raw text was the same as the template")
        raise JrnlException(Message(MsgText.NoChangesToTemplate, MsgStyle.NORMAL))

    if not raw or raw.isspace():
        logging.error("Append mode: couldn't get raw text or entry was empty")
        raise JrnlException(Message(MsgText.NoTextReceived, MsgStyle.NORMAL))

    logging.debug(
        f"Append mode: appending raw text to journal '{ctx.journal_name}': {raw}"
    )
    journal.new_entry(raw)
    if ctx.journal_name != DEFAULT_JOURNAL_KEY:
        print_msg(
            Message(
                MsgText.JournalEntryAdded,
                MsgStyle.NORMAL,
                {"journal_name": ctx.journal_name},
            )
        )
    journal.write()
    logging.debug("Append mode: completed journal.write()")


def _get_template(args, config) -> str:
    logging.debug(
        "Get template:\n"
        f"--template: {args.template}\n"
        f"from config: {config.get('template')}"
    )
    template_path = args.template or config.get("template")

    template_text = None

    if template_path:
        template_text = read_template_file(template_path)

    return template_text


def search_mode(ctx: RuntimeContext) -> None:
    """
    Search for entries in a journal, and return the
    results. If no search args, then return all results
    """
    logging.debug("Search mode: starting")

    args = ctx.args
    journal = ctx.journal

    if not _has_search_args(args) and not _has_display_args(args) and not ctx.effective_text:
        logging.debug("Search mode: has no search args")
        return

    logging.debug("Search mode: has search args")
    _filter_journal_entries(ctx)


def _write_in_editor(config: dict, prepopulated_text: str | None = None) -> str:
    if config["editor"]:
        logging.debug("Append mode: opening editor")
        raw = get_text_from_editor(config, prepopulated_text)
    else:
        raw = get_text_from_stdin()

    return raw


def _filter_journal_entries(ctx: RuntimeContext) -> None:
    """Filter journal entries in-place based upon search args"""
    args = ctx.args
    journal = ctx.journal

    if args.on_date:
        args.start_date = args.end_date = args.on_date

    if args.today_in_history:
        now = time.parse("now")
        args.day = now.day
        args.month = now.month

    journal.filter(
        tags=ctx.effective_text,
        month=args.month,
        day=args.day,
        year=args.year,
        start_date=args.start_date,
        end_date=args.end_date,
        strict=args.strict,
        starred=args.starred,
        tagged=args.tagged,
        exclude=args.excluded,
        exclude_starred=args.exclude_starred,
        exclude_tagged=args.exclude_tagged,
        contains=args.contains,
    )
    journal.limit(args.limit)


def _print_entries_found_count(count: int, args: ParsedArgs) -> None:
    logging.debug(f"count: {count}")
    if count == 0:
        if args.edit or args.change_time:
            print_msg(Message(MsgText.NothingToModify, MsgStyle.WARNING))
        elif args.delete:
            print_msg(Message(MsgText.NothingToDelete, MsgStyle.WARNING))
        else:
            print_msg(Message(MsgText.NoEntriesFound, MsgStyle.NORMAL))
        return
    elif args.limit and args.limit == count:
        logging.debug("args.limit is true-ish")
        return

    logging.debug("Printing general summary")
    my_msg = (
        MsgText.EntryFoundCountSingular if count == 1 else MsgText.EntryFoundCountPlural
    )
    print_msg(Message(my_msg, MsgStyle.NORMAL, {"num": count}))


def _other_entries(journal: "Journal", entries: list["Entry"]) -> list["Entry"]:
    """Find entries that are not in journal"""
    return [e for e in entries if e not in journal.entries]


def _edit_search_results(ctx: RuntimeContext) -> None:
    """
    1. Send the given journal entries to the user-configured editor
    2. Print out stats on any modifications to journal
    3. Write modifications to journal
    """
    from jrnl.config import get_config_path

    config = ctx.config
    journal = ctx.journal
    old_entries = ctx.old_entries

    if not config["editor"]:
        raise JrnlException(
            Message(
                MsgText.EditorNotConfigured,
                MsgStyle.ERROR,
                {"config_file": get_config_path()},
            )
        )

    other_entries = _other_entries(journal, old_entries)

    try:
        edited = get_text_from_editor(config, journal.editable_str())
    except JrnlException as e:
        if e.has_message_text(MsgText.NoTextReceived):
            raise JrnlException(
                Message(MsgText.NoEditsReceivedJournalNotDeleted, MsgStyle.WARNING)
            )
        else:
            raise e

    journal.parse_editable_str(edited)

    journal.entries += other_entries
    journal.sort()
    journal.write()


def _print_changed_counts(journal: "Journal", **kwargs) -> None:
    stats = journal.get_change_counts()
    msgs = []

    if stats["added"] > 0:
        my_msg = (
            MsgText.JournalCountAddedSingular
            if stats["added"] == 1
            else MsgText.JournalCountAddedPlural
        )
        msgs.append(Message(my_msg, MsgStyle.NORMAL, {"num": stats["added"]}))

    if stats["deleted"] > 0:
        my_msg = (
            MsgText.JournalCountDeletedSingular
            if stats["deleted"] == 1
            else MsgText.JournalCountDeletedPlural
        )
        msgs.append(Message(my_msg, MsgStyle.NORMAL, {"num": stats["deleted"]}))

    if stats["modified"] > 0:
        my_msg = (
            MsgText.JournalCountModifiedSingular
            if stats["modified"] == 1
            else MsgText.JournalCountModifiedPlural
        )
        msgs.append(Message(my_msg, MsgStyle.NORMAL, {"num": stats["modified"]}))

    if not msgs:
        msgs.append(Message(MsgText.NoEditsReceived, MsgStyle.NORMAL))

    print_msgs(msgs)


def _get_predit_stats(journal: "Journal") -> dict[str, int]:
    return {"count": len(journal)}


def _delete_search_results(ctx: RuntimeContext) -> None:
    journal = ctx.journal
    old_entries = ctx.old_entries

    entries_to_delete = journal.prompt_action_entries(MsgText.DeleteEntryQuestion)

    journal.entries = old_entries

    if entries_to_delete:
        journal.delete_entries(entries_to_delete)

        journal.write()


def _change_time_search_results(
    ctx: RuntimeContext,
    no_prompt: bool = False,
) -> None:
    args = ctx.args
    journal = ctx.journal
    old_entries = ctx.old_entries

    entries_to_change = journal.prompt_action_entries(MsgText.ChangeTimeEntryQuestion)

    if entries_to_change:
        date = time.parse(args.change_time)
        journal.entries = old_entries
        journal.change_date_entries(date, entries_to_change)

        journal.write()


def _display_search_results(ctx: RuntimeContext) -> None:
    journal = ctx.journal

    if len(journal) == 0:
        return

    export = ctx.args.export or ctx.config.get("display_format")

    if ctx.args.tags:
        print(plugins.get_exporter("tags").export(journal))

    elif ctx.args.short or export == "short":
        print(journal.pprint(short=True))

    elif export == "pretty":
        print(journal.pprint())

    elif export:
        exporter = plugins.get_exporter(export)
        print(exporter.export(journal, ctx.args.filename))
    else:
        print(journal.pprint())


def _has_search_args(args: ParsedArgs) -> bool:
    """Looking for arguments that filter a journal"""
    return any(
        (
            args.contains,
            args.tagged,
            args.excluded,
            args.exclude_starred,
            args.exclude_tagged,
            args.end_date,
            args.today_in_history,
            args.month,
            args.day,
            args.year,
            args.limit,
            args.on_date,
            args.starred,
            args.start_date,
            args.strict,
        )
    )


def _has_action_args(args: ParsedArgs) -> bool:
    return any(
        (
            args.change_time,
            args.delete,
            args.edit,
        )
    )


def _has_display_args(args: ParsedArgs) -> bool:
    return any(
        (
            args.tags,
            args.short,
            args.export,
        )
    )


def _has_only_tags(tag_symbols: str, args_text: list[str]) -> bool:
    return all(word[0] in tag_symbols for word in " ".join(args_text).split())
