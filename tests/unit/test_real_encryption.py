# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import datetime
import os

import pytest

from jrnl.encryption.Jrnlv2Encryption import Jrnlv2Encryption
from jrnl.journals import Journal


class TestFastEncryptionRoundTrip:
    def test_write_and_read_single_entry(self, make_fast_encrypted_journal):
        j_write = make_fast_encrypted_journal(password="mypassword")
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

        j_read = make_fast_encrypted_journal(password="mypassword")
        j_read.open()

        assert len(j_read) == 1
        assert "Hello encrypted world" in j_read.entries[0].title
        assert "@secret" in j_read.entries[0].tags

    def test_write_and_read_multiple_entries(self, make_fast_encrypted_journal):
        j_write = make_fast_encrypted_journal(password="pass123")
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

        j_read = make_fast_encrypted_journal(password="pass123")
        j_read.open()

        assert len(j_read) == 3
        titles = " ".join(e.title.strip() for e in j_read.entries)
        assert "First entry" in titles
        assert "Second entry" in titles
        assert "Third entry" in titles

    def test_encrypted_file_different_passwords_produce_different_output(
        self, tmp_path, make_fast_encrypted_journal
    ):
        j1 = make_fast_encrypted_journal("enc1", password="passwordA")
        j1.new_entry(
            "Same content @tag",
            date=datetime.datetime(2023, 1, 1, 9, 0),
        )
        j1.write()

        j2 = make_fast_encrypted_journal("enc2", password="passwordB")
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

    def test_round_trip_preserves_tags(self, make_fast_encrypted_journal):
        j_write = make_fast_encrypted_journal(password="tagpreserve")
        j_write.new_entry(
            "Entry with @alpha and @beta tags",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        j_write.new_entry(
            "Another entry @beta @gamma",
            date=datetime.datetime(2023, 1, 16, 10, 0),
        )
        j_write.write()

        j_read = make_fast_encrypted_journal(password="tagpreserve")
        j_read.open()

        assert len(j_read) == 2
        all_tags = set()
        for e in j_read.entries:
            all_tags.update(e.tags)
        assert "@alpha" in all_tags
        assert "@beta" in all_tags
        assert "@gamma" in all_tags


class TestTagSearchOnFastEncryptedJournal:
    def test_filter_single_tag_after_decrypt(self, make_fast_encrypted_journal):
        j_write = make_fast_encrypted_journal(password="tagtest")
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

        j_read = make_fast_encrypted_journal(password="tagtest")
        j_read.open()

        j_read.filter(tags=["@john"])
        assert len(j_read) == 1
        assert "@john" in j_read.entries[0].tags

    def test_filter_multiple_tags_or_mode_after_decrypt(self, make_fast_encrypted_journal):
        j_write = make_fast_encrypted_journal(password="multitag")
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

        j_read = make_fast_encrypted_journal(password="multitag")
        j_read.open()

        j_read.filter(tags=["@alpha", "@beta"])
        assert len(j_read) == 2

    def test_filter_strict_tags_after_decrypt(self, make_fast_encrypted_journal):
        j_write = make_fast_encrypted_journal(password="strict")
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

        j_read = make_fast_encrypted_journal(password="strict")
        j_read.open()

        j_read.filter(tags=["@alpha", "@beta"], strict=True)
        assert len(j_read) == 1

    def test_filter_exclude_tag_after_decrypt(self, make_fast_encrypted_journal):
        j_write = make_fast_encrypted_journal(password="exclude")
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

        j_read = make_fast_encrypted_journal(password="exclude")
        j_read.open()

        j_read.filter(exclude=["@secret"])
        assert len(j_read) == 2
        for entry in j_read.entries:
            assert "@secret" not in entry.tags

    def test_filter_tag_case_insensitive_after_decrypt(self, make_fast_encrypted_journal):
        j_write = make_fast_encrypted_journal(password="case")
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

        j_read = make_fast_encrypted_journal(password="case")
        j_read.open()

        j_read.filter(tags=["@HELLO"])
        assert len(j_read) == 2

    def test_filter_tagged_only_after_decrypt(self, make_fast_encrypted_journal):
        j_write = make_fast_encrypted_journal(password="tagged")
        j_write.new_entry(
            "With @tag",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        j_write.new_entry(
            "Without tag",
            date=datetime.datetime(2023, 1, 16, 10, 0),
        )
        j_write.write()

        j_read = make_fast_encrypted_journal(password="tagged")
        j_read.open()

        j_read.filter(tagged=True)
        assert len(j_read) == 1

    def test_tags_property_after_decrypt(self, make_fast_encrypted_journal):
        j_write = make_fast_encrypted_journal(password="tagcount")
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

        j_read = make_fast_encrypted_journal(password="tagcount")
        j_read.open()

        tag_counts = {t.name: t.count for t in j_read.tags}
        assert tag_counts.get("@alpha") == 2
        assert tag_counts.get("@beta") == 1


class TestDateFilterOnFastEncryptedJournal:
    def test_filter_start_date_after_decrypt(self, make_fast_encrypted_journal):
        j_write = make_fast_encrypted_journal(password="datestart")
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

        j_read = make_fast_encrypted_journal(password="datestart")
        j_read.open()

        j_read.filter(start_date="2023-01-15")
        assert len(j_read) == 2
        for entry in j_read.entries:
            assert entry.date >= datetime.datetime(2023, 1, 15)

    def test_filter_end_date_after_decrypt(self, make_fast_encrypted_journal):
        j_write = make_fast_encrypted_journal(password="dateend")
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

        j_read = make_fast_encrypted_journal(password="dateend")
        j_read.open()

        j_read.filter(end_date="2023-01-25")
        assert len(j_read) == 2

    def test_filter_date_range_after_decrypt(self, make_fast_encrypted_journal):
        j_write = make_fast_encrypted_journal(password="daterange")
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

        j_read = make_fast_encrypted_journal(password="daterange")
        j_read.open()

        j_read.filter(start_date="2023-01-15", end_date="2023-01-31")
        assert len(j_read) == 1
        assert j_read.entries[0].date.month == 1
        assert j_read.entries[0].date.day == 20

    def test_filter_month_after_decrypt(self, make_fast_encrypted_journal):
        j_write = make_fast_encrypted_journal(password="month")
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

        j_read = make_fast_encrypted_journal(password="month")
        j_read.open()

        j_read.filter(month="2")
        assert len(j_read) == 1
        assert j_read.entries[0].date.month == 2

    def test_filter_year_after_decrypt(self, make_fast_encrypted_journal):
        j_write = make_fast_encrypted_journal(password="year")
        j_write.new_entry(
            "2022 entry",
            date=datetime.datetime(2022, 6, 15, 10, 0),
        )
        j_write.new_entry(
            "2023 entry",
            date=datetime.datetime(2023, 6, 15, 10, 0),
        )
        j_write.write()

        j_read = make_fast_encrypted_journal(password="year")
        j_read.open()

        j_read.filter(year="2023")
        assert len(j_read) == 1
        assert j_read.entries[0].date.year == 2023

    def test_combined_tag_and_date_after_decrypt(self, make_fast_encrypted_journal):
        j_write = make_fast_encrypted_journal(password="combotagdate")
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

        j_read = make_fast_encrypted_journal(password="combotagdate")
        j_read.open()

        j_read.filter(tags=["@alpha"], month="1")
        assert len(j_read) == 1
        assert j_read.entries[0].date.month == 1


class TestWrongPasswordAndExceptionsFast:
    def test_wrong_password_decrypt_returns_none(self, make_fast_encrypted_journal):
        j_write = make_fast_encrypted_journal(password="correct")
        j_write.new_entry(
            "Secret entry @tag",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        j_write.write()

        enc_method_wrong = j_write.encryption_method.__class__(
            "encrypted", j_write.config
        )
        enc_method_wrong.check_keyring = False
        enc_method_wrong.password = "wrong"

        with open(j_write.config["journal"], "rb") as f:
            ciphertext = f.read()

        assert enc_method_wrong._decrypt(ciphertext) is None

    def test_password_set_to_none_clears_key(self, make_fast_encrypted_journal):
        enc_method = make_fast_encrypted_journal(password="somepass").encryption_method
        assert enc_method._key is not None
        assert enc_method.password == "somepass"

        enc_method.password = None
        assert enc_method.password is None
        assert enc_method._key is None

    def test_clear_resets_password_and_keyring(self, make_fast_encrypted_journal):
        j = make_fast_encrypted_journal(password="testpass")
        enc_method = j.encryption_method
        assert enc_method.password == "testpass"

        enc_method.clear()
        assert enc_method.password is None

    def test_correct_password_decrypts_successfully(self, make_fast_encrypted_journal):
        j_write = make_fast_encrypted_journal(password="correct")
        j_write.new_entry(
            "Secret entry @findme",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        j_write.write()

        with open(j_write.config["journal"], "rb") as f:
            ciphertext = f.read()

        result = j_write.encryption_method._decrypt(ciphertext)
        assert result is not None
        assert "@findme" in result

    def test_encrypted_content_is_not_plaintext(self, make_fast_encrypted_journal):
        j_write = make_fast_encrypted_journal(password="secret")
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

    def test_different_passwords_produce_different_keys(self):
        from tests.unit.conftest import FastJrnlv2Encryption

        enc1 = FastJrnlv2Encryption("test", {})
        enc1.password = "passwordA"
        key1 = enc1._key

        enc2 = FastJrnlv2Encryption("test", {})
        enc2.password = "passwordB"
        key2 = enc2._key

        assert key1 != key2


class TestMultipleEncryptedJournalsIsolationFast:
    def test_two_encrypted_journals_different_passwords(
        self, make_fast_encrypted_journal
    ):
        j1 = make_fast_encrypted_journal("journal1", password="pass1")
        j1.new_entry(
            "Entry only in j1 @onlyj1",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        j1.write()

        j2 = make_fast_encrypted_journal("journal2", password="pass2")
        j2.new_entry(
            "Entry only in j2 @onlyj2",
            date=datetime.datetime(2023, 1, 16, 10, 0),
        )
        j2.write()

        j1_read = make_fast_encrypted_journal("journal1", password="pass1")
        j1_read.open()

        j2_read = make_fast_encrypted_journal("journal2", password="pass2")
        j2_read.open()

        assert len(j1_read) == 1
        assert "@onlyj1" in j1_read.entries[0].tags
        assert "@onlyj2" not in j1_read.entries[0].tags

        assert len(j2_read) == 1
        assert "@onlyj2" in j2_read.entries[0].tags
        assert "@onlyj1" not in j2_read.entries[0].tags

    def test_three_encrypted_journals_data_isolation(self, make_fast_encrypted_journal):
        j1 = make_fast_encrypted_journal("work", password="workpass")
        j1.new_entry(
            "Work meeting @work @meeting",
            date=datetime.datetime(2023, 1, 15, 9, 0),
        )
        j1.new_entry(
            "Project review @work @review",
            date=datetime.datetime(2023, 1, 16, 10, 0),
        )
        j1.write()

        j2 = make_fast_encrypted_journal("personal", password="personalpass")
        j2.new_entry(
            "Dinner with friends @personal @friends",
            date=datetime.datetime(2023, 1, 15, 18, 0),
        )
        j2.write()

        j3 = make_fast_encrypted_journal("diary", password="diarypass")
        j3.new_entry(
            "Thoughts about life @diary @reflection",
            date=datetime.datetime(2023, 1, 17, 22, 0),
        )
        j3.write()

        j1r = make_fast_encrypted_journal("work", password="workpass")
        j1r.open()
        j2r = make_fast_encrypted_journal("personal", password="personalpass")
        j2r.open()
        j3r = make_fast_encrypted_journal("diary", password="diarypass")
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

    def test_cross_password_decrypt_fails(self, make_fast_encrypted_journal):
        j1 = make_fast_encrypted_journal("secure1", password="pwA")
        j1.new_entry(
            "Secret data A @secretA",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        j1.write()

        j2 = make_fast_encrypted_journal("secure2", password="pwB")
        j2.new_entry(
            "Secret data B @secretB",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        j2.write()

        with open(j1.config["journal"], "rb") as f:
            j1_ciphertext = f.read()

        enc_method_wrong = j2.encryption_method.__class__("secure1", j1.config)
        enc_method_wrong.check_keyring = False
        enc_method_wrong.password = "pwB"

        assert enc_method_wrong._decrypt(j1_ciphertext) is None

        enc_method_correct = j1.encryption_method.__class__("secure1", j1.config)
        enc_method_correct.check_keyring = False
        enc_method_correct.password = "pwA"

        result = enc_method_correct._decrypt(j1_ciphertext)
        assert result is not None
        assert "@secretA" in result

    def test_mixed_encrypted_and_plain_journals(
        self, tmp_path, make_fast_encrypted_journal
    ):
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

        enc_j = make_fast_encrypted_journal("encrypted", password="secret")
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

        enc_read = make_fast_encrypted_journal("encrypted", password="secret")
        enc_read.open()

        assert len(plain_read) == 1
        assert "@plaintag" in plain_read.entries[0].tags
        assert "@enctag" not in plain_read.entries[0].tags

        assert len(enc_read) == 1
        assert "@enctag" in enc_read.entries[0].tags
        assert "@plaintag" not in enc_read.entries[0].tags

    def test_encrypted_journals_different_tagsymbols(
        self, make_fast_encrypted_journal
    ):
        j1 = make_fast_encrypted_journal("at_tags", password="pass1", tagsymbols="@")
        j1.new_entry(
            "Entry with @atag",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        j1.write()

        j2 = make_fast_encrypted_journal("hash_tags", password="pass2", tagsymbols="#")
        j2.new_entry(
            "Entry with #hashtag",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        j2.write()

        j1r = make_fast_encrypted_journal("at_tags", password="pass1", tagsymbols="@")
        j1r.open()

        j2r = make_fast_encrypted_journal("hash_tags", password="pass2", tagsymbols="#")
        j2r.open()

        assert "@atag" in j1r.entries[0].tags
        assert "#hashtag" not in j1r.entries[0].tags

        assert "#hashtag" in j2r.entries[0].tags
        assert "@atag" not in j2r.entries[0].tags


class TestFastEncryptionWithRelativeDates:
    def test_yesterday_entry_in_encrypted_journal(self, make_fast_encrypted_journal):
        now = datetime.datetime.now()
        yesterday = now - datetime.timedelta(days=1)
        two_days_ago = now - datetime.timedelta(days=2)

        j_write = make_fast_encrypted_journal(password="reldate")
        j_write.new_entry("Today entry @today", date=now)
        j_write.new_entry("Yesterday entry @yesterday", date=yesterday)
        j_write.new_entry("Two days ago entry @twodays", date=two_days_ago)
        j_write.sort()
        j_write.write()

        j_read = make_fast_encrypted_journal(password="reldate")
        j_read.open()

        yesterday_str = yesterday.strftime("%Y-%m-%d")
        j_read.filter(start_date=yesterday_str, end_date=yesterday_str)
        assert len(j_read) == 1
        assert "@yesterday" in j_read.entries[0].tags

    def test_last_week_entry_in_encrypted_journal(self, make_fast_encrypted_journal):
        now = datetime.datetime.now()
        last_week = now - datetime.timedelta(weeks=1)
        two_weeks_ago = now - datetime.timedelta(weeks=2)

        j_write = make_fast_encrypted_journal(password="lastweek")
        j_write.new_entry("Today entry @today", date=now)
        j_write.new_entry("Last week entry @lastweek", date=last_week)
        j_write.new_entry("Two weeks ago entry @twoweeks", date=two_weeks_ago)
        j_write.sort()
        j_write.write()

        j_read = make_fast_encrypted_journal(password="lastweek")
        j_read.open()

        last_week_day_str = last_week.strftime("%Y-%m-%d")
        j_read.filter(start_date=last_week_day_str)
        assert len(j_read) == 2
        for entry in j_read.entries:
            assert entry.date.date() >= last_week.date()

    def test_date_filter_preserves_tag_integrity(self, make_fast_encrypted_journal):
        j_write = make_fast_encrypted_journal(password="integrity")
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

        j_read = make_fast_encrypted_journal(password="integrity")
        j_read.open()

        j_read.filter(month="2")
        assert len(j_read) == 1
        assert "@beta" in j_read.entries[0].tags
        assert "@feb" in j_read.entries[0].tags


class TestFullStrengthEncryption:
    @pytest.mark.slow
    def test_full_strength_write_and_read(self, make_real_encrypted_journal):
        j_write = make_real_encrypted_journal(password="realsecret")
        j_write.new_entry(
            "Real encrypted data @realtag",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        j_write.write()

        j_read = make_real_encrypted_journal(password="realsecret")
        j_read.open()

        assert len(j_read) == 1
        assert "@realtag" in j_read.entries[0].tags

    @pytest.mark.slow
    def test_full_strength_tag_filter(self, make_real_encrypted_journal):
        j_write = make_real_encrypted_journal(password="tagfilter")
        j_write.new_entry(
            "Important @urgent",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        j_write.new_entry(
            "Normal entry",
            date=datetime.datetime(2023, 1, 16, 10, 0),
        )
        j_write.write()

        j_read = make_real_encrypted_journal(password="tagfilter")
        j_read.open()

        j_read.filter(tags=["@urgent"])
        assert len(j_read) == 1

    @pytest.mark.slow
    def test_full_strength_date_filter(self, make_real_encrypted_journal):
        j_write = make_real_encrypted_journal(password="datefilter")
        j_write.new_entry(
            "January entry",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        j_write.new_entry(
            "February entry",
            date=datetime.datetime(2023, 2, 15, 10, 0),
        )
        j_write.write()

        j_read = make_real_encrypted_journal(password="datefilter")
        j_read.open()

        j_read.filter(month="1")
        assert len(j_read) == 1
        assert j_read.entries[0].date.month == 1

    @pytest.mark.slow
    def test_full_strength_wrong_password_fails(self, make_real_encrypted_journal):
        j_write = make_real_encrypted_journal(password="correctpass")
        j_write.new_entry(
            "Secret message @topsecret",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        j_write.write()

        with open(j_write.config["journal"], "rb") as f:
            ciphertext = f.read()

        enc_method_wrong = Jrnlv2Encryption("test", j_write.config)
        enc_method_wrong.check_keyring = False
        enc_method_wrong.password = "wrongpass"

        assert enc_method_wrong._decrypt(ciphertext) is None

    @pytest.mark.slow
    def test_full_strength_cross_password_denied(self, make_real_encrypted_journal):
        j1 = make_real_encrypted_journal("journalA", password="pwA")
        j1.new_entry("Data A @tagA", date=datetime.datetime(2023, 1, 1, 9, 0))
        j1.write()

        j2 = make_real_encrypted_journal("journalB", password="pwB")
        j2.new_entry("Data B @tagB", date=datetime.datetime(2023, 1, 1, 9, 0))
        j2.write()

        with open(j1.config["journal"], "rb") as f:
            j1_cipher = f.read()

        enc_method = Jrnlv2Encryption("journalA", j1.config)
        enc_method.check_keyring = False
        enc_method.password = "pwB"

        assert enc_method._decrypt(j1_cipher) is None

        enc_method.password = "pwA"
        result = enc_method._decrypt(j1_cipher)
        assert result is not None
        assert "@taga" in result.lower()

    @pytest.mark.slow
    def test_full_strength_content_not_readable(self, make_real_encrypted_journal):
        j = make_real_encrypted_journal(password="hidden")
        j.new_entry(
            "Sensitive content with @secrettag",
            date=datetime.datetime(2023, 1, 15, 10, 0),
        )
        j.write()

        with open(j.config["journal"], "rb") as f:
            raw = f.read()

        assert b"Sensitive content" not in raw
        assert b"@secrettag" not in raw
        assert len(raw) > 0
