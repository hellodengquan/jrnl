# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import argparse
import re
import textwrap
from dataclasses import dataclass, field

from jrnl.plugins import EXPORT_FORMATS
from jrnl.plugins import IMPORT_FORMATS
from jrnl.plugins import util

PRECONFIG_COMMANDS = frozenset({"version", "diagnostic"})
POSTCONFIG_COMMANDS = frozenset({"list", "encrypt", "decrypt", "import"})

DEPRECATED_COMMAND_ALIASES = {
    "list_deprecated": ("list", "-ls", "--list or --ls"),
}

DEPRECATED_ARG_ALIASES = {
    "-to": ("--to", "-until"),
    "--export": ("--export", "--format"),
    "-o": ("-o", "--file"),
    "config_password": ("password config field", "system keychain"),
}


@dataclass
class ParsedArgs:
    command: str | None = None
    used_deprecated_alias: str | None = None
    debug: bool = False
    config_file_path: str = ""
    config_override: list[list[str]] = field(default_factory=list)

    text: list[str] = field(default_factory=list)
    template: str | None = None

    on_date: str | None = None
    today_in_history: bool = False
    month: str | None = None
    day: str | None = None
    year: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    contains: list[str] | None = None
    strict: bool = False
    starred: bool = False
    tagged: bool = False
    limit: int | None = None
    excluded: list[str] = field(default_factory=list)
    exclude_starred: bool = False
    exclude_tagged: bool = False

    edit: bool = False
    delete: bool = False
    change_time: str | None = None

    export: str | bool = False
    tags: bool = False
    short: bool = False
    filename: str | None = None

    password: str | None = None
    keychain: bool = True
    keyring_available: bool = True

    @property
    def is_preconfig_command(self) -> bool:
        return self.command in PRECONFIG_COMMANDS

    @property
    def is_postconfig_command(self) -> bool:
        return self.command in POSTCONFIG_COMMANDS or self.command in DEPRECATED_COMMAND_ALIASES

    @property
    def effective_command(self) -> str | None:
        if self.command in DEPRECATED_COMMAND_ALIASES:
            return DEPRECATED_COMMAND_ALIASES[self.command][0]
        return self.command


class WrappingFormatter(argparse.RawTextHelpFormatter):
    """Used in help screen"""

    def _split_lines(self, text: str, width: int) -> list[str]:
        text = text.split("\n\n")
        text = map(lambda t: self._whitespace_matcher.sub(" ", t).strip(), text)
        text = map(lambda t: textwrap.wrap(t, width=56), text)
        text = [item for sublist in text for item in sublist]
        return text


class IgnoreNoneAppendAction(argparse._AppendAction):
    """
    Pass -not without a following string and avoid appending
    a None value to the excluded list
    """

    def __call__(self, parser, namespace, values, option_string=None):
        if values is not None:
            super().__call__(parser, namespace, values, option_string)


def parse_not_arg(
    args: list[str], parsed_args: argparse.Namespace, parser: argparse.ArgumentParser
) -> argparse.Namespace:
    """
    It's possible to use -not as a precursor to -starred and -tagged
    to reverse their behaviour, however this requires some extra logic
    to parse, and to ensure we still do not allow passing an empty -not
    """

    parsed_args.exclude_starred = False
    parsed_args.exclude_tagged = False

    if "-not-starred" in "".join(args):
        parsed_args.starred = False
        parsed_args.exclude_starred = True
    if "-not-tagged" in "".join(args):
        parsed_args.tagged = False
        parsed_args.exclude_tagged = True
    if "-not" in args and not any(
        [parsed_args.exclude_starred, parsed_args.exclude_tagged, parsed_args.excluded]
    ):
        parser.error("argument -not: expected 1 argument")

    return parsed_args


def _namespace_to_parsed_args(ns: argparse.Namespace) -> ParsedArgs:
    preconfig_cmd = getattr(ns, "preconfig_cmd", None)
    postconfig_cmd = getattr(ns, "postconfig_cmd", None)

    command = None
    used_deprecated_alias = None

    if preconfig_cmd is not None:
        command = preconfig_cmd
    elif postconfig_cmd is not None:
        command = postconfig_cmd
        if command in DEPRECATED_COMMAND_ALIASES:
            used_deprecated_alias = DEPRECATED_COMMAND_ALIASES[command][1]

    return ParsedArgs(
        command=command,
        used_deprecated_alias=used_deprecated_alias,
        debug=getattr(ns, "debug", False),
        config_file_path=getattr(ns, "config_file_path", ""),
        config_override=getattr(ns, "config_override", []),
        text=getattr(ns, "text", []),
        template=getattr(ns, "template", None),
        on_date=getattr(ns, "on_date", None),
        today_in_history=getattr(ns, "today_in_history", False),
        month=getattr(ns, "month", None),
        day=getattr(ns, "day", None),
        year=getattr(ns, "year", None),
        start_date=getattr(ns, "start_date", None),
        end_date=getattr(ns, "end_date", None),
        contains=getattr(ns, "contains", None),
        strict=getattr(ns, "strict", False),
        starred=getattr(ns, "starred", False),
        tagged=getattr(ns, "tagged", False),
        limit=getattr(ns, "limit", None),
        excluded=getattr(ns, "excluded", []),
        exclude_starred=getattr(ns, "exclude_starred", False),
        exclude_tagged=getattr(ns, "exclude_tagged", False),
        edit=getattr(ns, "edit", False),
        delete=getattr(ns, "delete", False),
        change_time=getattr(ns, "change_time", None),
        export=getattr(ns, "export", False),
        tags=getattr(ns, "tags", False),
        short=getattr(ns, "short", False),
        filename=getattr(ns, "filename", None),
        password=getattr(ns, "password", None),
        keychain=getattr(ns, "keychain", True),
        keyring_available=getattr(ns, "keyring_available", True),
    )


def parse_args(args: list[str] = []) -> ParsedArgs:
    """
    Argument parsing that is doable before the config is available.
    Everything else goes into "text" for later parsing.
    """
    parser = argparse.ArgumentParser(
        formatter_class=WrappingFormatter,
        add_help=False,
        description="Collect your thoughts and notes without leaving the command line",
        epilog=textwrap.dedent(
            """
        We gratefully thank all contributors!
        Come see the whole list of code and financial contributors at https://github.com/jrnl-org/jrnl
        And special thanks to Bad Lip Reading for the Yoda joke in the Writing section above :)"""  # noqa: E501
        ),
    )

    optional = parser.add_argument_group("Optional Arguments")
    optional.add_argument(
        "--debug",
        dest="debug",
        action="store_true",
        help="Print information useful for troubleshooting",
    )

    standalone = parser.add_argument_group(
        "Standalone Commands",
        "These commands will exit after they complete. You may only run one at a time.",
    )
    standalone.add_argument("--help", action="help", help="Show this help message")
    standalone.add_argument("-h", action="help", help=argparse.SUPPRESS)
    standalone.add_argument(
        "--version",
        action="store_const",
        const="version",
        dest="preconfig_cmd",
        help="Print version information",
    )
    standalone.add_argument(
        "-v",
        action="store_const",
        const="version",
        dest="preconfig_cmd",
        help=argparse.SUPPRESS,
    )
    standalone.add_argument(
        "--diagnostic",
        action="store_const",
        const="diagnostic",
        dest="preconfig_cmd",
        help=argparse.SUPPRESS,
    )
    standalone.add_argument(
        "--list",
        action="store_const",
        const="list",
        dest="postconfig_cmd",
        help="""
        List all configured journals.

        Optional parameters:

        --format [json or yaml]
        """,
    )
    standalone.add_argument(
        "--ls",
        action="store_const",
        const="list",
        dest="postconfig_cmd",
        help=argparse.SUPPRESS,
    )
    standalone.add_argument(
        "-ls",
        action="store_const",
        const="list_deprecated",
        dest="postconfig_cmd",
        help=argparse.SUPPRESS,
    )
    standalone.add_argument(
        "--encrypt",
        help="Encrypt selected journal with a password",
        action="store_const",
        metavar="TYPE",
        const="encrypt",
        dest="postconfig_cmd",
    )
    standalone.add_argument(
        "--decrypt",
        help="Decrypt selected journal and store it in plain text",
        action="store_const",
        metavar="TYPE",
        const="decrypt",
        dest="postconfig_cmd",
    )
    standalone.add_argument(
        "--import",
        action="store_const",
        metavar="TYPE",
        const="import",
        dest="postconfig_cmd",
        help=f"""
        Import entries from another journal.

        Optional parameters:

        --file FILENAME (default: uses stdin)

        --format [{util.oxford_list(IMPORT_FORMATS)}] (default: jrnl)
        """,
    )
    standalone.add_argument(
        "--file",
        metavar="FILENAME",
        dest="filename",
        help=argparse.SUPPRESS,
        default=None,
    )
    standalone.add_argument("-i", dest="filename", help=argparse.SUPPRESS)

    compose_msg = """
    To add a new entry into your journal, simply write it on the command line:

        jrnl yesterday: I was walking and I found this big log.

    The date and the following colon ("yesterday:") are optional. If you leave
    them out, "now" will be used:

        jrnl Then I rolled the log over.

    Also, you can mark extra special entries ("star" them) with an asterisk:

        jrnl *And underneath was a tiny little stick.

    Please note that asterisks might be a special character in your shell, so you
    might have to escape them. When in doubt about escaping, put quotes around
    your entire entry:

        jrnl "saturday at 2am: *Then I was like 'That log had a child!'" """

    composing = parser.add_argument_group(
        "Writing", textwrap.dedent(compose_msg).strip()
    )
    composing.add_argument("text", metavar="", nargs="*")
    composing.add_argument(
        "--template",
        dest="template",
        help="Path to template file. Can be a local path, absolute path, or a path "
        "relative to $XDG_DATA_HOME/jrnl/templates/",
    )

    read_msg = (
        "To find entries from your journal, use any combination of the below filters."
    )
    reading = parser.add_argument_group("Searching", textwrap.dedent(read_msg))
    reading.add_argument(
        "-on", dest="on_date", metavar="DATE", help="Show entries on this date"
    )
    reading.add_argument(
        "-today-in-history",
        dest="today_in_history",
        action="store_true",
        help="Show entries of today over the years",
    )
    reading.add_argument(
        "-month",
        dest="month",
        metavar="DATE",
        help="Show entries on this month of any year",
    )
    reading.add_argument(
        "-day",
        dest="day",
        metavar="DATE",
        help="Show entries on this day of any month",
    )
    reading.add_argument(
        "-year",
        dest="year",
        metavar="DATE",
        help="Show entries of a specific year",
    )
    reading.add_argument(
        "-from",
        dest="start_date",
        metavar="DATE",
        help="Show entries after, or on, this date",
    )
    reading.add_argument(
        "-to",
        dest="end_date",
        metavar="DATE",
        help="Show entries before, or on, this date (alias: -until)",
    )
    reading.add_argument("-until", dest="end_date", help=argparse.SUPPRESS)
    reading.add_argument(
        "-contains",
        dest="contains",
        action="append",
        metavar="TEXT",
        help="Show entries containing specific text (put quotes around text with "
        "spaces)",
    )
    reading.add_argument(
        "-and",
        dest="strict",
        action="store_true",
        help='Show only entries that match all conditions, like saying "x AND y" '
        "(default: OR)",
    )
    reading.add_argument(
        "-starred",
        dest="starred",
        action="store_true",
        help="Show only starred entries (marked with *)",
    )
    reading.add_argument(
        "-tagged",
        dest="tagged",
        action="store_true",
        help="Show only entries that have at least one tag",
    )
    reading.add_argument(
        "-n",
        dest="limit",
        default=None,
        metavar="NUMBER",
        help="Show a maximum of NUMBER entries (note: '-n 3' and '-3' have the same "
        "effect)",
        nargs="?",
        type=int,
    )
    reading.add_argument(
        "-not",
        dest="excluded",
        nargs="?",
        default=[],
        metavar="TAG/FLAG",
        action=IgnoreNoneAppendAction,
        help=(
            "If passed a string, will exclude entries with that tag. "
            "Can be also used before -starred or -tagged flags, to exclude "
            "starred or tagged entries respectively."
        ),
    )

    search_options_msg = (
        "    "  # Preserves indentation
        """
        These help you do various tasks with the selected entries from your search.
        If used on their own (with no search), they will act on your entire journal"""
    )
    exporting = parser.add_argument_group(
        "Searching Options", textwrap.dedent(search_options_msg)
    )
    exporting.add_argument(
        "--edit",
        dest="edit",
        help="Opens the selected entries in your configured editor",
        action="store_true",
    )
    exporting.add_argument(
        "--delete",
        dest="delete",
        action="store_true",
        help="Interactively deletes selected entries",
    )
    exporting.add_argument(
        "--change-time",
        dest="change_time",
        nargs="?",
        metavar="DATE",
        const="now",
        help="Change timestamp for selected entries (default: now)",
    )
    exporting.add_argument(
        "--format",
        metavar="TYPE",
        dest="export",
        choices=EXPORT_FORMATS,
        help=f"""
        Display selected entries in an alternate format.

        TYPE can be: {util.oxford_list(EXPORT_FORMATS)}.

        Optional parameters:

        --file FILENAME Write output to file instead of stdout
        """,
        default=False,
    )
    exporting.add_argument(
        "--export",
        metavar="TYPE",
        dest="export",
        choices=EXPORT_FORMATS,
        help=argparse.SUPPRESS,
    )
    exporting.add_argument(
        "--tags",
        dest="tags",
        action="store_true",
        help="Alias for '--format tags'. Returns a list of all tags and number of "
        "occurrences",
    )
    exporting.add_argument(
        "--short",
        dest="short",
        action="store_true",
        help="Show only titles or line containing the search tags",
    )
    exporting.add_argument(
        "-s",
        dest="short",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    exporting.add_argument(
        "-o",
        dest="filename",
        help=argparse.SUPPRESS,
    )

    config_overrides = parser.add_argument_group(
        "Config file override",
        textwrap.dedent("Apply a one-off override of the config file option"),
    )
    config_overrides.add_argument(
        "--config-override",
        dest="config_override",
        action="append",
        type=str,
        nargs=2,
        default=[],
        metavar="CONFIG_KV_PAIR",
        help="""
        Override configured key-value pair with CONFIG_KV_PAIR for this command invocation only.

        Examples: \n
        \t - Use a different editor for this jrnl entry, call: \n
            \t jrnl --config-override editor "nano" \n
        \t - Override color selections\n
           \t jrnl --config-override colors.body blue --config-override colors.title green
        """,  # noqa: E501
    )
    config_overrides.add_argument(
        "--co",
        dest="config_override",
        action="append",
        type=str,
        nargs=2,
        default=[],
        help=argparse.SUPPRESS,
    )

    alternate_config = parser.add_argument_group(
        "Specifies alternate config to be used",
        textwrap.dedent("Applies alternate config for current session"),
    )

    alternate_config.add_argument(
        "--config-file",
        dest="config_file_path",
        type=str,
        default="",
        help="""
        Overrides default (created when first installed) config file for this command only.

        Examples: \n
        \t - Use a work config file for this jrnl entry, call: \n
            \t jrnl --config-file /home/user1/work_config.yaml
        \t - Use a personal config file stored on a thumb drive: \n
            \t jrnl --config-file /media/user1/my-thumb-drive/personal_config.yaml
        """,  # noqa: E501
    )

    alternate_config.add_argument(
        "--cf", dest="config_file_path", type=str, default="", help=argparse.SUPPRESS
    )

    # Handle '-123' as a shortcut for '-n 123'
    num = re.compile(r"^-(\d+)$")
    args = [num.sub(r"-n \1", arg) for arg in args]
    ns = parser.parse_intermixed_args(args)
    ns = parse_not_arg(args, ns, parser)

    return _namespace_to_parsed_args(ns)
