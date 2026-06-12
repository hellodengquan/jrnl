# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import os
import re
import shutil
from io import StringIO
from unittest.mock import patch

import pytest
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


CHINESE_TRANSLATIONS = {
    "DoctorTitle": "jrnl 配置体检",
    "DoctorSectionJournal": "日记路径",
    "DoctorSectionEditor": "编辑器",
    "DoctorSectionTemplate": "模板",
    "DoctorGroupFatal": "致命问题（必须修复）",
    "DoctorGroupWarning": "警告（建议修复）",
    "DoctorGroupInfo": "提示（可选）",
    "DoctorAllOk": "所有检查通过！您的配置状态良好。",
    "DoctorCategoryLabel": "类别",
    "DoctorIssueLabel": "问题",
    "DoctorSuggestionLabel": "建议",
    "DoctorJournalPathOK": "日记路径已存在：{path}",
    "DoctorJournalPathNotFound": "未找到日记路径：{path}",
    "DoctorJournalPathNotWritable": "日记路径不可写：{path}",
    "DoctorJournalPathIsDir": "日记路径是一个目录：{path}",
    "DoctorJournalPathSuggestion": (
        "请检查配置文件中的 'journal' 路径，"
        "并确保它指向一个有效的文件。"
    ),
    "DoctorEditorOK": "编辑器可用：{editor}",
    "DoctorEditorNotSet": "未配置编辑器",
    "DoctorEditorNotFound": "未找到编辑器：{editor}",
    "DoctorEditorNotSetSuggestion": (
        "请在配置文件中设置编辑器，"
        "或者设置 VISUAL 或 EDITOR 环境变量。"
    ),
    "DoctorEditorNotFoundSuggestion": (
        "请安装 '{editor}' 或更新您的配置"
        "以使用其他编辑器。"
    ),
    "DoctorEncryptionOK": "加密依赖均可用",
    "DoctorEncryptionCryptographyMissing": "未安装 'cryptography' 包。",
    "DoctorEncryptionKeyringMissing": "未安装 'keyring' 包。",
    "DoctorEncryptionKeyringNoBackend": (
        "没有可用的 keyring 后端，密码将无法安全存储。"
    ),
    "DoctorEncryptionSuggestion": (
        "请使用 'pip install cryptography keyring' "
        "安装缺失的依赖。"
    ),
    "DoctorEncryptionKeyringSuggestion": (
        "请为您的系统安装合适的 keyring 后端。"
    ),
    "DoctorTemplateOK": "模板文件已存在：{path}",
    "DoctorTemplateNotSet": "未配置模板",
    "DoctorTemplateNotFound": "未找到模板文件：{path}",
    "DoctorTemplateNotReadable": "模板文件不可读：{path}",
    "DoctorTemplateSuggestion": (
        "请检查配置文件中的 'template' 路径，"
        "如果不需要可以删除该配置。"
    ),
    "DoctorTemplateNotFoundSuggestion": (
        "请在 {path} 创建模板文件，"
        "或更新配置以指向已存在的文件。"
    ),
    "DoctorSummary": "汇总：{ok} 项通过，{warning} 项警告，{error} 项致命问题",
}

JAPANESE_TRANSLATIONS = {
    "DoctorTitle": "jrnl 設定ヘルスチェック",
    "DoctorSectionJournal": "ジャーナルパス",
    "DoctorSectionEditor": "エディタ",
    "DoctorSectionTemplate": "テンプレート",
    "DoctorGroupFatal": "致命的問題（要修正）",
    "DoctorGroupWarning": "警告（推奨修正）",
    "DoctorGroupInfo": "情報（任意）",
    "DoctorAllOk": "すべてのチェックに合格しました！",
    "DoctorCategoryLabel": "カテゴリ",
    "DoctorIssueLabel": "問題",
    "DoctorSuggestionLabel": "提案",
    "DoctorJournalPathOK": "ジャーナルパスが存在します：{path}",
    "DoctorJournalPathNotFound": "ジャーナルパスが見つかりません：{path}",
    "DoctorJournalPathNotWritable": "ジャーナルパスは書き込み不可：{path}",
    "DoctorJournalPathIsDir": "ジャーナルパスはディレクトリです：{path}",
    "DoctorJournalPathSuggestion": (
        "設定ファイルの 'journal' パスを確認し、"
        "有効なファイルを指していることを確認してください。"
    ),
    "DoctorEditorOK": "エディタが利用可能です：{editor}",
    "DoctorEditorNotSet": "エディタが設定されていません",
    "DoctorEditorNotFound": "エディタが見つかりません：{editor}",
    "DoctorEditorNotSetSuggestion": (
        "設定ファイルでエディタを指定するか、"
        "VISUAL または EDITOR 環境変数を設定してください。"
    ),
    "DoctorEditorNotFoundSuggestion": (
        "'{editor}' をインストールするか、"
        "別のエディタを使用するように設定を更新してください。"
    ),
    "DoctorEncryptionOK": "暗号化依存関係が利用可能です",
    "DoctorEncryptionCryptographyMissing": (
        "'cryptography' パッケージが未インストールです。"
    ),
    "DoctorEncryptionKeyringMissing": (
        "'keyring' パッケージが未インストールです。"
    ),
    "DoctorEncryptionKeyringNoBackend": (
        "keyring バックエンドがありません。パスワードは安全に保存されません。"
    ),
    "DoctorEncryptionSuggestion": (
        "'pip install cryptography keyring' で不足している依存関係を"
        "インストールしてください。"
    ),
    "DoctorEncryptionKeyringSuggestion": (
        "システムに適した keyring バックエンドをインストールしてください。"
    ),
    "DoctorTemplateOK": "テンプレートファイルが存在します：{path}",
    "DoctorTemplateNotSet": "テンプレート未設定",
    "DoctorTemplateNotFound": "テンプレートファイルが見つかりません：{path}",
    "DoctorTemplateNotReadable": "テンプレートファイルが読み取れません：{path}",
    "DoctorTemplateSuggestion": (
        "設定ファイルの 'template' パスを確認するか、"
        "不要な場合は削除してください。"
    ),
    "DoctorTemplateNotFoundSuggestion": (
        "{path} にテンプレートファイルを作成するか、"
        "既存のファイルを指すように設定を更新してください。"
    ),
    "DoctorSummary": (
        "集計：{ok} 件合格、{warning} 件警告、{error} 件致命的問題"
    ),
}


def _apply_msgtext_overrides(monkeypatch, overrides: dict[str, str]):
    """Override MsgText enum member values for i18n testing."""
    for name, value in overrides.items():
        member = getattr(MsgText, name)
        monkeypatch.setattr(member, "_value_", value)


class TestDoctorI18nPrimaryLanguage:
    """Primary (English) language: doctor output should be readable and complete."""

    def test_default_english_render_has_all_sections(self):
        results = _run_doctor_checks(
            _make_config(
                journal="/nonexistent_dir/sub/journal.txt",
                editor="",
                template="nonexistent.template",
            )
        )
        output = _render_to_string(results, no_color=True)

        assert MsgText.DoctorTitle.value in output
        assert MsgText.DoctorGroupFatal.value in output
        assert MsgText.DoctorGroupWarning.value in output
        assert MsgText.DoctorGroupInfo.value in output
        assert MsgText.DoctorCategoryLabel.value in output
        assert MsgText.DoctorIssueLabel.value in output
        summary = MsgText.DoctorSummary.value
        assert "passed" in summary
        assert "warning" in summary
        assert "fatal" in summary

    def test_default_english_has_non_empty_suggestions(self):
        level, msg, suggestion = _check_editor("")
        assert suggestion != ""
        assert isinstance(suggestion, str)
        assert len(suggestion.strip()) > 0

        level, msg, suggestion = _check_editor("no_such_editor_xyz")
        assert suggestion != ""

    def test_default_english_format_placeholders_work(self):
        fmt = MsgText.DoctorJournalPathNotFound.value
        formatted = fmt.format(path="/foo/bar.txt")
        assert "/foo/bar.txt" in formatted

        fmt = MsgText.DoctorEditorNotFoundSuggestion.value
        formatted = fmt.format(editor="vim")
        assert "vim" in formatted


class TestDoctorI18nNonDefaultLanguage:
    """Non-default language: translated messages should appear in output."""

    def test_chinese_translation_render(self, monkeypatch):
        _apply_msgtext_overrides(monkeypatch, CHINESE_TRANSLATIONS)

        results = _run_doctor_checks(
            _make_config(
                journal="/nonexistent_dir/sub/journal.txt",
                editor="",
                template="nonexistent.template",
            )
        )
        output = _render_to_string(results, no_color=True)

        assert "jrnl 配置体检" in output
        assert "致命问题（必须修复）" in output
        assert "警告（建议修复）" in output
        assert "提示（可选）" in output
        assert "类别" in output
        assert "问题" in output
        assert "建议" in output
        assert "未配置编辑器" in output or "未找到编辑器" in output

    def test_chinese_format_placeholders_preserved(self, monkeypatch):
        _apply_msgtext_overrides(monkeypatch, CHINESE_TRANSLATIONS)

        level, msg, suggestion = _check_journal_path(
            "/nonexistent_xyz/test.txt"
        )
        assert "/nonexistent_xyz/test.txt" in msg

        level, msg, suggestion = _check_editor("weird_editor_xyz")
        assert "weird_editor_xyz" in msg

    def test_non_default_language_render_output_stable(self, monkeypatch):
        _apply_msgtext_overrides(monkeypatch, CHINESE_TRANSLATIONS)

        results = [
            {
                "category": MsgText.DoctorSectionJournal.value,
                "level": "error",
                "message": MsgText.DoctorJournalPathNotFound.value.format(
                    path="/a/b.txt"
                ),
                "suggestion": MsgText.DoctorJournalPathSuggestion.value,
            },
            {
                "category": MsgText.DoctorSectionEditor.value,
                "level": "warning",
                "message": MsgText.DoctorEditorNotSet.value,
                "suggestion": MsgText.DoctorEditorNotSetSuggestion.value,
            },
            {
                "category": "Encryption",
                "level": "ok",
                "message": MsgText.DoctorEncryptionOK.value,
                "suggestion": "",
            },
        ]
        output = _render_to_string(results, no_color=True)

        assert ANSI_ESCAPE_RE.search(output) is None
        assert output.strip() != ""
        assert "致命问题" in output
        assert "警告" in output
        assert "提示" in output


class TestDoctorI18nMissingTranslation:
    """Missing/partial translations: output must be readable and not crash."""

    def test_partial_translation_still_outputs_english_fallback(self, monkeypatch):
        partial = {
            "DoctorTitle": "jrnl 配置体检",
            "DoctorGroupFatal": "致命问题（必须修复）",
        }
        _apply_msgtext_overrides(monkeypatch, partial)

        results = [
            {
                "category": MsgText.DoctorSectionJournal.value,
                "level": "error",
                "message": "Something broke",
                "suggestion": "Fix it",
            },
        ]
        output = _render_to_string(results, no_color=True)

        assert "jrnl 配置体检" in output
        assert "致命问题（必须修复）" in output
        assert MsgText.DoctorCategoryLabel.value in output
        assert "Something broke" in output

    def test_empty_string_message_does_not_crash(self, monkeypatch):
        overrides = {
            "DoctorEditorNotSet": "",
            "DoctorEditorNotSetSuggestion": "",
        }
        _apply_msgtext_overrides(monkeypatch, overrides)

        try:
            level, msg, suggestion = _check_editor("")
        except Exception as exc:  # pragma: no cover
            pytest.fail(
                f"_check_editor crashed with empty translation: {exc}"
            )

        assert isinstance(msg, str)
        assert isinstance(suggestion, str)

    def test_format_placeholder_missing_from_translation_no_crash(
        self, monkeypatch
    ):
        overrides = {
            "DoctorJournalPathNotFound": "找不到日记路径（翻译漏了占位符）",
        }
        _apply_msgtext_overrides(monkeypatch, overrides)

        level, msg, suggestion = _check_journal_path("/tmp/x/y/z.txt")
        assert level in ("ok", "warning", "error")
        assert isinstance(msg, str)

    def test_all_messages_present_in_default(self):
        """Every Doctor* message member must have a non-empty default value."""
        doctor_members = [
            m for m in MsgText if m.name.startswith("Doctor")
        ]
        assert len(doctor_members) >= 25, (
            f"Expected at least 25 Doctor* message members, "
            f"found {len(doctor_members)}"
        )
        for member in doctor_members:
            value = member.value
            assert isinstance(value, str), (
                f"{member.name} value must be str, got {type(value).__name__}"
            )
            assert value.strip() != "", (
                f"{member.name} default value must not be empty"
            )

    def test_format_messages_contain_expected_placeholders(self):
        """Messages that use .format() must contain the expected placeholders."""
        expectation = {
            "DoctorJournalPathOK": ["{path}"],
            "DoctorJournalPathNotFound": ["{path}"],
            "DoctorJournalPathNotWritable": ["{path}"],
            "DoctorJournalPathIsDir": ["{path}"],
            "DoctorEditorOK": ["{editor}"],
            "DoctorEditorNotFound": ["{editor}"],
            "DoctorEditorNotFoundSuggestion": ["{editor}"],
            "DoctorTemplateOK": ["{path}"],
            "DoctorTemplateNotFound": ["{path}"],
            "DoctorTemplateNotReadable": ["{path}"],
            "DoctorTemplateNotFoundSuggestion": ["{path}"],
            "DoctorSummary": ["{ok}", "{warning}", "{error}"],
        }
        for name, placeholders in expectation.items():
            value = getattr(MsgText, name).value
            for ph in placeholders:
                assert ph in value, (
                    f"MsgText.{name} is missing placeholder {ph!r}"
                )

    def test_render_with_missing_category_label_graceful(self, monkeypatch):
        _apply_msgtext_overrides(
            monkeypatch, {"DoctorCategoryLabel": "", "DoctorIssueLabel": ""}
        )
        results = [
            {
                "category": "Journal Path",
                "level": "error",
                "message": "some fatal issue",
                "suggestion": "fix it please",
            },
        ]
        output = _render_to_string(results, no_color=True)
        assert isinstance(output, str)
        assert "some fatal issue" in output
        assert "fix it please" in output


MIXED_RESULTS = [
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


def _assert_group_order(output, fatal_text, warn_text, info_text):
    """Assert Fatal group appears before Warning group before Info group."""
    fatal_pos = output.find(fatal_text)
    warn_pos = output.find(warn_text)
    info_pos = output.find(info_text)

    assert fatal_pos != -1, (
        f"Fatal group {fatal_text!r} must be present in output"
    )
    assert warn_pos != -1, (
        f"Warning group {warn_text!r} must be present in output"
    )
    assert info_pos != -1, (
        f"Info group {info_text!r} must be present in output"
    )
    assert fatal_pos < warn_pos, (
        f"Fatal group ({fatal_text!r} at pos {fatal_pos}) must appear "
        f"before Warning group ({warn_text!r} at pos {warn_pos})"
    )
    assert warn_pos < info_pos, (
        f"Warning group ({warn_text!r} at pos {warn_pos}) must appear "
        f"before Info group ({info_text!r} at pos {info_pos})"
    )


class TestDoctorI18nGroupOrder:
    """Group ordering must remain Fatal→Warning→Info across all locales."""

    def test_chinese_fatal_before_warning_before_info(self, monkeypatch):
        _apply_msgtext_overrides(monkeypatch, CHINESE_TRANSLATIONS)
        output = _render_to_string(MIXED_RESULTS, no_color=True)
        _assert_group_order(
            output,
            "致命问题（必须修复）",
            "警告（建议修复）",
            "提示（可选）",
        )

    def test_japanese_fatal_before_warning_before_info(self, monkeypatch):
        _apply_msgtext_overrides(monkeypatch, JAPANESE_TRANSLATIONS)
        output = _render_to_string(MIXED_RESULTS, no_color=True)
        _assert_group_order(
            output,
            "致命的問題（要修正）",
            "警告（推奨修正）",
            "情報（任意）",
        )

    def test_english_fatal_before_warning_before_info(self):
        output = _render_to_string(MIXED_RESULTS, no_color=True)
        _assert_group_order(
            output,
            MsgText.DoctorGroupFatal.value,
            MsgText.DoctorGroupWarning.value,
            MsgText.DoctorGroupInfo.value,
        )

    def test_partial_translation_order_still_stable(self, monkeypatch):
        partial = {
            "DoctorGroupFatal": "严重错误",
            "DoctorGroupWarning": "警告（建议修复）",
            "DoctorGroupInfo": "提示（可选）",
        }
        _apply_msgtext_overrides(monkeypatch, partial)
        output = _render_to_string(MIXED_RESULTS, no_color=True)
        _assert_group_order(
            output,
            "严重错误",
            "警告（建议修复）",
            "提示（可选）",
        )

    def test_sequential_language_switch_order_consistent(self, monkeypatch):
        """Switch language mid-session: ordering must not drift."""
        en_fatal = MsgText.DoctorGroupFatal.value
        en_warn = MsgText.DoctorGroupWarning.value
        en_info = MsgText.DoctorGroupInfo.value

        output_en = _render_to_string(MIXED_RESULTS, no_color=True)
        _assert_group_order(output_en, en_fatal, en_warn, en_info)

        _apply_msgtext_overrides(monkeypatch, CHINESE_TRANSLATIONS)
        output_cn = _render_to_string(MIXED_RESULTS, no_color=True)
        _assert_group_order(
            output_cn,
            "致命问题（必须修复）",
            "警告（建议修复）",
            "提示（可选）",
        )

        monkeypatch.undo()
        output_en2 = _render_to_string(MIXED_RESULTS, no_color=True)
        _assert_group_order(output_en2, en_fatal, en_warn, en_info)

        en_order = (
            output_en.find(en_fatal),
            output_en.find(en_warn),
            output_en.find(en_info),
        )
        en2_order = (
            output_en2.find(en_fatal),
            output_en2.find(en_warn),
            output_en2.find(en_info),
        )
        assert en_order == en2_order, (
            f"Order changed after locale round-trip: "
            f"{en_order} != {en2_order}"
        )

    def test_level_prefix_labels_consistent_across_locales(
        self, monkeypatch
    ):
        """Severity level prefix (FATAL/WARNING/INFO) must map
        to the same group regardless of locale."""
        _apply_msgtext_overrides(monkeypatch, CHINESE_TRANSLATIONS)
        output = _render_to_string(MIXED_RESULTS, no_color=True)

        fatal_pos = output.find("致命问题（必须修复）")
        warn_pos = output.find("警告（建议修复）")

        error_msgs_near_fatal = [
            r["message"] for r in MIXED_RESULTS if r["level"] == "error"
        ]
        for msg in error_msgs_near_fatal:
            msg_pos = output.find(msg)
            assert msg_pos != -1, f"{msg!r} not found in output"
            assert fatal_pos < msg_pos, (
                f"Error message {msg!r} should appear inside "
                f"the Fatal group, but appears before it"
            )

        warn_msgs_near_warn = [
            r["message"] for r in MIXED_RESULTS if r["level"] == "warning"
        ]
        for msg in warn_msgs_near_warn:
            msg_pos = output.find(msg)
            assert msg_pos != -1, f"{msg!r} not found in output"
            assert warn_pos < msg_pos, (
                f"Warning message {msg!r} should appear inside "
                f"the Warning group, but appears before it"
            )

    def test_two_locales_produce_same_structural_order(self, monkeypatch):
        """Structural positions of groups relative to each other
        must be identical in Chinese and Japanese."""
        _apply_msgtext_overrides(monkeypatch, CHINESE_TRANSLATIONS)
        cn_output = _render_to_string(MIXED_RESULTS, no_color=True)
        cn_fatal = cn_output.find("致命问题（必须修复）")
        cn_warn = cn_output.find("警告（建议修复）")
        cn_info = cn_output.find("提示（可选）")

        monkeypatch.undo()

        _apply_msgtext_overrides(monkeypatch, JAPANESE_TRANSLATIONS)
        jp_output = _render_to_string(MIXED_RESULTS, no_color=True)
        jp_fatal = jp_output.find("致命的問題（要修正）")
        jp_warn = jp_output.find("警告（推奨修正）")
        jp_info = jp_output.find("情報（任意）")

        cn_rel = (
            cn_fatal < cn_warn < cn_info,
        )
        jp_rel = (
            jp_fatal < jp_warn < jp_info,
        )
        assert cn_rel == jp_rel, (
            f"Relative group order differs between locales: "
            f"CN={cn_rel}, JP={jp_rel}"
        )

    def test_only_fatal_and_warning_order_under_chinese(self, monkeypatch):
        _apply_msgtext_overrides(monkeypatch, CHINESE_TRANSLATIONS)
        results = [
            {
                "category": "Editor",
                "level": "error",
                "message": "err",
                "suggestion": "",
            },
            {
                "category": "Journal Path",
                "level": "warning",
                "message": "warn",
                "suggestion": "",
            },
        ]
        output = _render_to_string(results, no_color=True)
        fatal_pos = output.find("致命问题（必须修复）")
        warn_pos = output.find("警告（建议修复）")

        assert fatal_pos != -1
        assert warn_pos != -1
        assert fatal_pos < warn_pos
        assert "提示（可选）" not in output
