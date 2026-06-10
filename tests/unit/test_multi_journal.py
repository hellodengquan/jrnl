# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import datetime
import os
import shutil

import pytest

from jrnl.args import parse_args
from jrnl.config import DEFAULT_JOURNAL_KEY
from jrnl.config import get_journal_name
from jrnl.config import scope_config
from jrnl.config import validate_journal_name
from jrnl.exception import JrnlException
from jrnl.journals import Journal
from jrnl.journals.FolderJournal import Folder


class TestMultiJournalDataIsolation:
    def test_journal_data_isolation(self, multi_journal_config):
        journals = {}
        for name in ["default", "work", "personal"]:
            journal = Journal(
                name=name,
                **scope_config(multi_journal_config.copy(), name),
            )
            journals[name] = journal

        journals["default"].new_entry(
            "2023-01-01 09:00: Default entry @defaulttag",
            date=datetime.datetime(2023, 1, 1, 9, 0),
        )
        journals["work"].new_entry(
            "2023-01-02 10:00: Work entry #worktag",
            date=datetime.datetime(2023, 1, 2, 10, 0),
        )
        journals["personal"].new_entry(
            "2023-01-03 11:00: Personal entry @personaltag !family",
            date=datetime.datetime(2023, 1, 3, 11, 0),
        )

        assert len(journals["default"]) == 1
        assert len(journals["work"]) == 1
        assert len(journals["personal"]) == 1

        assert "@defaulttag" in journals["default"].entries[0].tags
        assert "#worktag" not in journals["default"].entries[0].tags

        assert "#worktag" in journals["work"].entries[0].tags
        assert "@defaulttag" not in journals["work"].entries[0].tags

        assert set(journals["personal"].entries[0].tags) == {"@personaltag", "!family"}

    def test_journal_config_isolation(self, multi_journal_config):
        default_config = scope_config(multi_journal_config.copy(), "default")
        work_config = scope_config(multi_journal_config.copy(), "work")
        personal_config = scope_config(multi_journal_config.copy(), "personal")

        assert default_config["tagsymbols"] == "@"
        assert work_config["tagsymbols"] == "#"
        assert personal_config["tagsymbols"] == "@!"

        assert default_config["linewrap"] == 79
        assert work_config["linewrap"] == 100

    def test_search_in_specific_journal_isolated(self, multi_journal_config):
        journals = {}
        for name in ["default", "work", "personal"]:
            journal = Journal(
                name=name,
                **scope_config(multi_journal_config.copy(), name),
            )
            journals[name] = journal

        journals["default"].new_entry(
            "2023-01-01 09:00: Shared topic @important",
            date=datetime.datetime(2023, 1, 1, 9, 0),
        )
        journals["default"].new_entry(
            "2023-01-02 09:00: Only default",
            date=datetime.datetime(2023, 1, 2, 9, 0),
        )
        journals["work"].new_entry(
            "2023-01-01 09:00: Shared topic #important",
            date=datetime.datetime(2023, 1, 1, 9, 0),
        )
        journals["personal"].new_entry(
            "2023-01-01 09:00: Different topic @home",
            date=datetime.datetime(2023, 1, 1, 9, 0),
        )

        journals["default"].filter(tags=["@important"])
        assert len(journals["default"]) == 1

        journals["work"].filter(tags=["#important"])
        assert len(journals["work"]) == 1

        journals["personal"].filter(tags=["@important"])
        assert len(journals["personal"]) == 0

    def test_same_tag_different_journals_isolated(self):
        j1 = Journal(name="journal1", tagsymbols="@")
        j2 = Journal(name="journal2", tagsymbols="@")

        j1.new_entry(
            "2023-01-01 09:00: Entry in j1 @shared",
            date=datetime.datetime(2023, 1, 1, 9, 0),
        )
        j1.new_entry(
            "2023-01-02 09:00: Another in j1 @shared @onlyj1",
            date=datetime.datetime(2023, 1, 2, 9, 0),
        )
        j2.new_entry(
            "2023-01-01 09:00: Entry in j2 @shared @onlyj2",
            date=datetime.datetime(2023, 1, 1, 9, 0),
        )

        j1.filter(tags=["@shared"])
        assert len(j1) == 2

        j2.filter(tags=["@shared"])
        assert len(j2) == 1

        j1_copy = Journal(name="journal1", tagsymbols="@")
        j1_copy.new_entry(
            "2023-01-01 09:00: Entry in j1 @shared",
            date=datetime.datetime(2023, 1, 1, 9, 0),
        )
        j1_copy.new_entry(
            "2023-01-02 09:00: Another in j1 @shared @onlyj1",
            date=datetime.datetime(2023, 1, 2, 9, 0),
        )
        j1_copy.filter(tags=["@onlyj1"])
        assert len(j1_copy) == 1

        j2_copy = Journal(name="journal2", tagsymbols="@")
        j2_copy.new_entry(
            "2023-01-01 09:00: Entry in j2 @shared @onlyj2",
            date=datetime.datetime(2023, 1, 1, 9, 0),
        )
        j2_copy.filter(tags=["@onlyj2"])
        assert len(j2_copy) == 1


class TestJournalNameFromArgs:
    def test_get_journal_name_from_args_default(self, multi_journal_config):
        args = parse_args(["some", "text"])
        args = get_journal_name(args, multi_journal_config)
        assert args.journal_name == DEFAULT_JOURNAL_KEY
        assert args.text == ["some", "text"]

    def test_get_journal_name_from_args_specific(self, multi_journal_config):
        args = parse_args(["work:", "meeting", "notes"])
        args = get_journal_name(args, multi_journal_config)
        assert args.journal_name == "work"
        assert args.text == ["meeting", "notes"]

    def test_get_journal_name_nonexistent_stays_default(self, multi_journal_config):
        args = parse_args(["nonexistent:", "text"])
        args = get_journal_name(args, multi_journal_config)
        assert args.journal_name == DEFAULT_JOURNAL_KEY
        assert args.text == ["nonexistent:", "text"]


class TestValidateJournalName:
    def test_validate_journal_name_valid(self, multi_journal_config):
        validate_journal_name("default", multi_journal_config)
        validate_journal_name("work", multi_journal_config)
        validate_journal_name("personal", multi_journal_config)

    def test_validate_journal_name_invalid(self, multi_journal_config):
        with pytest.raises(JrnlException):
            validate_journal_name("nonexistent", multi_journal_config)


class TestDefaultAndSpecifiedJournalMixing:
    def test_default_journal_string_path(self, mixed_journals_config):
        scoped = scope_config(mixed_journals_config.copy(), "default")
        assert "journal" in scoped
        assert scoped["journal"].endswith("default.txt")

    def test_work_journal_dict_path(self, mixed_journals_config):
        scoped = scope_config(mixed_journals_config.copy(), "work")
        assert scoped["journal"].endswith("work.txt")
        assert scoped["tagsymbols"] == "@#"

    def test_default_journal_no_prefix_in_args(self, mixed_journals_config):
        args = parse_args(["entry", "text"])
        args = get_journal_name(args, mixed_journals_config)
        assert args.journal_name == "default"
        assert args.text == ["entry", "text"]

    def test_work_journal_prefix_in_args(self, mixed_journals_config):
        args = parse_args(["work:", "meeting", "notes"])
        args = get_journal_name(args, mixed_journals_config)
        assert args.journal_name == "work"
        assert args.text == ["meeting", "notes"]

    def test_scope_config_inherits_global(self, mixed_journals_config):
        default_scoped = scope_config(mixed_journals_config.copy(), "default")
        work_scoped = scope_config(mixed_journals_config.copy(), "work")

        assert default_scoped["editor"] == mixed_journals_config["editor"]
        assert work_scoped["editor"] == mixed_journals_config["editor"]

        assert default_scoped["default_hour"] == mixed_journals_config["default_hour"]
        assert work_scoped["default_hour"] == mixed_journals_config["default_hour"]


class TestMultiJournalMixedTypes:
    def test_mixed_type_config_has_all_journals(self, multi_journal_config_mixed_types):
        config = multi_journal_config_mixed_types
        assert "default" in config["journals"]
        assert "folder" in config["journals"]
        assert "encrypted" in config["journals"]

    def test_mixed_type_scoped_configs(self, multi_journal_config_mixed_types):
        config = multi_journal_config_mixed_types
        default_scoped = scope_config(config.copy(), "default")
        folder_scoped = scope_config(config.copy(), "folder")
        encrypted_scoped = scope_config(config.copy(), "encrypted")

        assert default_scoped["tagsymbols"] == "@"
        assert folder_scoped["tagsymbols"] == "#"
        assert encrypted_scoped["tagsymbols"] == "@!"
        assert encrypted_scoped["encrypt"] is True

    def test_folder_journal_data_isolation(self, multi_journal_config_with_folder):
        config = multi_journal_config_with_folder
        default_config = scope_config(config.copy(), "default")
        notes_config = scope_config(config.copy(), "notes")

        default_j = Journal(name="default", **default_config)
        folder_j = Folder(name="notes", **notes_config)

        default_j.new_entry(
            "2023-01-01 09:00: Default entry @defaulttag",
            date=datetime.datetime(2023, 1, 1, 9, 0),
        )

        folder_path = notes_config["journal"]
        os.makedirs(os.path.join(folder_path, "2023", "01"), exist_ok=True)
        with open(os.path.join(folder_path, "2023", "01", "15.txt"), "w") as f:
            f.write("[2023-01-15 09:00] Folder entry #foldertag\n")

        folder_j.open()

        assert len(default_j) == 1
        assert len(folder_j) == 1

        assert "@defaulttag" in default_j.entries[0].tags
        assert "#foldertag" not in default_j.entries[0].tags

        assert "#foldertag" in folder_j.entries[0].tags
        assert "@defaulttag" not in folder_j.entries[0].tags

    def test_folder_and_plain_journal_tag_search_isolation(
        self, multi_journal_config_with_folder
    ):
        config = multi_journal_config_with_folder
        default_config = scope_config(config.copy(), "default")
        notes_config = scope_config(config.copy(), "notes")

        default_j = Journal(name="default", **default_config)
        folder_j = Folder(name="notes", **notes_config)

        default_j.new_entry(
            "2023-01-01 09:00: Shared @topic in default",
            date=datetime.datetime(2023, 1, 1, 9, 0),
        )
        default_j.new_entry(
            "2023-01-02 09:00: Only default entry",
            date=datetime.datetime(2023, 1, 2, 9, 0),
        )

        folder_path = notes_config["journal"]
        os.makedirs(os.path.join(folder_path, "2023", "01"), exist_ok=True)
        with open(os.path.join(folder_path, "2023", "01", "15.txt"), "w") as f:
            f.write("[2023-01-15 09:00] Shared #topic in folder\n")

        folder_j.open()

        default_j.filter(tags=["@topic"])
        assert len(default_j) == 1

        folder_j.filter(tags=["#topic"])
        assert len(folder_j) == 1

    def test_encrypted_journal_data_isolation(self, tmp_path):
        from jrnl.encryption.NoEncryption import NoEncryption

        plain_path = str(tmp_path / "plain.journal")
        enc_path = str(tmp_path / "encrypted.journal")

        plain_j = Journal(
            name="plain",
            journal=plain_path,
            tagsymbols="@",
            timeformat="%Y-%m-%d %H:%M",
            default_hour=9,
            default_minute=0,
            highlight=True,
            linewrap=79,
            indent_character="|",
        )
        enc_j = Journal(
            name="encrypted",
            journal=enc_path,
            tagsymbols="!",
            timeformat="%Y-%m-%d %H:%M",
            default_hour=9,
            default_minute=0,
            highlight=True,
            linewrap=79,
            indent_character="|",
        )

        plain_j.new_entry(
            "2023-01-01 09:00: Plain entry @plaintag",
            date=datetime.datetime(2023, 1, 1, 9, 0),
        )
        enc_j.new_entry(
            "2023-01-01 09:00: Encrypted entry !enctag",
            date=datetime.datetime(2023, 1, 1, 9, 0),
        )

        enc_j.encryption_method = NoEncryption(enc_path, enc_j.config)
        enc_j.write()

        enc_j2 = Journal(
            name="encrypted",
            journal=enc_path,
            tagsymbols="!",
            timeformat="%Y-%m-%d %H:%M",
            default_hour=9,
            default_minute=0,
            highlight=True,
            linewrap=79,
            indent_character="|",
        )
        enc_j2.encryption_method = NoEncryption(enc_path, enc_j2.config)
        enc_j2.open()

        assert len(plain_j) == 1
        assert len(enc_j2) == 1

        assert "@plaintag" in plain_j.entries[0].tags
        assert "!enctag" not in plain_j.entries[0].tags

        assert "!enctag" in enc_j2.entries[0].tags
        assert "@plaintag" not in enc_j2.entries[0].tags

    def test_encrypted_journal_tag_search_round_trip(self, tmp_path):
        from jrnl.encryption.NoEncryption import NoEncryption

        enc_path = str(tmp_path / "encrypted.journal")

        enc_j = Journal(
            name="encrypted",
            journal=enc_path,
            tagsymbols="@",
            timeformat="%Y-%m-%d %H:%M",
            default_hour=9,
            default_minute=0,
            highlight=True,
            linewrap=79,
            indent_character="|",
        )
        enc_j.new_entry(
            "2023-01-01 09:00: First @alpha",
            date=datetime.datetime(2023, 1, 1, 9, 0),
        )
        enc_j.new_entry(
            "2023-01-02 09:00: Second @beta and @alpha",
            date=datetime.datetime(2023, 1, 2, 9, 0),
        )
        enc_j.new_entry(
            "2023-01-03 09:00: Third @beta only",
            date=datetime.datetime(2023, 1, 3, 9, 0),
        )

        enc_j.encryption_method = NoEncryption(enc_path, enc_j.config)
        enc_j.write()

        enc_j2 = Journal(
            name="encrypted",
            journal=enc_path,
            tagsymbols="@",
            timeformat="%Y-%m-%d %H:%M",
            default_hour=9,
            default_minute=0,
            highlight=True,
            linewrap=79,
            indent_character="|",
        )
        enc_j2.encryption_method = NoEncryption(enc_path, enc_j2.config)
        enc_j2.open()

        enc_j2.filter(tags=["@alpha"])
        assert len(enc_j2) == 2

    def test_folder_journal_date_isolation(self, multi_journal_config_with_folder):
        config = multi_journal_config_with_folder
        default_config = scope_config(config.copy(), "default")
        notes_config = scope_config(config.copy(), "notes")

        default_j = Journal(name="default", **default_config)
        default_j.new_entry(
            "2023-01-01 09:00: January default entry",
            date=datetime.datetime(2023, 1, 1, 9, 0),
        )
        default_j.new_entry(
            "2023-06-15 12:00: June default entry",
            date=datetime.datetime(2023, 6, 15, 12, 0),
        )

        folder_path = notes_config["journal"]
        os.makedirs(os.path.join(folder_path, "2023", "01"), exist_ok=True)
        with open(os.path.join(folder_path, "2023", "01", "10.txt"), "w") as f:
            f.write("[2023-01-10 09:00] January folder entry\n")

        folder_j = Folder(name="notes", **notes_config)
        folder_j.open()

        default_j.filter(month="1")
        assert len(default_j) == 1
        assert default_j.entries[0].date.month == 1

        folder_j.filter(month="1")
        assert len(folder_j) == 1
        assert folder_j.entries[0].date.month == 1
