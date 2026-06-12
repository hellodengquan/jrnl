# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import os
import re
import shutil
from io import StringIO
from unittest.mock import patch

from rich.console import Console

from jrnl.commands import _check_editor
from jrnl.commands import _check_encryption_dependencies
from jrnl.commands import _check_journal_path
from jrnl.commands import _check_template
from jrnl.commands import _render_doctor_results
from jrnl.commands import _run_doctor_checks
from jrnl.messages import MsgText

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def _make_config(
    journal="/tmp/test_journal.txt",
    editor="nano",
    encrypt=False,
    template=False,
):
    return {
        "journal": journal,
        "editor": editor,
        "encrypt": encrypt,
        "template": template,
    }


def _render_to_string(results, no_color=False):
    buf = StringIO()
    console = Console(
        file=buf, no_color=no_color, width=120, legacy_windows=False
    )
    _render_doctor_results(console, results)
    return buf.getvalue()


class TestDoctorGroupOrder:
    """Fatal before Warning before Info in output order."""

    def test_fatal_before_warning_before_info(self):
        results = [
            {
                "category": "A",
                "level": "ok",
                "message": "ok msg",
                "suggestion": "",
            },
            {
                "category": "B",
                "level": "error",
                "message": "err msg",
                "suggestion": "fix it",
            },
            {
                "category": "C",
                "level": "warning",
                "message": "warn msg",
                "suggestion": "check it",
            },
        ]
        output = _render_to_string(results, no_color=True)

        fatal_pos = output.find(MsgText.DoctorGroupFatal.value)
        warn_pos = output.find(MsgText.DoctorGroupWarning.value)
        info_pos = output.find(MsgText.DoctorGroupInfo.value)

        assert fatal_pos != -1, "Fatal group must be present"
        assert warn_pos != -1, "Warning group must be present"
        assert info_pos != -1, "Info group must be present"
        assert fatal_pos < warn_pos, (
            "Fatal group must appear before Warning group"
        )
        assert warn_pos < info_pos, (
            "Warning group must appear before Info group"
        )

    def test_only_fatal_and_warning_shown_when_no_info(self):
        results = [
            {
                "category": "A",
                "level": "error",
                "message": "err",
                "suggestion": "",
            },
            {
                "category": "B",
                "level": "warning",
                "message": "warn",
                "suggestion": "",
            },
        ]
        output = _render_to_string(results, no_color=True)

        assert MsgText.DoctorGroupFatal.value in output
        assert MsgText.DoctorGroupWarning.value in output
        assert MsgText.DoctorGroupInfo.value not in output

    def test_all_ok_panel_when_no_issues(self):
        results = [
            {
                "category": "A",
                "level": "ok",
                "message": "ok msg",
                "suggestion": "",
            },
            {
                "category": "B",
                "level": "ok",
                "message": "ok msg 2",
                "suggestion": "",
            },
        ]
        output = _render_to_string(results, no_color=True)

        assert MsgText.DoctorAllOk.value in output
        assert MsgText.DoctorGroupFatal.value not in output
        assert MsgText.DoctorGroupWarning.value not in output
        assert MsgText.DoctorGroupInfo.value not in output

    def test_info_group_shown_alongside_issues(self):
        results = [
            {
                "category": "A",
                "level": "error",
                "message": "err",
                "suggestion": "",
            },
            {
                "category": "B",
                "level": "ok",
                "message": "ok",
                "suggestion": "",
            },
        ]
        output = _render_to_string(results, no_color=True)

        assert MsgText.DoctorGroupFatal.value in output
        assert MsgText.DoctorGroupInfo.value in output

    def test_only_warnings_no_fatal(self):
        results = [
            {
                "category": "A",
                "level": "warning",
                "message": "warn",
                "suggestion": "",
            },
        ]
        output = _render_to_string(results, no_color=True)

        assert MsgText.DoctorGroupWarning.value in output
        assert MsgText.DoctorGroupFatal.value not in output


class TestDoctorSeverityCounts:
    """Summary line must reflect the correct counts of each severity."""

    def test_summary_with_fatal(self):
        results = [
            {
                "category": "A",
                "level": "error",
                "message": "err",
                "suggestion": "",
            },
            {
                "category": "B",
                "level": "warning",
                "message": "warn",
                "suggestion": "",
            },
            {
                "category": "C",
                "level": "ok",
                "message": "ok",
                "suggestion": "",
            },
        ]
        output = _render_to_string(results, no_color=True)
        summary = MsgText.DoctorSummary.value.format(
            ok=1, warning=1, error=1
        )
        assert summary in output

    def test_summary_all_ok(self):
        results = [
            {
                "category": "A",
                "level": "ok",
                "message": "ok",
                "suggestion": "",
            },
        ]
        output = _render_to_string(results, no_color=True)
        summary = MsgText.DoctorSummary.value.format(
            ok=1, warning=0, error=0
        )
        assert summary in output


class TestDoctorNoColorDegradation:
    """NO_COLOR mode must produce plain text without ANSI escape sequences."""

    def test_no_color_no_ansi_sequences(self):
        results = [
            {
                "category": "A",
                "level": "error",
                "message": "fatal issue",
                "suggestion": "fix it",
            },
            {
                "category": "B",
                "level": "warning",
                "message": "warn issue",
                "suggestion": "check",
            },
            {
                "category": "C",
                "level": "ok",
                "message": "info item",
                "suggestion": "",
            },
        ]
        output = _render_to_string(results, no_color=True)

        assert ANSI_ESCAPE_RE.search(output) is None, (
            f"NO_COLOR output must not contain ANSI sequences, "
            f"found: {ANSI_ESCAPE_RE.findall(output)}"
        )

    def test_no_color_preserves_content(self):
        results = [
            {
                "category": "Journal Path",
                "level": "error",
                "message": "path broken",
                "suggestion": "fix path",
            },
            {
                "category": "Editor",
                "level": "warning",
                "message": "no editor",
                "suggestion": "set editor",
            },
            {
                "category": "Encryption",
                "level": "ok",
                "message": "all good",
                "suggestion": "",
            },
        ]
        output = _render_to_string(results, no_color=True)

        assert "Journal Path" in output
        assert "path broken" in output
        assert "fix path" in output
        assert "Editor" in output
        assert "no editor" in output
        assert "Encryption" in output
        assert "all good" in output
        assert MsgText.DoctorGroupFatal.value in output
        assert MsgText.DoctorGroupWarning.value in output
        assert MsgText.DoctorGroupInfo.value in output

    def test_no_color_all_ok_still_readable(self):
        results = [
            {
                "category": "A",
                "level": "ok",
                "message": "ok",
                "suggestion": "",
            },
        ]
        output = _render_to_string(results, no_color=True)

        assert ANSI_ESCAPE_RE.search(output) is None
        assert MsgText.DoctorAllOk.value in output

    def test_no_color_env_var(self):
        results = [
            {
                "category": "A",
                "level": "error",
                "message": "err",
                "suggestion": "fix",
            },
        ]
        buf = StringIO()
        console = Console(
            file=buf,
            no_color=True,
            width=120,
            legacy_windows=False,
            _environ={"NO_COLOR": "1"},
        )
        _render_doctor_results(console, results)
        output = buf.getvalue()

        assert ANSI_ESCAPE_RE.search(output) is None

    def test_color_mode_produces_styled_output(self):
        results = [
            {
                "category": "A",
                "level": "error",
                "message": "err",
                "suggestion": "fix",
            },
        ]
        buf = StringIO()
        console = Console(
            file=buf,
            width=120,
            force_terminal=True,
            legacy_windows=False,
        )
        _render_doctor_results(console, results)
        output = buf.getvalue()

        assert ANSI_ESCAPE_RE.search(output) is not None, (
            "Color mode should produce ANSI sequences"
        )


class TestDoctorCheckJournalPath:
    def test_existing_writable_file(self, tmp_path):
        journal_file = tmp_path / "journal.txt"
        journal_file.write_text("entry")
        level, msg, suggestion = _check_journal_path(str(journal_file))
        assert level == "ok"
        assert str(journal_file) in msg
        assert suggestion == ""

    def test_file_not_found_parent_exists(self, tmp_path):
        journal_file = tmp_path / "journal.txt"
        level, msg, suggestion = _check_journal_path(str(journal_file))
        assert level == "ok"
        assert "file will be created on first write" in msg

    def test_file_not_found_parent_missing(self):
        level, msg, suggestion = _check_journal_path(
            "/nonexistent_dir/sub/journal.txt"
        )
        assert level == "warning"
        assert "not found" in msg

    def test_path_is_directory(self, tmp_path):
        level, msg, suggestion = _check_journal_path(str(tmp_path))
        assert level == "error"
        assert "directory" in msg

    def test_not_writable(self, tmp_path):
        journal_file = tmp_path / "journal.txt"
        journal_file.write_text("entry")
        os.chmod(str(journal_file), 0o444)
        level, msg, suggestion = _check_journal_path(str(journal_file))
        assert level == "error"
        assert "not writable" in msg


class TestDoctorCheckEditor:
    def test_editor_not_set(self):
        level, msg, suggestion = _check_editor("")
        assert level == "warning"
        assert "No editor configured" in msg

    def test_editor_found_in_path(self):
        level, msg, suggestion = _check_editor("nano")
        if shutil.which("nano"):
            assert level == "ok"
        else:
            assert level == "error"

    def test_editor_not_found(self):
        level, msg, suggestion = _check_editor(
            "nonexistent_editor_xyz_12345"
        )
        assert level == "error"
        assert "not found" in msg

    def test_editor_absolute_path_not_found(self):
        level, msg, suggestion = _check_editor(
            "/usr/local/bin/nonexistent_editor"
        )
        assert level == "error"


class TestDoctorCheckEncryption:
    def test_encryption_ok(self):
        level, msg, suggestion = _check_encryption_dependencies()
        try:
            import cryptography  # noqa: F401
            import keyring  # noqa: F401

            keyring.get_keyring()
            assert level == "ok"
        except (ImportError, keyring.errors.NoKeyringError):
            assert level in ("warning", "error")

    @patch("importlib.import_module", side_effect=ImportError("no cryptography"))
    def test_cryptography_missing(self, mock_import):
        pass


class TestDoctorCheckTemplate:
    def test_no_template(self):
        level, msg, suggestion = _check_template(False)
        assert level == "ok"
        assert "No template configured" in msg

    def test_template_not_found(self):
        level, msg, suggestion = _check_template(
            "nonexistent_template_xyz.template"
        )
        assert level == "error"
        assert "not found" in msg

    def test_template_exists(self, tmp_path):
        template_file = tmp_path / "test.template"
        template_file.write_text("template content")
        level, msg, suggestion = _check_template(str(template_file))
        assert level == "ok"


class TestDoctorRunChecks:
    """Integration: _run_doctor_checks returns results with expected keys."""

    def test_returns_four_results(self, tmp_path):
        journal_file = tmp_path / "journal.txt"
        config = _make_config(journal=str(journal_file), editor="nano")
        results = _run_doctor_checks(config)
        assert len(results) == 4
        for r in results:
            assert "category" in r
            assert "level" in r
            assert "message" in r
            assert "suggestion" in r
            assert r["level"] in ("ok", "warning", "error")

    def test_mixed_severity_bad_editor_missing_template(self, tmp_path):
        journal_file = tmp_path / "journal.txt"
        config = _make_config(
            journal=str(journal_file),
            editor="nonexistent_editor_xyz_12345",
            template="nonexistent.template",
        )
        results = _run_doctor_checks(config)
        levels = {r["category"]: r["level"] for r in results}
        assert levels.get("Editor") == "error"
        assert levels.get("Template") == "error"
