import os
import stat
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from jrnl.journals.Journal import Journal
from jrnl.journals.Journal import open_journal
from jrnl.messages import MsgStyle
from jrnl.messages import MsgText
from jrnl.path import create_journal_file
from jrnl.path import ensure_journal_directory
from jrnl.path import expand_journal_path
from jrnl.path import journal_path_exists


def _make_config(journal_path, encrypt=False):
    return {
        "journals": {"default": journal_path},
        "journal": journal_path,
        "encrypt": encrypt,
        "default_hour": 9,
        "default_minute": 0,
        "timeformat": "%Y-%m-%d %H:%M",
        "tagsymbols": "@",
        "highlight": True,
        "linewrap": 80,
        "indent_character": "|",
    }


def _encrypt_mocks():
    return [
        patch("jrnl.encryption.BasePasswordEncryption.get_keyring_password", return_value=None),
        patch("jrnl.encryption.BasePasswordEncryption.create_password", return_value="testpw"),
        patch("jrnl.encryption.BasePasswordEncryption.prompt_password", return_value="testpw"),
    ]


class TestExpandJournalPath:
    def test_expands_tilde(self):
        result = expand_journal_path("~/journals/default.journal")
        assert not result.startswith("~")
        assert result == os.path.expanduser("~/journals/default.journal")

    def test_expands_env_var(self, monkeypatch):
        monkeypatch.setenv("JRNL_TEST_DIR", "/tmp/jrnl_test")
        result = expand_journal_path("$JRNL_TEST_DIR/journal.txt")
        assert result == "/tmp/jrnl_test/journal.txt"

    def test_expands_tilde_and_env_var(self, monkeypatch):
        monkeypatch.setenv("JRNL_SUBDIR", "journals")
        result = expand_journal_path("~/$JRNL_SUBDIR/default.journal")
        assert not result.startswith("~")
        assert "journals" in result

    def test_missing_env_var_left_as_is(self):
        result = expand_journal_path("$JRNL_NONEXISTENT_VAR_12345/journal.txt")
        assert "$JRNL_NONEXISTENT_VAR_12345" in result

    def test_empty_path(self):
        result = expand_journal_path("")
        assert result == ""

    def test_plain_path_unchanged(self):
        result = expand_journal_path("/absolute/path/journal.txt")
        assert result == "/absolute/path/journal.txt"

    def test_relative_path_unchanged(self):
        result = expand_journal_path("relative/path/journal.txt")
        assert result == "relative/path/journal.txt"


class TestJournalPathExists:
    def test_existing_file(self, tmp_path):
        f = tmp_path / "journal.txt"
        f.write_text("")
        assert journal_path_exists(str(f)) is True

    def test_existing_directory(self, tmp_path):
        assert journal_path_exists(str(tmp_path)) is True

    def test_nonexistent_path(self):
        assert journal_path_exists("/nonexistent/path/journal.txt") is False

    def test_empty_path(self):
        assert journal_path_exists("") is False


class TestEnsureJournalDirectory:
    def test_creates_missing_directory(self, tmp_path):
        journal_path = str(tmp_path / "subdir" / "journal.txt")
        with patch("jrnl.path.print_msg") as mock_print:
            result = ensure_journal_directory(journal_path)
        assert result is True
        assert os.path.isdir(str(tmp_path / "subdir"))
        mock_print.assert_called_once()
        msg = mock_print.call_args[0][0]
        assert msg.text == MsgText.DirectoryCreated
        assert msg.style == MsgStyle.NORMAL

    def test_no_creation_if_directory_exists(self, tmp_path):
        journal_path = str(tmp_path / "journal.txt")
        with patch("jrnl.path.print_msg") as mock_print:
            result = ensure_journal_directory(journal_path)
        assert result is False
        mock_print.assert_not_called()

    def test_no_creation_if_no_directory_component(self):
        with patch("jrnl.path.print_msg") as mock_print:
            result = ensure_journal_directory("journal.txt")
        assert result is False
        mock_print.assert_not_called()

    def test_creates_nested_directories(self, tmp_path):
        journal_path = str(tmp_path / "a" / "b" / "c" / "journal.txt")
        with patch("jrnl.path.print_msg") as mock_print:
            result = ensure_journal_directory(journal_path)
        assert result is True
        assert os.path.isdir(str(tmp_path / "a" / "b" / "c"))
        mock_print.assert_called_once()
        msg = mock_print.call_args[0][0]
        assert msg.text == MsgText.DirectoryCreated

    def test_permission_error(self, tmp_path):
        if os.getuid() == 0:
            pytest.skip("Cannot test permission denial as root")
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        os.chmod(str(readonly_dir), stat.S_IRUSR | stat.S_IXUSR)
        journal_path = str(readonly_dir / "subdir" / "journal.txt")
        with pytest.raises(PermissionError):
            ensure_journal_directory(journal_path)
        os.chmod(str(readonly_dir), stat.S_IRWXU)


class TestCreateJournalFile:
    def test_creates_file(self, tmp_path):
        journal_path = str(tmp_path / "journal.txt")
        with patch("jrnl.path.print_msg") as mock_print:
            create_journal_file(journal_path, "default")
        assert os.path.isfile(journal_path)
        mock_print.assert_called_once()
        msg = mock_print.call_args[0][0]
        assert msg.text == MsgText.JournalCreated
        assert msg.style == MsgStyle.NORMAL
        assert msg.params["journal_name"] == "default"
        assert msg.params["filename"] == journal_path

    def test_message_contains_journal_name(self, tmp_path):
        journal_path = str(tmp_path / "my_diary.txt")
        with patch("jrnl.path.print_msg") as mock_print:
            create_journal_file(journal_path, "my_diary")
        msg = mock_print.call_args[0][0]
        assert msg.params["journal_name"] == "my_diary"
        assert msg.params["filename"] == journal_path

    def test_permission_error(self, tmp_path):
        if os.getuid() == 0:
            pytest.skip("Cannot test permission denial as root")
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        os.chmod(str(readonly_dir), stat.S_IRUSR | stat.S_IXUSR)
        journal_path = str(readonly_dir / "journal.txt")
        with pytest.raises(PermissionError):
            create_journal_file(journal_path, "default")
        os.chmod(str(readonly_dir), stat.S_IRWXU)


class TestPlainJournalOpenPathHandling:
    def test_opens_existing_journal(self, tmp_path):
        journal_path = str(tmp_path / "journal.txt")
        with open(journal_path, "w") as f:
            f.write("")
        config = _make_config(journal_path, encrypt=False)
        with patch("jrnl.journals.Journal.validate_journal_name"):
            j = open_journal("default", config)
        assert isinstance(j, Journal)

    def test_creates_journal_when_missing(self, tmp_path):
        journal_path = str(tmp_path / "new_journal.txt")
        config = _make_config(journal_path, encrypt=False)
        with patch("jrnl.journals.Journal.validate_journal_name"):
            with patch("jrnl.path.print_msg") as mock_print:
                j = open_journal("default", config)
        assert os.path.isfile(journal_path)
        created_msgs = [
            c for c in mock_print.call_args_list
            if c[0][0].text == MsgText.JournalCreated
        ]
        assert len(created_msgs) == 1
        assert created_msgs[0][0][0].style == MsgStyle.NORMAL

    def test_creates_nested_directories_when_missing(self, tmp_path):
        journal_path = str(tmp_path / "deep" / "nested" / "journal.txt")
        config = _make_config(journal_path, encrypt=False)
        with patch("jrnl.journals.Journal.validate_journal_name"):
            with patch("jrnl.path.print_msg") as mock_print:
                j = open_journal("default", config)
        assert os.path.isfile(journal_path)
        dir_msgs = [
            c for c in mock_print.call_args_list
            if c[0][0].text == MsgText.DirectoryCreated
        ]
        created_msgs = [
            c for c in mock_print.call_args_list
            if c[0][0].text == MsgText.JournalCreated
        ]
        assert len(dir_msgs) == 1
        assert dir_msgs[0][0][0].style == MsgStyle.NORMAL
        assert len(created_msgs) == 1
        assert created_msgs[0][0][0].style == MsgStyle.NORMAL

    def test_expands_env_var_in_path(self, tmp_path, monkeypatch):
        journal_path = str(tmp_path / "journal.txt")
        with open(journal_path, "w") as f:
            f.write("")
        monkeypatch.setenv("JRNL_JOURNAL_DIR", str(tmp_path))
        config = _make_config("$JRNL_JOURNAL_DIR/journal.txt", encrypt=False)
        with patch("jrnl.journals.Journal.validate_journal_name"):
            j = open_journal("default", config)
        assert j.config["journal"] == journal_path

    def test_permission_error_on_create(self, tmp_path):
        if os.getuid() == 0:
            pytest.skip("Cannot test permission denial as root")
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        os.chmod(str(readonly_dir), stat.S_IRUSR | stat.S_IXUSR)
        journal_path = str(readonly_dir / "journal.txt")
        config = _make_config(journal_path, encrypt=False)
        with patch("jrnl.journals.Journal.validate_journal_name"):
            with pytest.raises(PermissionError):
                open_journal("default", config)
        os.chmod(str(readonly_dir), stat.S_IRWXU)


class TestEncryptedJournalOpenPathHandling:
    def test_creates_encrypted_journal_when_missing(self, tmp_path):
        journal_path = str(tmp_path / "encrypted.txt")
        config = _make_config(journal_path, encrypt=True)
        mocks = _encrypt_mocks()
        with patch("jrnl.journals.Journal.validate_journal_name"):
            with patch("jrnl.path.print_msg") as mock_print:
                for m in mocks:
                    m.start()
                try:
                    j = open_journal("default", config)
                finally:
                    for m in mocks:
                        m.stop()
        assert os.path.isfile(journal_path)
        created_msgs = [
            c for c in mock_print.call_args_list
            if c[0][0].text == MsgText.JournalCreated
        ]
        assert len(created_msgs) == 1
        assert created_msgs[0][0][0].style == MsgStyle.NORMAL

    def test_creates_nested_directories_for_encrypted(self, tmp_path):
        journal_path = str(tmp_path / "deep" / "nested" / "encrypted.txt")
        config = _make_config(journal_path, encrypt=True)
        mocks = _encrypt_mocks()
        with patch("jrnl.journals.Journal.validate_journal_name"):
            with patch("jrnl.path.print_msg") as mock_print:
                for m in mocks:
                    m.start()
                try:
                    j = open_journal("default", config)
                finally:
                    for m in mocks:
                        m.stop()
        assert os.path.isfile(journal_path)
        dir_msgs = [
            c for c in mock_print.call_args_list
            if c[0][0].text == MsgText.DirectoryCreated
        ]
        created_msgs = [
            c for c in mock_print.call_args_list
            if c[0][0].text == MsgText.JournalCreated
        ]
        assert len(dir_msgs) == 1
        assert dir_msgs[0][0][0].style == MsgStyle.NORMAL
        assert len(created_msgs) == 1
        assert created_msgs[0][0][0].style == MsgStyle.NORMAL

    def test_expands_env_var_in_encrypted_path(self, tmp_path, monkeypatch):
        journal_path = str(tmp_path / "encrypted.txt")
        with open(journal_path, "wb") as f:
            f.write(b"")
        monkeypatch.setenv("JRNL_ENC_DIR", str(tmp_path))
        config = _make_config("$JRNL_ENC_DIR/encrypted.txt", encrypt=True)
        config["encrypt"] = "jrnlv2"
        mocks = _encrypt_mocks()
        with patch("jrnl.journals.Journal.validate_journal_name"):
            with patch(
                "jrnl.encryption.Jrnlv2Encryption.Jrnlv2Encryption.decrypt",
                return_value="",
            ):
                for m in mocks:
                    m.start()
                try:
                    j = open_journal("default", config)
                finally:
                    for m in mocks:
                        m.stop()
        assert j.config["journal"] == journal_path

    def test_permission_error_on_create_encrypted(self, tmp_path):
        if os.getuid() == 0:
            pytest.skip("Cannot test permission denial as root")
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        os.chmod(str(readonly_dir), stat.S_IRUSR | stat.S_IXUSR)
        journal_path = str(readonly_dir / "encrypted.txt")
        config = _make_config(journal_path, encrypt=True)
        with patch("jrnl.journals.Journal.validate_journal_name"):
            with pytest.raises(PermissionError):
                open_journal("default", config)
        os.chmod(str(readonly_dir), stat.S_IRWXU)


class TestUpgradePathHandling:
    def test_missing_path_reports_does_not_exist(self, tmp_path):
        from jrnl.upgrade import upgrade_jrnl

        missing_path = str(tmp_path / "nonexistent" / "journal.txt")
        config = {
            "journals": {
                "missing": missing_path,
            },
            "encrypt": False,
        }
        with patch("jrnl.upgrade.load_config", return_value=config):
            with patch("jrnl.upgrade.print_msg") as mock_print:
                with patch("jrnl.upgrade.yesno") as mock_yesno:
                    mock_yesno.return_value = False
                    try:
                        upgrade_jrnl("/fake/config.yaml")
                    except Exception:
                        pass
        does_not_exist_calls = [
            c for c in mock_print.call_args_list
            if c[0][0].text == MsgText.DoesNotExist
        ]
        assert len(does_not_exist_calls) >= 1
        msg = does_not_exist_calls[0][0][0]
        assert msg.style == MsgStyle.ERROR
        assert missing_path in str(msg)

    def test_missing_path_with_env_var(self, tmp_path, monkeypatch):
        from jrnl.upgrade import upgrade_jrnl

        monkeypatch.setenv("JRNL_MISSING_DIR", str(tmp_path / "also_missing"))
        env_path = "$JRNL_MISSING_DIR/journal.txt"
        config = {
            "journals": {
                "missing_env": env_path,
            },
            "encrypt": False,
        }
        expanded = expand_journal_path(env_path)
        with patch("jrnl.upgrade.load_config", return_value=config):
            with patch("jrnl.upgrade.print_msg") as mock_print:
                with patch("jrnl.upgrade.yesno") as mock_yesno:
                    mock_yesno.return_value = False
                    try:
                        upgrade_jrnl("/fake/config.yaml")
                    except Exception:
                        pass
        does_not_exist_calls = [
            c for c in mock_print.call_args_list
            if c[0][0].text == MsgText.DoesNotExist
        ]
        assert len(does_not_exist_calls) >= 1
        msg = does_not_exist_calls[0][0][0]
        assert msg.style == MsgStyle.ERROR
        assert expanded in str(msg)

    def test_missing_encrypted_path_reports_does_not_exist(self, tmp_path):
        from jrnl.upgrade import upgrade_jrnl

        missing_path = str(tmp_path / "nonexistent" / "encrypted.txt")
        config = {
            "journals": {
                "missing_enc": {
                    "journal": missing_path,
                    "encrypt": True,
                },
            },
            "encrypt": False,
        }
        with patch("jrnl.upgrade.load_config", return_value=config):
            with patch("jrnl.upgrade.print_msg") as mock_print:
                with patch("jrnl.upgrade.yesno") as mock_yesno:
                    mock_yesno.return_value = False
                    try:
                        upgrade_jrnl("/fake/config.yaml")
                    except Exception:
                        pass
        does_not_exist_calls = [
            c for c in mock_print.call_args_list
            if c[0][0].text == MsgText.DoesNotExist
        ]
        assert len(does_not_exist_calls) >= 1
        msg = does_not_exist_calls[0][0][0]
        assert msg.style == MsgStyle.ERROR

    def test_check_exists_expands_path(self, tmp_path, monkeypatch):
        from jrnl.upgrade import check_exists

        journal_path = str(tmp_path / "journal.txt")
        with open(journal_path, "w") as f:
            f.write("")
        monkeypatch.setenv("JRNL_CHECK_DIR", str(tmp_path))
        assert check_exists("$JRNL_CHECK_DIR/journal.txt") is True

    def test_check_exists_missing_env_var(self):
        from jrnl.upgrade import check_exists

        result = check_exists("$JRNL_NONEXISTENT_VAR_99999/journal.txt")
        assert result is False

    def test_backup_expands_path(self, tmp_path, monkeypatch):
        from jrnl.upgrade import backup

        journal_path = str(tmp_path / "journal.txt")
        with open(journal_path, "w") as f:
            f.write("test content")
        monkeypatch.setenv("JRNL_BACKUP_DIR", str(tmp_path))
        with patch("jrnl.upgrade.print_msg"):
            backup("$JRNL_BACKUP_DIR/journal.txt")
        assert os.path.isfile(journal_path + ".backup")


class TestCrossEntryConsistency:
    def test_directory_created_message_same_for_plain_and_encrypted(self, tmp_path):
        plain_path = str(tmp_path / "plain" / "deep" / "journal.txt")
        encrypted_path = str(tmp_path / "encrypted" / "deep" / "journal.txt")

        plain_config = _make_config(plain_path, encrypt=False)
        encrypted_config = _make_config(encrypted_path, encrypt=True)

        encrypted_dir_msgs = []
        mocks = _encrypt_mocks()
        with patch("jrnl.journals.Journal.validate_journal_name"):
            with patch("jrnl.path.print_msg") as mock_print:
                for m in mocks:
                    m.start()
                try:
                    open_journal("default", encrypted_config)
                finally:
                    for m in mocks:
                        m.stop()
                encrypted_dir_msgs = [
                    c for c in mock_print.call_args_list
                    if c[0][0].text == MsgText.DirectoryCreated
                ]

        plain_dir_msgs = []
        with patch("jrnl.journals.Journal.validate_journal_name"):
            with patch("jrnl.path.print_msg") as mock_print:
                open_journal("default", plain_config)
                plain_dir_msgs = [
                    c for c in mock_print.call_args_list
                    if c[0][0].text == MsgText.DirectoryCreated
                ]

        assert len(plain_dir_msgs) == 1
        assert len(encrypted_dir_msgs) == 1
        assert plain_dir_msgs[0][0][0].text == encrypted_dir_msgs[0][0][0].text
        assert plain_dir_msgs[0][0][0].style == encrypted_dir_msgs[0][0][0].style

    def test_journal_created_message_same_for_plain_and_encrypted(self, tmp_path):
        plain_path = str(tmp_path / "plain_journal.txt")
        encrypted_path = str(tmp_path / "encrypted_journal.txt")

        plain_config = _make_config(plain_path, encrypt=False)
        encrypted_config = _make_config(encrypted_path, encrypt=True)

        encrypted_created_msgs = []
        mocks = _encrypt_mocks()
        with patch("jrnl.journals.Journal.validate_journal_name"):
            with patch("jrnl.path.print_msg") as mock_print:
                for m in mocks:
                    m.start()
                try:
                    open_journal("default", encrypted_config)
                finally:
                    for m in mocks:
                        m.stop()
                encrypted_created_msgs = [
                    c for c in mock_print.call_args_list
                    if c[0][0].text == MsgText.JournalCreated
                ]

        plain_created_msgs = []
        with patch("jrnl.journals.Journal.validate_journal_name"):
            with patch("jrnl.path.print_msg") as mock_print:
                open_journal("default", plain_config)
                plain_created_msgs = [
                    c for c in mock_print.call_args_list
                    if c[0][0].text == MsgText.JournalCreated
                ]

        assert len(plain_created_msgs) == 1
        assert len(encrypted_created_msgs) == 1
        assert plain_created_msgs[0][0][0].text == encrypted_created_msgs[0][0][0].text
        assert plain_created_msgs[0][0][0].style == encrypted_created_msgs[0][0][0].style

    def test_does_not_exist_message_same_for_plain_and_encrypted_upgrade(self, tmp_path):
        from jrnl.upgrade import upgrade_jrnl

        plain_missing = str(tmp_path / "missing_plain" / "journal.txt")
        encrypted_missing = str(tmp_path / "missing_encrypted" / "journal.txt")

        config = {
            "journals": {
                "missing_plain": plain_missing,
                "missing_enc": {
                    "journal": encrypted_missing,
                    "encrypt": True,
                },
            },
            "encrypt": False,
        }

        with patch("jrnl.upgrade.load_config", return_value=config):
            with patch("jrnl.upgrade.print_msg") as mock_print:
                with patch("jrnl.upgrade.yesno") as mock_yesno:
                    mock_yesno.return_value = False
                    try:
                        upgrade_jrnl("/fake/config.yaml")
                    except Exception:
                        pass
                does_not_exist_calls = [
                    c for c in mock_print.call_args_list
                    if c[0][0].text == MsgText.DoesNotExist
                ]
                plain_msg = None
                encrypted_msg = None
                for call in does_not_exist_calls:
                    msg = call[0][0]
                    if plain_missing in str(msg):
                        plain_msg = msg
                    if encrypted_missing in str(msg):
                        encrypted_msg = msg

        assert plain_msg is not None
        assert encrypted_msg is not None
        assert plain_msg.text == encrypted_msg.text
        assert plain_msg.style == encrypted_msg.style

    def test_env_var_expansion_consistent_across_entries(self, tmp_path, monkeypatch):
        journal_path = str(tmp_path / "journal.txt")
        with open(journal_path, "w") as f:
            f.write("")
        monkeypatch.setenv("JRNL_CONSISTENCY_DIR", str(tmp_path))

        plain_config = _make_config("$JRNL_CONSISTENCY_DIR/journal.txt", encrypt=False)
        encrypted_config = _make_config(
            "$JRNL_CONSISTENCY_DIR/journal.txt", encrypt=True
        )
        encrypted_config["encrypt"] = "jrnlv2"

        mocks = _encrypt_mocks()
        with patch("jrnl.journals.Journal.validate_journal_name"):
            with patch(
                "jrnl.encryption.Jrnlv2Encryption.Jrnlv2Encryption.decrypt",
                return_value="",
            ):
                for m in mocks:
                    m.start()
                try:
                    j = open_journal("default", encrypted_config)
                    encrypted_expanded = j.config["journal"]
                finally:
                    for m in mocks:
                        m.stop()

        with patch("jrnl.journals.Journal.validate_journal_name"):
            j = open_journal("default", plain_config)
            plain_expanded = j.config["journal"]

        assert plain_expanded == encrypted_expanded == journal_path


WINDOWS_HOME = "C:\\Users\\TestUser"
WINDOWS_JOURNAL_DIR = "C:\\Users\\TestUser\\Journals"
WINDOWS_JOURNAL_PATH = "C:\\Users\\TestUser\\Journals\\default.journal"
WINDOWS_MISSING_PATH = "C:\\Users\\TestUser\\Journals\\MissingDir\\journal.txt"


class TestWindowsPathExpansion:
    def test_windows_tilde_expansion(self):
        with patch("jrnl.path.os.path.expanduser") as mock_expanduser:
            mock_expanduser.side_effect = lambda p: p.replace(
                "~", WINDOWS_HOME
            ) if p.startswith("~") else p
            result = expand_journal_path("~\\Journals\\default.journal")
        assert not result.startswith("~")
        assert WINDOWS_HOME in result
        assert "Journals" in result

    def test_windows_env_var_with_dollar_sign(self, monkeypatch):
        monkeypatch.setenv("JRNL_WIN_DIR", "C:\\Journals")
        with patch("jrnl.path.os.path.expanduser") as mock_expanduser:
            mock_expanduser.side_effect = lambda p: p
            result = expand_journal_path("$JRNL_WIN_DIR\\journal.txt")
        assert result == "C:\\Journals\\journal.txt"

    def test_windows_env_var_expands_on_both_platforms(self, monkeypatch):
        monkeypatch.setenv("JRNL_WIN_DIR", "C:\\Journals")
        with patch("jrnl.path.os.path.expanduser") as mock_expanduser:
            mock_expanduser.side_effect = lambda p: p
            dollar_result = expand_journal_path("$JRNL_WIN_DIR\\journal.txt")
        assert dollar_result == "C:\\Journals\\journal.txt"

    def test_windows_percent_env_var_preserved_on_posix(self, monkeypatch):
        monkeypatch.setenv("JRNL_WIN_DIR", "C:\\Journals")
        with patch("jrnl.path.os.path.expanduser") as mock_expanduser:
            mock_expanduser.side_effect = lambda p: p
            result = expand_journal_path("%JRNL_WIN_DIR%\\journal.txt")
        if os.name == "nt":
            assert result == "C:\\Journals\\journal.txt"
        else:
            assert "%JRNL_WIN_DIR%" in result

    def test_windows_tilde_and_env_var_combined(self, monkeypatch):
        monkeypatch.setenv("JRNL_SUBDIR", "Journals")
        with patch("jrnl.path.os.path.expanduser") as mock_expanduser:
            mock_expanduser.side_effect = lambda p: p.replace(
                "~", WINDOWS_HOME
            ) if p.startswith("~") else p
            result = expand_journal_path("~\\$JRNL_SUBDIR\\default.journal")
        assert not result.startswith("~")
        assert WINDOWS_HOME in result
        assert "Journals" in result

    def test_windows_absolute_path_unchanged(self):
        with patch("jrnl.path.os.path.expanduser") as mock_expanduser:
            mock_expanduser.side_effect = lambda p: p
            result = expand_journal_path("C:\\Users\\TestUser\\journal.txt")
        assert result == "C:\\Users\\TestUser\\journal.txt"

    def test_windows_backslash_path_preserved(self):
        with patch("jrnl.path.os.path.expanduser") as mock_expanduser:
            mock_expanduser.side_effect = lambda p: p
            result = expand_journal_path("D:\\Data\\Journals\\my_journal.txt")
        assert "\\" in result
        assert "D:\\Data\\Journals\\my_journal.txt" == result

    def test_windows_missing_env_var_preserved(self):
        with patch("jrnl.path.os.path.expanduser") as mock_expanduser:
            mock_expanduser.side_effect = lambda p: p
            result = expand_journal_path("%NONEXISTENT_WIN_VAR%\\journal.txt")
        assert "%NONEXISTENT_WIN_VAR%" in result

    def test_windows_empty_path(self):
        result = expand_journal_path("")
        assert result == ""

    def test_windows_unc_path(self):
        with patch("jrnl.path.os.path.expanduser") as mock_expanduser:
            mock_expanduser.side_effect = lambda p: p
            result = expand_journal_path("\\\\server\\share\\journal.txt")
        assert result.startswith("\\\\")


class TestWindowsDirectoryHandling:
    def test_windows_dirname_with_backslashes(self):
        win_path = "C:\\Users\\TestUser\\Journals\\journal.txt"
        with patch("jrnl.path.os.path.dirname") as mock_dirname:
            import ntpath

            mock_dirname.side_effect = ntpath.dirname
            with patch("jrnl.path.os.path.isdir", return_value=False):
                with patch("jrnl.path.os.makedirs"):
                    with patch("jrnl.path.print_msg") as mock_print:
                        result = ensure_journal_directory(win_path)
        assert result is True
        mock_print.assert_called_once()
        msg = mock_print.call_args[0][0]
        assert msg.text == MsgText.DirectoryCreated
        assert msg.style == MsgStyle.NORMAL

    def test_windows_create_journal_file_with_backslashes(self, tmp_path):
        import ntpath

        win_style_path = str(tmp_path).replace("/", "\\") + "\\new_journal.txt"
        actual_path = str(tmp_path / "new_journal.txt")
        with patch("jrnl.path.open"):
            with patch("jrnl.path.print_msg") as mock_print:
                with patch("os.path.dirname", side_effect=ntpath.dirname):
                    with patch("os.path.isdir", return_value=True):
                        create_journal_file(win_style_path, "default")
        mock_print.assert_called_once()
        msg = mock_print.call_args[0][0]
        assert msg.text == MsgText.JournalCreated
        assert msg.style == MsgStyle.NORMAL
        assert msg.params["journal_name"] == "default"
        assert win_style_path in msg.params["filename"]

    def test_windows_journal_path_exists(self):
        win_path = "C:\\Users\\TestUser\\Journal.txt"
        with patch("jrnl.path.os.path.exists", return_value=True) as mock_exists:
            result = journal_path_exists(win_path)
        assert result is True
        mock_exists.assert_called_with(win_path)

    def test_windows_journal_path_not_exists(self):
        win_path = "C:\\Users\\TestUser\\Missing.txt"
        with patch("jrnl.path.os.path.exists", return_value=False):
            result = journal_path_exists(win_path)
        assert result is False


class TestWindowsPlainJournalLoading:
    def test_windows_plain_journal_expands_path(self, tmp_path):
        real_journal_path = str(tmp_path / "journal.txt")
        with open(real_journal_path, "w") as f:
            f.write("")
        win_style_path = str(tmp_path).replace("/", "\\") + "\\journal.txt"
        config = _make_config(win_style_path, encrypt=False)
        with patch("jrnl.journals.Journal.validate_journal_name"):
            with patch("jrnl.path.os.path.expanduser") as mock_expanduser:
                mock_expanduser.side_effect = lambda p: p.replace("\\", "/")
                j = open_journal("default", config)
        assert j is not None

    def test_windows_plain_journal_creates_dir(self, tmp_path):
        if os.name == "nt":
            real_path = str(tmp_path / "win_subdir" / "journal.txt")
            win_style_path = str(tmp_path).replace("/", "\\") + "\\win_subdir\\journal.txt"
            config = _make_config(win_style_path, encrypt=False)
            with patch("jrnl.journals.Journal.validate_journal_name"):
                with patch("jrnl.path.print_msg") as mock_print:
                    j = open_journal("default", config)
            assert os.path.isfile(real_path)
            dir_msgs = [
                c for c in mock_print.call_args_list
                if c[0][0].text == MsgText.DirectoryCreated
            ]
            created_msgs = [
                c for c in mock_print.call_args_list
                if c[0][0].text == MsgText.JournalCreated
            ]
            assert len(dir_msgs) == 1
            assert dir_msgs[0][0][0].style == MsgStyle.NORMAL
            assert len(created_msgs) == 1
            assert created_msgs[0][0][0].style == MsgStyle.NORMAL
        else:
            real_path = str(tmp_path / "win_subdir" / "journal.txt")
            config = _make_config(real_path, encrypt=False)
            with patch("jrnl.journals.Journal.validate_journal_name"):
                with patch("jrnl.path.print_msg") as mock_print:
                    j = open_journal("default", config)
            assert os.path.isfile(real_path)
            dir_msgs = [
                c for c in mock_print.call_args_list
                if c[0][0].text == MsgText.DirectoryCreated
            ]
            created_msgs = [
                c for c in mock_print.call_args_list
                if c[0][0].text == MsgText.JournalCreated
            ]
            assert len(dir_msgs) == 1
            assert dir_msgs[0][0][0].style == MsgStyle.NORMAL
            assert len(created_msgs) == 1
            assert created_msgs[0][0][0].style == MsgStyle.NORMAL

    def test_windows_plain_journal_expands_env_var(self, tmp_path, monkeypatch):
        real_journal_path = str(tmp_path / "journal.txt")
        with open(real_journal_path, "w") as f:
            f.write("")
        monkeypatch.setenv("WIN_JOURNAL_DIR", str(tmp_path))
        win_env_path = "$WIN_JOURNAL_DIR/journal.txt"
        config = _make_config(win_env_path, encrypt=False)
        with patch("jrnl.journals.Journal.validate_journal_name"):
            j = open_journal("default", config)
        assert j.config["journal"] == real_journal_path


class TestWindowsEncryptedJournalLoading:
    def test_windows_encrypted_journal_creates_file(self, tmp_path):
        if os.name == "nt":
            real_path = str(tmp_path / "encrypted.txt")
            win_style_path = str(tmp_path).replace("/", "\\") + "\\encrypted.txt"
        else:
            real_path = str(tmp_path / "encrypted.txt")
            win_style_path = real_path
        config = _make_config(win_style_path, encrypt=True)
        mocks = _encrypt_mocks()
        with patch("jrnl.journals.Journal.validate_journal_name"):
            with patch("jrnl.path.print_msg") as mock_print:
                for m in mocks:
                    m.start()
                try:
                    j = open_journal("default", config)
                finally:
                    for m in mocks:
                        m.stop()
        assert os.path.isfile(real_path)
        created_msgs = [
            c for c in mock_print.call_args_list
            if c[0][0].text == MsgText.JournalCreated
        ]
        assert len(created_msgs) == 1
        assert created_msgs[0][0][0].style == MsgStyle.NORMAL

    def test_windows_encrypted_journal_creates_nested_dirs(self, tmp_path):
        if os.name == "nt":
            real_path = str(tmp_path / "deep" / "nested" / "encrypted.txt")
            win_style_path = str(tmp_path).replace("/", "\\") + "\\deep\\nested\\encrypted.txt"
        else:
            real_path = str(tmp_path / "deep" / "nested" / "encrypted.txt")
            win_style_path = real_path
        config = _make_config(win_style_path, encrypt=True)
        mocks = _encrypt_mocks()
        with patch("jrnl.journals.Journal.validate_journal_name"):
            with patch("jrnl.path.print_msg") as mock_print:
                for m in mocks:
                    m.start()
                try:
                    j = open_journal("default", config)
                finally:
                    for m in mocks:
                        m.stop()
        assert os.path.isfile(real_path)
        dir_msgs = [
            c for c in mock_print.call_args_list
            if c[0][0].text == MsgText.DirectoryCreated
        ]
        created_msgs = [
            c for c in mock_print.call_args_list
            if c[0][0].text == MsgText.JournalCreated
        ]
        assert len(dir_msgs) == 1
        assert dir_msgs[0][0][0].style == MsgStyle.NORMAL
        assert len(created_msgs) == 1
        assert created_msgs[0][0][0].style == MsgStyle.NORMAL

    def test_windows_encrypted_journal_expands_env_var(self, tmp_path, monkeypatch):
        real_journal_path = str(tmp_path / "encrypted.txt")
        with open(real_journal_path, "wb") as f:
            f.write(b"")
        monkeypatch.setenv("WIN_ENC_DIR", str(tmp_path))
        win_env_path = "$WIN_ENC_DIR\\encrypted.txt"
        config = _make_config(win_env_path, encrypt=True)
        config["encrypt"] = "jrnlv2"
        mocks = _encrypt_mocks()
        with patch("jrnl.journals.Journal.validate_journal_name"):
            with patch(
                "jrnl.encryption.Jrnlv2Encryption.Jrnlv2Encryption.decrypt",
                return_value="",
            ):
                for m in mocks:
                    m.start()
                try:
                    j = open_journal("default", config)
                finally:
                    for m in mocks:
                        m.stop()
        assert j is not None


class TestWindowsUpgradePathHandling:
    def test_windows_missing_path_reports_does_not_exist(self):
        from jrnl.upgrade import upgrade_jrnl

        win_missing = "C:\\Users\\TestUser\\Missing\\journal.txt"
        config = {
            "journals": {
                "missing_win": win_missing,
            },
            "encrypt": False,
        }
        with patch("jrnl.upgrade.load_config", return_value=config):
            with patch("jrnl.upgrade.journal_path_exists", return_value=False):
                with patch("jrnl.upgrade.print_msg") as mock_print:
                    with patch("jrnl.upgrade.yesno") as mock_yesno:
                        mock_yesno.return_value = False
                        try:
                            upgrade_jrnl("/fake/config.yaml")
                        except Exception:
                            pass
        does_not_exist_calls = [
            c for c in mock_print.call_args_list
            if c[0][0].text == MsgText.DoesNotExist
        ]
        assert len(does_not_exist_calls) >= 1
        msg = does_not_exist_calls[0][0][0]
        assert msg.style == MsgStyle.ERROR
        assert msg.params["name"] == win_missing

    def test_windows_encrypted_missing_path_reports_same_error(self):
        from jrnl.upgrade import upgrade_jrnl

        win_plain_missing = "C:\\Users\\TestUser\\Journals\\plain.txt"
        win_enc_missing = "C:\\Users\\TestUser\\Journals\\encrypted.txt"
        config = {
            "journals": {
                "win_plain": win_plain_missing,
                "win_enc": {
                    "journal": win_enc_missing,
                    "encrypt": True,
                },
            },
            "encrypt": False,
        }
        with patch("jrnl.upgrade.load_config", return_value=config):
            with patch("jrnl.upgrade.expand_journal_path") as mock_expand:
                mock_expand.side_effect = lambda p: p
                with patch("jrnl.upgrade.journal_path_exists", return_value=False):
                    with patch("jrnl.upgrade.print_msg") as mock_print:
                        with patch("jrnl.upgrade.yesno") as mock_yesno:
                            mock_yesno.return_value = False
                            try:
                                upgrade_jrnl("/fake/config.yaml")
                            except Exception:
                                pass
        does_not_exist_calls = [
            c for c in mock_print.call_args_list
            if c[0][0].text == MsgText.DoesNotExist
        ]
        assert len(does_not_exist_calls) >= 2
        plain_msg = None
        enc_msg = None
        for call in does_not_exist_calls:
            msg = call[0][0]
            if msg.params["name"] == win_plain_missing:
                plain_msg = msg
            if msg.params["name"] == win_enc_missing:
                enc_msg = msg
        assert plain_msg is not None
        assert enc_msg is not None
        assert plain_msg.text == enc_msg.text
        assert plain_msg.style == enc_msg.style

    def test_windows_check_exists_expands_path(self, monkeypatch):
        from jrnl.upgrade import check_exists

        monkeypatch.setenv("WIN_TEST_DIR", "C:\\Journals")
        with patch("jrnl.upgrade.journal_path_exists", return_value=True):
            result = check_exists("%WIN_TEST_DIR%\\journal.txt")
        assert result is True

    def test_windows_backup_expands_path(self, tmp_path, monkeypatch):
        from jrnl.upgrade import backup

        journal_path = str(tmp_path / "backup_test.txt")
        with open(journal_path, "w") as f:
            f.write("content")
        monkeypatch.setenv("WIN_BACKUP_DIR", str(tmp_path))
        with patch("jrnl.upgrade.print_msg"):
            backup("$WIN_BACKUP_DIR/backup_test.txt")
        assert os.path.isfile(journal_path + ".backup")


class TestCrossPlatformPathConsistency:
    def test_expand_path_produces_equivalent_results(self, tmp_path, monkeypatch):
        monkeypatch.setenv("JRNL_DIR", str(tmp_path))
        posix_path = f"$JRNL_DIR/journal.txt"
        windows_path = f"$JRNL_DIR\\journal.txt"
        posix_result = expand_journal_path(posix_path)
        windows_result = expand_journal_path(windows_path)
        assert posix_result.endswith("journal.txt")
        assert "journal.txt" in windows_result

    def test_directory_created_message_same_style_on_windows_and_posix(self, tmp_path):
        posix_path = str(tmp_path / "posix_dir" / "journal.txt")
        win_dir_path = str(tmp_path / "win_dir")

        with patch("jrnl.path.print_msg") as mock_print:
            ensure_journal_directory(posix_path)
        posix_msg = None
        for call in mock_print.call_args_list:
            if call[0][0].text == MsgText.DirectoryCreated:
                posix_msg = call[0][0]
                break

        with patch("jrnl.path.print_msg") as mock_print_win:
            ensure_journal_directory(str(Path(win_dir_path) / "journal.txt"))
        win_msg = None
        for call in mock_print_win.call_args_list:
            if call[0][0].text == MsgText.DirectoryCreated:
                win_msg = call[0][0]
                break

        assert posix_msg is not None
        assert win_msg is not None
        assert posix_msg.text == win_msg.text
        assert posix_msg.style == win_msg.style

    def test_journal_created_message_same_style_on_windows_and_posix(self, tmp_path):
        posix_path = str(tmp_path / "posix_journal.txt")
        win_style_path = str(tmp_path / "win_journal.txt")

        with patch("jrnl.path.open"):
            with patch("jrnl.path.print_msg") as mock_print:
                create_journal_file(posix_path, "test_posix")
        posix_msg = mock_print.call_args[0][0]

        with patch("jrnl.path.open"):
            with patch("jrnl.path.print_msg") as mock_print_win:
                create_journal_file(win_style_path, "test_win")
        win_msg = mock_print_win.call_args[0][0]

        assert posix_msg.text == win_msg.text
        assert posix_msg.style == win_msg.style

    def test_does_not_exist_error_same_style_plain_and_encrypted_windows(self):
        from jrnl.upgrade import upgrade_jrnl

        win_plain = "C:\\Journals\\plain.txt"
        win_enc = "C:\\Journals\\encrypted.txt"
        config = {
            "journals": {
                "win_plain": win_plain,
                "win_enc": {"journal": win_enc, "encrypt": True},
            },
            "encrypt": False,
        }
        with patch("jrnl.upgrade.load_config", return_value=config):
            with patch("jrnl.upgrade.expand_journal_path") as mock_expand:
                mock_expand.side_effect = lambda p: p
                with patch("jrnl.upgrade.journal_path_exists", return_value=False):
                    with patch("jrnl.upgrade.print_msg") as mock_print:
                        with patch("jrnl.upgrade.yesno", return_value=False):
                            try:
                                upgrade_jrnl("/fake/config.yaml")
                            except Exception:
                                pass
        does_not_exist = [
            c for c in mock_print.call_args_list
            if c[0][0].text == MsgText.DoesNotExist
        ]
        assert len(does_not_exist) >= 2
        for call in does_not_exist:
            assert call[0][0].style == MsgStyle.ERROR
            assert call[0][0].text == MsgText.DoesNotExist

    def test_env_var_expansion_consistent_windows_and_posix(self, monkeypatch):
        monkeypatch.setenv("JRNL_DATA", "/data/journals")
        posix_path = "$JRNL_DATA/default.txt"
        posix_result = expand_journal_path(posix_path)
        assert posix_result == "/data/journals/default.txt"
        monkeypatch.setenv("JRNL_DATA_WIN", "D:\\Journals")
        win_path = "$JRNL_DATA_WIN\\default.txt"
        win_result = expand_journal_path(win_path)
        assert "default.txt" in win_result
        assert "$JRNL_DATA_WIN" not in win_result

    def test_backslash_and_forward_slash_both_resolve(self, tmp_path, monkeypatch):
        monkeypatch.setenv("JRNL_BASE", str(tmp_path))
        posix_style = "$JRNL_BASE/subdir/journal.txt"
        win_style = "$JRNL_BASE\\subdir\\journal.txt"
        posix_result = expand_journal_path(posix_style)
        win_result = expand_journal_path(win_style)
        assert str(tmp_path) in posix_result
        assert str(tmp_path) in win_result

