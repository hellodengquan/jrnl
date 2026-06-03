# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import logging
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from jrnl import install
from jrnl import plugins
from jrnl import time
from jrnl.args import DEPRECATED_COMMAND_ALIASES
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
    if command in DEPRECATED_COMMAND_ALIASES:
        _, old_alias, new_alias = DEPRECATED_COMMAND_ALIASES[command]
        deprecated_cmd(old_alias, new_alias)
        effective = DEPRECATED_COMMAND_ALIASES[command][0]

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
    _print_entries_found_count(ctx)

    _perform_actions_on_search_results(ctx)

    if entries_found_count != 0 and _has_action_args(ctx):
        _print_changed_counts(ctx)
    else:
        _display_search_results(ctx)


def _perform_actions_on_search_results(ctx: RuntimeContext):
    if ctx.args.change_time:
        _change_time_search_results(ctx)

    if ctx.args.delete:
        _delete_search_results(ctx)

    if ctx.args.edit:
        _edit_search_results(ctx)


def _is_append_mode(ctx: RuntimeContext) -> bool:
    """Determines if we are in append mode (as opposed to search mode)"""
    append_mode = (
        not _has_search_args(ctx)
        and not _has_action_args(ctx)
        and not _has_display_args(ctx)
    )

    if ctx.args.edit and ctx.effective_text:
        append_mode = True

    if append_mode and ctx.effective_text and _has_only_tags(ctx):
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

    template_text = _get_template(ctx)

    if ctx.effective_text:
        logging.debug(f"Append mode: cli text detected: {ctx.effective_text}")
        raw = " ".join(ctx.effective_text).strip()
        if ctx.args.edit:
            raw = _write_in_editor(ctx, raw)
    elif not sys.stdin.isatty():
        logging.debug("Append mode: receiving piped text")
        raw = sys.stdin.read()
    else:
        raw = _write_in_editor(ctx, template_text)

    if template_text is not None and raw == template_text:
        logging.error("Append mode: raw text was the same as the template")
        raise JrnlException(Message(MsgText.NoChangesToTemplate, MsgStyle.NORMAL))

    if not raw or raw.isspace():
        logging.error("Append mode: couldn't get raw text or entry was empty")
        raise JrnlException(Message(MsgText.NoTextReceived, MsgStyle.NORMAL))

    logging.debug(
        f"Append mode: appending raw text to journal '{ctx.journal_name}': {raw}"
    )
    ctx.journal.new_entry(raw)
    if ctx.journal_name != DEFAULT_JOURNAL_KEY:
        print_msg(
            Message(
                MsgText.JournalEntryAdded,
                MsgStyle.NORMAL,
                {"journal_name": ctx.journal_name},
            )
        )
    ctx.journal.write()
    logging.debug("Append mode: completed journal.write()")


def _get_template(ctx: RuntimeContext) -> str:
    logging.debug(
        "Get template:\n"
        f"--template: {ctx.args.template}\n"
        f"from config: {ctx.config.get('template')}"
    )
    template_path = ctx.args.template or ctx.config.get("template")

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

    if not _has_search_args(ctx) and not _has_display_args(ctx) and not ctx.effective_text:
        logging.debug("Search mode: has no search args")
        return

    logging.debug("Search mode: has search args")
    _filter_journal_entries(ctx)


def _write_in_editor(ctx: RuntimeContext, prepopulated_text: str | None = None) -> str:
    if ctx.config["editor"]:
        logging.debug("Append mode: opening editor")
        raw = get_text_from_editor(ctx.config, prepopulated_text)
    else:
        raw = get_text_from_stdin()

    return raw


def _filter_journal_entries(ctx: RuntimeContext) -> None:
    """Filter journal entries in-place based upon search args"""
    if ctx.args.on_date:
        ctx.args.start_date = ctx.args.end_date = ctx.args.on_date

    if ctx.args.today_in_history:
        now = time.parse("now")
        ctx.args.day = now.day
        ctx.args.month = now.month

    ctx.journal.filter(
        tags=ctx.effective_text,
        month=ctx.args.month,
        day=ctx.args.day,
        year=ctx.args.year,
        start_date=ctx.args.start_date,
        end_date=ctx.args.end_date,
        strict=ctx.args.strict,
        starred=ctx.args.starred,
        tagged=ctx.args.tagged,
        exclude=ctx.args.excluded,
        exclude_starred=ctx.args.exclude_starred,
        exclude_tagged=ctx.args.exclude_tagged,
        contains=ctx.args.contains,
    )
    ctx.journal.limit(ctx.args.limit)


def _print_entries_found_count(ctx: RuntimeContext) -> None:
    count = len(ctx.journal)
    logging.debug(f"count: {count}")
    if count == 0:
        if ctx.args.edit or ctx.args.change_time:
            print_msg(Message(MsgText.NothingToModify, MsgStyle.WARNING))
        elif ctx.args.delete:
            print_msg(Message(MsgText.NothingToDelete, MsgStyle.WARNING))
        else:
            print_msg(Message(MsgText.NoEntriesFound, MsgStyle.NORMAL))
        return
    elif ctx.args.limit and ctx.args.limit == count:
        logging.debug("args.limit is true-ish")
        return

    logging.debug("Printing general summary")
    my_msg = (
        MsgText.EntryFoundCountSingular if count == 1 else MsgText.EntryFoundCountPlural
    )
    print_msg(Message(my_msg, MsgStyle.NORMAL, {"num": count}))


def _other_entries(ctx: RuntimeContext) -> list["Entry"]:
    """Find entries that are not in the current filtered journal view"""
    return [e for e in ctx.old_entries if e not in ctx.journal.entries]


def _edit_search_results(ctx: RuntimeContext) -> None:
    """
    1. Send the given journal entries to the user-configured editor
    2. Print out stats on any modifications to journal
    3. Write modifications to journal
    """
    from jrnl.config import get_config_path

    if not ctx.config["editor"]:
        raise JrnlException(
            Message(
                MsgText.EditorNotConfigured,
                MsgStyle.ERROR,
                {"config_file": get_config_path()},
            )
        )

    other_entries = _other_entries(ctx)

    try:
        edited = get_text_from_editor(ctx.config, ctx.journal.editable_str())
    except JrnlException as e:
        if e.has_message_text(MsgText.NoTextReceived):
            raise JrnlException(
                Message(MsgText.NoEditsReceivedJournalNotDeleted, MsgStyle.WARNING)
            )
        else:
            raise e

    ctx.journal.parse_editable_str(edited)

    ctx.journal.entries += other_entries
    ctx.journal.sort()
    ctx.journal.write()


def _print_changed_counts(ctx: RuntimeContext) -> None:
    stats = ctx.journal.get_change_counts()
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


def _delete_search_results(ctx: RuntimeContext) -> None:
    entries_to_delete = ctx.journal.prompt_action_entries(MsgText.DeleteEntryQuestion)

    ctx.journal.entries = ctx.old_entries

    if entries_to_delete:
        ctx.journal.delete_entries(entries_to_delete)
        ctx.journal.write()


def _change_time_search_results(
    ctx: RuntimeContext,
    no_prompt: bool = False,
) -> None:
    entries_to_change = ctx.journal.prompt_action_entries(MsgText.ChangeTimeEntryQuestion)

    if entries_to_change:
        date = time.parse(ctx.args.change_time)
        ctx.journal.entries = ctx.old_entries
        ctx.journal.change_date_entries(date, entries_to_change)
        ctx.journal.write()


def _display_search_results(ctx: RuntimeContext) -> None:
    if len(ctx.journal) == 0:
        return

    export = ctx.args.export or ctx.config.get("display_format")

    if ctx.args.tags:
        print(plugins.get_exporter("tags").export(ctx.journal))

    elif ctx.args.short or export == "short":
        print(ctx.journal.pprint(short=True))

    elif export == "pretty":
        print(ctx.journal.pprint())

    elif export:
        exporter = plugins.get_exporter(export)
        print(exporter.export(ctx.journal, ctx.args.filename))
    else:
        print(ctx.journal.pprint())


def _has_search_args(ctx: RuntimeContext) -> bool:
    """Looking for arguments that filter a journal"""
    return any(
        (
            ctx.args.contains,
            ctx.args.tagged,
            ctx.args.excluded,
            ctx.args.exclude_starred,
            ctx.args.exclude_tagged,
            ctx.args.end_date,
            ctx.args.today_in_history,
            ctx.args.month,
            ctx.args.day,
            ctx.args.year,
            ctx.args.limit,
            ctx.args.on_date,
            ctx.args.starred,
            ctx.args.start_date,
            ctx.args.strict,
        )
    )


def _has_action_args(ctx: RuntimeContext) -> bool:
    return any(
        (
            ctx.args.change_time,
            ctx.args.delete,
            ctx.args.edit,
        )
    )


def _has_display_args(ctx: RuntimeContext) -> bool:
    return any(
        (
            ctx.args.tags,
            ctx.args.short,
            ctx.args.export,
        )
    )


def _has_only_tags(ctx: RuntimeContext) -> bool:
    tag_symbols = ctx.config["tagsymbols"]
    args_text = ctx.effective_text
    return all(word[0] in tag_symbols for word in " ".join(args_text).split())
