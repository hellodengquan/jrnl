# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import datetime
import os
import shutil

import pytest

from jrnl.config import scope_config
from jrnl.journals import Entry
from jrnl.journals import Journal


@pytest.fixture
def journal_with_tags():
    journal = Journal()
    journal.new_entry(
        "2023-01-15 10:00: Meeting with @john and @jane about project @alpha",
        date=datetime.datetime(2023, 1, 15, 10, 0),
    )
    journal.new_entry(
        "2023-01-16 14:00: @jane asked about @beta project",
        date=datetime.datetime(2023, 1, 16, 14, 0),
    )
    journal.new_entry(
        "2023-01-17 09:00: Lunch with @bob",
        date=datetime.datetime(2023, 1, 17, 9, 0),
    )
    journal.new_entry(
        "2023-01-18 16:00: No tags here, just plain entry",
        date=datetime.datetime(2023, 1, 18, 16, 0),
    )
    journal.new_entry(
        "2023-01-19 11:00: @alpha and @beta meeting",
        date=datetime.datetime(2023, 1, 19, 11, 0),
    )
    return journal


@pytest.fixture
def journal_with_dates():
    journal = Journal()
    base_date = datetime.datetime(2023, 6, 15, 12, 0)
    dates = [
        base_date - datetime.timedelta(days=10),
        base_date - datetime.timedelta(days=5),
        base_date - datetime.timedelta(days=1),
        base_date,
        base_date + datetime.timedelta(days=1),
        base_date + datetime.timedelta(days=5),
        base_date + datetime.timedelta(days=10),
    ]
    for i, d in enumerate(dates):
        journal.new_entry(f"Entry {i} for date {d}", date=d, sort=False)
    journal.sort()
    return journal, base_date


@pytest.fixture
def complex_journal():
    journal = Journal(tagsymbols="@#")
    entries_data = [
        ("2023-01-15 09:00", "Work meeting @projectA @meeting", True),
        ("2023-01-16 14:00", "Personal note #family #vacation", False),
        ("2023-01-17 10:00", "Work review @projectA @review", True),
        ("2023-01-18 16:00", "Dinner with friends #friends", False),
        ("2023-01-19 11:00", "ProjectA planning @projectA #planning", True),
        ("2023-02-01 09:00", "New month start @projectB", False),
        ("2023-02-15 14:00", "ProjectB milestone @projectB @milestone", True),
    ]
    for date_str, text, starred in entries_data:
        date = datetime.datetime.strptime(date_str, "%Y-%m-%d %H:%M")
        entry = Entry(journal, date=date, text=text, starred=starred)
        journal.entries.append(entry)
    journal.sort()
    return journal


def _base_config(tmp_path):
    return {
        "version": "4.0",
        "editor": "",
        "encrypt": False,
        "default_hour": 9,
        "default_minute": 0,
        "timeformat": "%Y-%m-%d %H:%M",
        "highlight": True,
        "linewrap": 79,
        "indent_character": "|",
        "colors": {"body": "none", "date": "none", "tags": "none", "title": "none"},
    }


@pytest.fixture
def multi_journal_config(tmp_path):
    default_path = str(tmp_path / "default.journal")
    work_path = str(tmp_path / "work.journal")
    personal_path = str(tmp_path / "personal.journal")
    config = _base_config(tmp_path)
    config["journals"] = {
        "default": {
            "journal": default_path,
            "tagsymbols": "@",
        },
        "work": {
            "journal": work_path,
            "tagsymbols": "#",
            "linewrap": 100,
        },
        "personal": {
            "journal": personal_path,
            "tagsymbols": "@!",
        },
    }
    config["tagsymbols"] = "@"
    return config


@pytest.fixture
def mixed_journals_config(tmp_path):
    default_path = str(tmp_path / "default.txt")
    work_path = str(tmp_path / "work.txt")
    config = _base_config(tmp_path)
    config["journals"] = {
        "default": default_path,
        "work": {
            "journal": work_path,
            "tagsymbols": "@#",
        },
    }
    config["tagsymbols"] = "@"
    return config


@pytest.fixture
def multi_journal_config_with_folder(tmp_path):
    default_path = str(tmp_path / "default.journal")
    folder_path = str(tmp_path / "folder_journal")
    os.makedirs(folder_path, exist_ok=True)
    config = _base_config(tmp_path)
    config["journals"] = {
        "default": {
            "journal": default_path,
            "tagsymbols": "@",
        },
        "notes": {
            "journal": folder_path,
            "tagsymbols": "#",
        },
    }
    config["tagsymbols"] = "@"
    return config


@pytest.fixture
def folder_journal_with_entries(tmp_path):
    folder_path = str(tmp_path / "folder_journal")
    os.makedirs(os.path.join(folder_path, "2023", "01"), exist_ok=True)
    os.makedirs(os.path.join(folder_path, "2023", "02"), exist_ok=True)
    entry_text_1 = "[2023-01-15 09:00] Meeting with @john\n"
    with open(os.path.join(folder_path, "2023", "01", "15.txt"), "w") as f:
        f.write(entry_text_1)
    entry_text_2 = "[2023-02-10 14:00] Review with #team\n"
    with open(os.path.join(folder_path, "2023", "02", "10.txt"), "w") as f:
        f.write(entry_text_2)
    return folder_path


@pytest.fixture
def encrypted_journal_config(tmp_path):
    journal_path = str(tmp_path / "encrypted.journal")
    config = _base_config(tmp_path)
    config["journals"] = {
        "encrypted": {
            "journal": journal_path,
            "encrypt": True,
            "tagsymbols": "@",
        },
    }
    config["tagsymbols"] = "@"
    return config


@pytest.fixture
def multi_journal_config_mixed_types(tmp_path):
    default_path = str(tmp_path / "default.journal")
    folder_path = str(tmp_path / "folder_journal")
    encrypted_path = str(tmp_path / "encrypted.journal")
    os.makedirs(folder_path, exist_ok=True)
    config = _base_config(tmp_path)
    config["journals"] = {
        "default": {
            "journal": default_path,
            "tagsymbols": "@",
        },
        "folder": {
            "journal": folder_path,
            "tagsymbols": "#",
        },
        "encrypted": {
            "journal": encrypted_path,
            "encrypt": True,
            "tagsymbols": "@!",
        },
    }
    config["tagsymbols"] = "@"
    return config


@pytest.fixture
def make_journal_with_entries():
    def _make(journal_cls=Journal, tagsymbols="@", name="default", **kwargs):
        journal = journal_cls(name=name, tagsymbols=tagsymbols, **kwargs)
        base = datetime.datetime(2023, 6, 15, 12, 0)
        journal.new_entry(
            f"Entry from today @todaytag",
            date=base,
        )
        journal.new_entry(
            f"Entry from yesterday @yesterdaytag",
            date=base - datetime.timedelta(days=1),
        )
        journal.new_entry(
            f"Entry from last week @lastweektag",
            date=base - datetime.timedelta(weeks=1),
        )
        journal.new_entry(
            f"Entry from last month @lastmonthtag",
            date=base - datetime.timedelta(days=30),
        )
        journal.new_entry(
            "Entry with no tags",
            date=base - datetime.timedelta(days=60),
        )
        journal.sort()
        return journal

    return _make


class FastJrnlv2Encryption:
    _PBKDF2_ITERATIONS = 100

    def __init__(self, journal_name: str, config: dict):
        from jrnl.encryption.Jrnlv2Encryption import Jrnlv2Encryption

        self._impl = Jrnlv2Encryption(journal_name, config)
        self._journal_name = journal_name
        self._config = config
        self._password: str | None = None
        self._key: bytes | None = None
        self._salt: bytes = b"\xf2\xd5q\x0e\xc1\x8d.\xde\xdc\x8e6t\x89\x04\xce\xf8"
        self._encoding: str = "utf-8"
        self._attempts: int = 0
        self._max_attempts: int = 3
        self._check_keyring: bool = True
        self.check_keyring = False

    @property
    def password(self) -> str | None:
        return self._password

    @password.setter
    def password(self, value: str | None):
        self._password = value
        if value is None:
            self._key = None
            return
        self._derive_key()

    def _derive_key(self) -> None:
        import base64

        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

        password = self._password.encode(self._encoding)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self._salt,
            iterations=self._PBKDF2_ITERATIONS,
            backend=default_backend(),
        )
        key = kdf.derive(password)
        self._key = base64.urlsafe_b64encode(key)

    def _encrypt(self, text: str) -> bytes:
        from cryptography.fernet import Fernet

        return Fernet(self._key).encrypt(text.encode(self._encoding))

    def _decrypt(self, text: bytes) -> str | None:
        from cryptography.fernet import Fernet
        from cryptography.fernet import InvalidToken

        try:
            return Fernet(self._key).decrypt(text).decode(self._encoding)
        except (InvalidToken, IndexError):
            return None

    def encrypt(self, text: str) -> bytes:
        return self._encrypt(text)

    def decrypt(self, text: bytes) -> str:
        from jrnl.exception import JrnlException
        from jrnl.messages import Message
        from jrnl.messages import MsgStyle
        from jrnl.messages import MsgText

        if (result := self._decrypt(text)) is None:
            raise JrnlException(
                Message(MsgText.DecryptionFailedGeneric, MsgStyle.ERROR)
            )
        return result

    def clear(self) -> None:
        self._password = None
        self._key = None
        self._check_keyring = False


def _make_enc_journal_config(tmp_path, journal_name="encrypted"):
    journal_path = str(tmp_path / f"{journal_name}.journal")
    return {
        "journal": journal_path,
        "encrypt": True,
        "tagsymbols": "@",
        "timeformat": "%Y-%m-%d %H:%M",
        "default_hour": 9,
        "default_minute": 0,
        "highlight": True,
        "linewrap": 79,
        "indent_character": "|",
        "editor": "",
    }


@pytest.fixture
def make_fast_encrypted_journal(tmp_path):
    def _make(journal_name="encrypted", password="testpass", tagsymbols="@"):
        config = _make_enc_journal_config(tmp_path, journal_name)
        config["tagsymbols"] = tagsymbols
        journal = Journal(name=journal_name, **config)
        journal.encryption_method = FastJrnlv2Encryption(journal_name, journal.config)
        journal.encryption_method.check_keyring = False
        journal.encryption_method.password = password
        return journal

    return _make


@pytest.fixture
def make_real_encrypted_journal(tmp_path):
    from jrnl.encryption.Jrnlv2Encryption import Jrnlv2Encryption

    def _make(journal_name="encrypted", password="testpass", tagsymbols="@"):
        config = _make_enc_journal_config(tmp_path, journal_name)
        config["tagsymbols"] = tagsymbols
        journal = Journal(name=journal_name, **config)
        journal.encryption_method = Jrnlv2Encryption(journal_name, journal.config)
        journal.encryption_method.check_keyring = False
        journal.encryption_method.password = password
        return journal

    return _make
