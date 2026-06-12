import os
import stat
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
