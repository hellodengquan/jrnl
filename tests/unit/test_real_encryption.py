# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import datetime
import os

import pytest

from jrnl.encryption.Jrnlv2Encryption import Jrnlv2Encryption
from jrnl.exception import JrnlException
from jrnl.journals import Journal


def _make_encrypted_journal_config(tmp_path, journal_name="encrypted"):
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


def _create_encrypted_journal(tmp_path, journal_name="encrypted", password="testpass"):
    config = _make_encrypted_journal_config(tmp_path, journal_name)
    journal = Journal(name=journal_name, **config)
    journal.encryption_method = Jrnlv2Encryption(journal_name, journal.config)
    journal.encryption_method.check_keyring = False
    journal.encryption_method.password = password
    return journal


class TestRealEncryptionRoundTrip:
    def test_write_and_read_single_entry(self, tmp_path):
        j_write = _create_encrypted_journal(tmp_path, password="mypassword")
        j_write.new_entry(
            "Hello encrypted world @secret",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        j_write.write()

        assert os.path.exists(j_write.config["journal"])
        with open(j_write.config["journal"], "rb") as f:
            raw = f.read()
        assert raw != b"[2023-01-15 10:00] Hello encrypted world @secret"
        assert len(raw) > 0

        j_read = _create_encrypted_journal(tmp_path, password="mypassword")
        j_read.open()

        assert len(j_read) == 1
        assert "Hello encrypted world" in j_read.entries[0].title
        assert "@secret" in j_read.entries[0].tags

    def test_write_and_read_multiple_entries(self, tmp_path):
        j_write = _create_encrypted_journal(tmp_path, password="pass123")
        j_write.new_entry(
            "First entry @alpha",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        j_write.new_entry(
            "Second entry @beta",
            date=datetime.datetime(2023, 2, 20, 14, 0),
        )
        j_write.new_entry(
            "Third entry @gamma",
            date=datetime.datetime(2023, 3, 25, 9, 0),
        )
        j_write.write()

        j_read = _create_encrypted_journal(tmp_path, password="pass123")
        j_read.open()

        assert len(j_read) == 3
        titles = [e.title.strip() for e in j_read.entries]
        assert "First entry" in " ".join(titles)
        assert "Second entry" in " ".join(titles)
        assert "Third entry" in " ".join(titles)

    def test_encrypted_file_different_passwords_produce_different_output(self, tmp_path):
        j1 = _create_encrypted_journal(tmp_path, "enc1", password="passwordA")
        j1.new_entry(
            "Same content @tag",
            date=datetime.datetime(2023, 1, 1, 9, 0),
        )
        j1.write()

        j2 = _create_encrypted_journal(tmp_path, "enc2", password="passwordB")
        j2.new_entry(
            "Same content @tag",
            date=datetime.datetime(2023, 1, 1, 9, 0),
        )
        j2.write()

        with open(j1.config["journal"], "rb") as f:
            raw1 = f.read()
        with open(j2.config["journal"], "rb") as f:
            raw2 = f.read()

        assert raw1 != raw2

    def test_round_trip_preserves_tags(self, tmp_path):
        j_write = _create_encrypted_journal(tmp_path, password="tagpreserve")
        j_write.new_entry(
            "Entry with @alpha and @beta tags",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        j_write.new_entry(
            "Another entry @beta @gamma",
            date=datetime.datetime(2023, 1, 16, 10, 0),
        )
        j_write.write()

        j_read = _create_encrypted_journal(tmp_path, password="tagpreserve")
        j_read.open()

        assert len(j_read) == 2
        all_tags = set()
        for e in j_read.entries:
            all_tags.update(e.tags)
        assert "@alpha" in all_tags
        assert "@beta" in all_tags
        assert "@gamma" in all_tags


class TestTagSearchOnRealEncryptedJournal:
    def test_filter_single_tag_after_decrypt(self, tmp_path):
        j_write = _create_encrypted_journal(tmp_path, password="tagtest")
        j_write.new_entry(
            "Meeting with @john and @jane",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        j_write.new_entry(
            "Lunch with @bob",
            date=datetime.datetime(2023, 1, 16, 14, 0),
        )
        j_write.new_entry(
            "No tags here",
            date=datetime.datetime(2023, 1, 17, 9, 0),
        )
        j_write.write()

        j_read = _create_encrypted_journal(tmp_path, password="tagtest")
        j_read.open()

        j_read.filter(tags=["@john"])
        assert len(j_read) == 1
        assert "@john" in j_read.entries[0].tags

    def test_filter_multiple_tags_or_mode_after_decrypt(self, tmp_path):
        j_write = _create_encrypted_journal(tmp_path, password="multitag")
        j_write.new_entry(
            "@alpha project",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        j_write.new_entry(
            "@beta project",
            date=datetime.datetime(2023, 1, 16, 14, 0),
        )
        j_write.new_entry(
            "@gamma project",
            date=datetime.datetime(2023, 1, 17, 9, 0),
        )
        j_write.write()

        j_read = _create_encrypted_journal(tmp_path, password="multitag")
        j_read.open()

        j_read.filter(tags=["@alpha", "@beta"])
        assert len(j_read) == 2

    def test_filter_strict_tags_after_decrypt(self, tmp_path):
        j_write = _create_encrypted_journal(tmp_path, password="strict")
        j_write.new_entry(
            "@alpha and @beta together",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        j_write.new_entry(
            "Only @alpha",
            date=datetime.datetime(2023, 1, 16, 14, 0),
        )
        j_write.new_entry(
            "Only @beta",
            date=datetime.datetime(2023, 1, 17, 9, 0),
        )
        j_write.write()

        j_read = _create_encrypted_journal(tmp_path, password="strict")
        j_read.open()

        j_read.filter(tags=["@alpha", "@beta"], strict=True)
        assert len(j_read) == 1

    def test_filter_exclude_tag_after_decrypt(self, tmp_path):
        j_write = _create_encrypted_journal(tmp_path, password="exclude")
        j_write.new_entry(
            "Public entry @public",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        j_write.new_entry(
            "Secret entry @secret",
            date=datetime.datetime(2023, 1, 16, 14, 0),
        )
        j_write.new_entry(
            "Another public @public",
            date=datetime.datetime(2023, 1, 17, 9, 0),
        )
        j_write.write()

        j_read = _create_encrypted_journal(tmp_path, password="exclude")
        j_read.open()

        j_read.filter(exclude=["@secret"])
        assert len(j_read) == 2
        for entry in j_read.entries:
            assert "@secret" not in entry.tags

    def test_filter_tag_case_insensitive_after_decrypt(self, tmp_path):
        j_write = _create_encrypted_journal(tmp_path, password="case")
        j_write.new_entry(
            "@Hello World",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        j_write.new_entry(
            "@hello there",
            date=datetime.datetime(2023, 1, 16, 10, 0),
        )
        j_write.new_entry(
            "No match @other",
            date=datetime.datetime(2023, 1, 17, 10, 0),
        )
        j_write.write()

        j_read = _create_encrypted_journal(tmp_path, password="case")
        j_read.open()

        j_read.filter(tags=["@HELLO"])
        assert len(j_read) == 2

    def test_filter_tagged_only_after_decrypt(self, tmp_path):
        j_write = _create_encrypted_journal(tmp_path, password="tagged")
        j_write.new_entry(
            "With @tag",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        j_write.new_entry(
            "Without tag",
            date=datetime.datetime(2023, 1, 16, 10, 0),
        )
        j_write.write()

        j_read = _create_encrypted_journal(tmp_path, password="tagged")
        j_read.open()

        j_read.filter(tagged=True)
        assert len(j_read) == 1

    def test_tags_property_after_decrypt(self, tmp_path):
        j_write = _create_encrypted_journal(tmp_path, password="tagcount")
        j_write.new_entry(
            "@alpha and @beta",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        j_write.new_entry(
            "@alpha again",
            date=datetime.datetime(2023, 1, 16, 10, 0),
        )
        j_write.new_entry(
            "Just text",
            date=datetime.datetime(2023, 1, 17, 10, 0),
        )
        j_write.write()

        j_read = _create_encrypted_journal(tmp_path, password="tagcount")
        j_read.open()

        tag_counts = {t.name: t.count for t in j_read.tags}
        assert tag_counts.get("@alpha") == 2
        assert tag_counts.get("@beta") == 1


class TestDateFilterOnRealEncryptedJournal:
    def test_filter_start_date_after_decrypt(self, tmp_path):
        j_write = _create_encrypted_journal(tmp_path, password="datestart")
        j_write.new_entry(
            "Jan 10 entry",
            date=datetime.datetime(2023, 1, 10, 10, 0),
        )
        j_write.new_entry(
            "Jan 20 entry",
            date=datetime.datetime(2023, 1, 20, 10, 0),
        )
        j_write.new_entry(
            "Feb 5 entry",
            date=datetime.datetime(2023, 2, 5, 10, 0),
        )
        j_write.write()

        j_read = _create_encrypted_journal(tmp_path, password="datestart")
        j_read.open()

        j_read.filter(start_date="2023-01-15")
        assert len(j_read) == 2
        for entry in j_read.entries:
            assert entry.date >= datetime.datetime(2023, 1, 15)

    def test_filter_end_date_after_decrypt(self, tmp_path):
        j_write = _create_encrypted_journal(tmp_path, password="dateend")
        j_write.new_entry(
            "Jan 10 entry",
            date=datetime.datetime(2023, 1, 10, 10, 0),
        )
        j_write.new_entry(
            "Jan 20 entry",
            date=datetime.datetime(2023, 1, 20, 10, 0),
        )
        j_write.new_entry(
            "Feb 5 entry",
            date=datetime.datetime(2023, 2, 5, 10, 0),
        )
        j_write.write()

        j_read = _create_encrypted_journal(tmp_path, password="dateend")
        j_read.open()

        j_read.filter(end_date="2023-01-25")
        assert len(j_read) == 2

    def test_filter_date_range_after_decrypt(self, tmp_path):
        j_write = _create_encrypted_journal(tmp_path, password="daterange")
        j_write.new_entry(
            "Jan 10 entry",
            date=datetime.datetime(2023, 1, 10, 10, 0),
        )
        j_write.new_entry(
            "Jan 20 entry",
            date=datetime.datetime(2023, 1, 20, 10, 0),
        )
        j_write.new_entry(
            "Feb 5 entry",
            date=datetime.datetime(2023, 2, 5, 10, 0),
        )
        j_write.write()

        j_read = _create_encrypted_journal(tmp_path, password="daterange")
        j_read.open()

        j_read.filter(start_date="2023-01-15", end_date="2023-01-31")
        assert len(j_read) == 1
        assert j_read.entries[0].date.month == 1
        assert j_read.entries[0].date.day == 20

    def test_filter_month_after_decrypt(self, tmp_path):
        j_write = _create_encrypted_journal(tmp_path, password="month")
        j_write.new_entry(
            "Jan entry",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        j_write.new_entry(
            "Feb entry",
            date=datetime.datetime(2023, 2, 15, 10, 0),
        )
        j_write.new_entry(
            "Mar entry",
            date=datetime.datetime(2023, 3, 15, 10, 0),
        )
        j_write.write()

        j_read = _create_encrypted_journal(tmp_path, password="month")
        j_read.open()

        j_read.filter(month="2")
        assert len(j_read) == 1
        assert j_read.entries[0].date.month == 2

    def test_filter_year_after_decrypt(self, tmp_path):
        j_write = _create_encrypted_journal(tmp_path, password="year")
        j_write.new_entry(
            "2022 entry",
            date=datetime.datetime(2022, 6, 15, 10, 0),
        )
        j_write.new_entry(
            "2023 entry",
            date=datetime.datetime(2023, 6, 15, 10, 0),
        )
        j_write.write()

        j_read = _create_encrypted_journal(tmp_path, password="year")
        j_read.open()

        j_read.filter(year="2023")
        assert len(j_read) == 1
        assert j_read.entries[0].date.year == 2023

    def test_combined_tag_and_date_after_decrypt(self, tmp_path):
        j_write = _create_encrypted_journal(tmp_path, password="combotagdate")
        j_write.new_entry(
            "Jan alpha @alpha",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        j_write.new_entry(
            "Jan beta @beta",
            date=datetime.datetime(2023, 1, 20, 10, 0),
        )
        j_write.new_entry(
            "Feb alpha @alpha",
            date=datetime.datetime(2023, 2, 15, 10, 0),
        )
        j_write.write()

        j_read = _create_encrypted_journal(tmp_path, password="combotagdate")
        j_read.open()

        j_read.filter(tags=["@alpha"], month="1")
        assert len(j_read) == 1
        assert j_read.entries[0].date.month == 1


class TestWrongPasswordAndExceptions:
    def test_wrong_password_decrypt_returns_none(self, tmp_path):
        j_write = _create_encrypted_journal(tmp_path, password="correct")
        j_write.new_entry(
            "Secret entry @tag",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        j_write.write()

        enc_method = Jrnlv2Encryption(
            "encrypted", _make_encrypted_journal_config(tmp_path)
        )
        enc_method.check_keyring = False
        enc_method.password = "wrong"

        with open(j_write.config["journal"], "rb") as f:
            ciphertext = f.read()

        assert enc_method._decrypt(ciphertext) is None

    def test_password_set_to_none_clears_key(self, tmp_path):
        enc_method = Jrnlv2Encryption("test", {})
        enc_method.password = "somepassword"
        assert enc_method._key is not None
        assert enc_method.password == "somepassword"

        enc_method.password = None
        assert enc_method.password is None
        assert enc_method._key is None

    def test_clear_resets_password_and_keyring(self, tmp_path):
        enc_method = Jrnlv2Encryption("test", {})
        enc_method.password = "testpass"
        assert enc_method.password == "testpass"
        assert enc_method.check_keyring is True

        enc_method.clear()
        assert enc_method.password is None
        assert enc_method.check_keyring is False

    def test_correct_password_decrypts_successfully(self, tmp_path):
        j_write = _create_encrypted_journal(tmp_path, password="correct")
        j_write.new_entry(
            "Secret entry @findme",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        j_write.write()

        enc_method = Jrnlv2Encryption(
            "encrypted", _make_encrypted_journal_config(tmp_path)
        )
        enc_method.check_keyring = False
        enc_method.password = "correct"

        with open(j_write.config["journal"], "rb") as f:
            ciphertext = f.read()

        result = enc_method._decrypt(ciphertext)
        assert result is not None
        assert "@findme" in result

    def test_password_clear_requires_reentry(self, tmp_path):
        j_write = _create_encrypted_journal(tmp_path, password="cleartest")
        j_write.new_entry(
            "Secret entry",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        j_write.write()

        j_read = _create_encrypted_journal(tmp_path, password="cleartest")
        j_read.open()
        assert len(j_read) == 1

        j_read.encryption_method.clear()
        assert j_read.encryption_method.password is None
        assert j_read.encryption_method.check_keyring is False

        j_read.encryption_method.password = "cleartest"
        j_read.write()

        j_read2 = _create_encrypted_journal(tmp_path, password="cleartest")
        j_read2.open()
        assert len(j_read2) == 1

    def test_attempts_counter_state(self, tmp_path):
        enc_method = Jrnlv2Encryption("test", {})
        assert enc_method._attempts == 0
        assert enc_method._max_attempts == 3

        enc_method._attempts = 2
        assert enc_method._attempts == 2

    def test_encrypted_content_is_not_plaintext(self, tmp_path):
        j_write = _create_encrypted_journal(tmp_path, password="secret")
        j_write.new_entry(
            "Very secret content @topsecret",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        j_write.write()

        with open(j_write.config["journal"], "rb") as f:
            raw = f.read()

        assert b"Very secret content" not in raw
        assert b"@topsecret" not in raw
        assert len(raw) > 0

    def test_different_passwords_produce_different_keys(self, tmp_path):
        enc1 = Jrnlv2Encryption("test", {})
        enc1.password = "passwordA"
        key1 = enc1._key

        enc2 = Jrnlv2Encryption("test", {})
        enc2.password = "passwordB"
        key2 = enc2._key

        assert key1 != key2


class TestMultipleEncryptedJournalsIsolation:
    def test_two_encrypted_journals_different_passwords(self, tmp_path):
        j1 = _create_encrypted_journal(tmp_path, "journal1", password="pass1")
        j1.new_entry(
            "Entry only in j1 @onlyj1",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        j1.write()

        j2 = _create_encrypted_journal(tmp_path, "journal2", password="pass2")
        j2.new_entry(
            "Entry only in j2 @onlyj2",
            date=datetime.datetime(2023, 1, 16, 10, 0),
        )
        j2.write()

        j1_read = _create_encrypted_journal(tmp_path, "journal1", password="pass1")
        j1_read.open()

        j2_read = _create_encrypted_journal(tmp_path, "journal2", password="pass2")
        j2_read.open()

        assert len(j1_read) == 1
        assert "@onlyj1" in j1_read.entries[0].tags
        assert "@onlyj2" not in j1_read.entries[0].tags

        assert len(j2_read) == 1
        assert "@onlyj2" in j2_read.entries[0].tags
        assert "@onlyj1" not in j2_read.entries[0].tags

    def test_three_encrypted_journals_data_isolation(self, tmp_path):
        j1 = _create_encrypted_journal(tmp_path, "work", password="workpass")
        j1.new_entry(
            "Work meeting @work @meeting",
            date=datetime.datetime(2023, 1, 15, 9, 0),
        )
        j1.new_entry(
            "Project review @work @review",
            date=datetime.datetime(2023, 1, 16, 10, 0),
        )
        j1.write()

        j2 = _create_encrypted_journal(tmp_path, "personal", password="personalpass")
        j2.new_entry(
            "Dinner with friends @personal @friends",
            date=datetime.datetime(2023, 1, 15, 18, 0),
        )
        j2.write()

        j3 = _create_encrypted_journal(tmp_path, "diary", password="diarypass")
        j3.new_entry(
            "Thoughts about life @diary @reflection",
            date=datetime.datetime(2023, 1, 17, 22, 0),
        )
        j3.write()

        j1r = _create_encrypted_journal(tmp_path, "work", password="workpass")
        j1r.open()
        j2r = _create_encrypted_journal(tmp_path, "personal", password="personalpass")
        j2r.open()
        j3r = _create_encrypted_journal(tmp_path, "diary", password="diarypass")
        j3r.open()

        assert len(j1r) == 2
        assert len(j2r) == 1
        assert len(j3r) == 1

        j1r.filter(tags=["@work"])
        assert len(j1r) == 2

        j2r.filter(tags=["@personal"])
        assert len(j2r) == 1

        j3r.filter(tags=["@work"])
        assert len(j3r) == 0

    def test_cross_password_decrypt_fails(self, tmp_path):
        j1 = _create_encrypted_journal(tmp_path, "secure1", password="pwA")
        j1.new_entry(
            "Secret data A @secretA",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        j1.write()

        j2 = _create_encrypted_journal(tmp_path, "secure2", password="pwB")
        j2.new_entry(
            "Secret data B @secretB",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        j2.write()

        with open(j1.config["journal"], "rb") as f:
            j1_ciphertext = f.read()

        enc_method_wrong = Jrnlv2Encryption("secure1", j1.config)
        enc_method_wrong.check_keyring = False
        enc_method_wrong.password = "pwB"

        assert enc_method_wrong._decrypt(j1_ciphertext) is None

        enc_method_correct = Jrnlv2Encryption("secure1", j1.config)
        enc_method_correct.check_keyring = False
        enc_method_correct.password = "pwA"

        result = enc_method_correct._decrypt(j1_ciphertext)
        assert result is not None
        assert "@secretA" in result

    def test_mixed_encrypted_and_plain_journals(self, tmp_path):
        plain_path = str(tmp_path / "plain.journal")
        plain_j = Journal(
            name="plain",
            journal=plain_path,
            encrypt=False,
            tagsymbols="@",
            timeformat="%Y-%m-%d %H:%M",
            default_hour=9,
            default_minute=0,
            highlight=True,
            linewrap=79,
            indent_character="|",
            editor="",
        )
        plain_j.new_entry(
            "Plain text entry @plaintag",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        plain_j.write()

        enc_j = _create_encrypted_journal(tmp_path, "encrypted", password="secret")
        enc_j.new_entry(
            "Encrypted entry @enctag",
            date=datetime.datetime(2023, 1, 16, 10, 0),
        )
        enc_j.write()

        plain_read = Journal(
            name="plain",
            journal=plain_path,
            encrypt=False,
            tagsymbols="@",
            timeformat="%Y-%m-%d %H:%M",
            default_hour=9,
            default_minute=0,
            highlight=True,
            linewrap=79,
            indent_character="|",
            editor="",
        )
        plain_read.open()

        enc_read = _create_encrypted_journal(tmp_path, "encrypted", password="secret")
        enc_read.open()

        assert len(plain_read) == 1
        assert "@plaintag" in plain_read.entries[0].tags
        assert "@enctag" not in plain_read.entries[0].tags

        assert len(enc_read) == 1
        assert "@enctag" in enc_read.entries[0].tags
        assert "@plaintag" not in enc_read.entries[0].tags

    def test_encrypted_journals_different_tagsymbols(self, tmp_path):
        j1 = Journal(
            name="at_tags",
            journal=str(tmp_path / "at.journal"),
            encrypt=True,
            tagsymbols="@",
            timeformat="%Y-%m-%d %H:%M",
            default_hour=9,
            default_minute=0,
            highlight=True,
            linewrap=79,
            indent_character="|",
            editor="",
        )
        j1.encryption_method = Jrnlv2Encryption("at_tags", j1.config)
        j1.encryption_method.check_keyring = False
        j1.encryption_method.password = "pass1"
        j1.new_entry(
            "Entry with @atag",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        j1.write()

        j2 = Journal(
            name="hash_tags",
            journal=str(tmp_path / "hash.journal"),
            encrypt=True,
            tagsymbols="#",
            timeformat="%Y-%m-%d %H:%M",
            default_hour=9,
            default_minute=0,
            highlight=True,
            linewrap=79,
            indent_character="|",
            editor="",
        )
        j2.encryption_method = Jrnlv2Encryption("hash_tags", j2.config)
        j2.encryption_method.check_keyring = False
        j2.encryption_method.password = "pass2"
        j2.new_entry(
            "Entry with #hashtag",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        j2.write()

        j1r = Journal(
            name="at_tags",
            journal=str(tmp_path / "at.journal"),
            encrypt=True,
            tagsymbols="@",
            timeformat="%Y-%m-%d %H:%M",
            default_hour=9,
            default_minute=0,
            highlight=True,
            linewrap=79,
            indent_character="|",
            editor="",
        )
        j1r.encryption_method = Jrnlv2Encryption("at_tags", j1r.config)
        j1r.encryption_method.check_keyring = False
        j1r.encryption_method.password = "pass1"
        j1r.open()

        j2r = Journal(
            name="hash_tags",
            journal=str(tmp_path / "hash.journal"),
            encrypt=True,
            tagsymbols="#",
            timeformat="%Y-%m-%d %H:%M",
            default_hour=9,
            default_minute=0,
            highlight=True,
            linewrap=79,
            indent_character="|",
            editor="",
        )
        j2r.encryption_method = Jrnlv2Encryption("hash_tags", j2r.config)
        j2r.encryption_method.check_keyring = False
        j2r.encryption_method.password = "pass2"
        j2r.open()

        assert "@atag" in j1r.entries[0].tags
        assert "#hashtag" not in j1r.entries[0].tags

        assert "#hashtag" in j2r.entries[0].tags
        assert "@atag" not in j2r.entries[0].tags


class TestRealEncryptionWithRelativeDates:
    def test_yesterday_entry_in_encrypted_journal(self, tmp_path):
        now = datetime.datetime.now()
        yesterday = now - datetime.timedelta(days=1)
        two_days_ago = now - datetime.timedelta(days=2)

        j_write = _create_encrypted_journal(tmp_path, password="reldate")
        j_write.new_entry(
            "Today entry @today",
            date=now,
        )
        j_write.new_entry(
            "Yesterday entry @yesterday",
            date=yesterday,
        )
        j_write.new_entry(
            "Two days ago entry @twodays",
            date=two_days_ago,
        )
        j_write.sort()
        j_write.write()

        j_read = _create_encrypted_journal(tmp_path, password="reldate")
        j_read.open()

        yesterday_str = yesterday.strftime("%Y-%m-%d")
        j_read.filter(start_date=yesterday_str, end_date=yesterday_str)
        assert len(j_read) == 1
        assert "@yesterday" in j_read.entries[0].tags

    def test_last_week_entry_in_encrypted_journal(self, tmp_path):
        now = datetime.datetime.now()
        last_week = now - datetime.timedelta(weeks=1)
        two_weeks_ago = now - datetime.timedelta(weeks=2)

        j_write = _create_encrypted_journal(tmp_path, password="lastweek")
        j_write.new_entry(
            "Today entry @today",
            date=now,
        )
        j_write.new_entry(
            "Last week entry @lastweek",
            date=last_week,
        )
        j_write.new_entry(
            "Two weeks ago entry @twoweeks",
            date=two_weeks_ago,
        )
        j_write.sort()
        j_write.write()

        j_read = _create_encrypted_journal(tmp_path, password="lastweek")
        j_read.open()

        last_week_day_str = last_week.strftime("%Y-%m-%d")
        j_read.filter(start_date=last_week_day_str)
        assert len(j_read) == 2
        for entry in j_read.entries:
            assert entry.date.date() >= last_week.date()

    def test_date_filter_preserves_tag_integrity(self, tmp_path):
        j_write = _create_encrypted_journal(tmp_path, password="integrity")
        j_write.new_entry(
            "Jan alpha @alpha @jan",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        j_write.new_entry(
            "Feb beta @beta @feb",
            date=datetime.datetime(2023, 2, 15, 10, 0),
        )
        j_write.new_entry(
            "Mar gamma @gamma @mar",
            date=datetime.datetime(2023, 3, 15, 10, 0),
        )
        j_write.write()

        j_read = _create_encrypted_journal(tmp_path, password="integrity")
        j_read.open()

        j_read.filter(month="2")
        assert len(j_read) == 1
        assert "@beta" in j_read.entries[0].tags
        assert "@feb" in j_read.entries[0].tags
