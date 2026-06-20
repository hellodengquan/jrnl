# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

"""Unit tests for:
- batch rename failure -> history stack cleanup (Journal.commit/abort pending)
- normalization of emoji / VS-variant tags
- search_index rebuild -> immediate query consistency / latency sanity
"""

import os
import shutil
import tempfile
import time
import unicodedata
from dataclasses import dataclass

import pytest

from jrnl.history import JournalHistory
from jrnl.history import HistoryEntry
from jrnl.journals.Entry import Entry
from jrnl.journals.Journal import Journal
from jrnl.normalization import normalize_tag
from jrnl.normalization import tags_match
from jrnl.search_index import JournalSearchIndex


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_journal_dir(tmp_path):
    """Yield a temp directory, clean up afterwards."""
    yield tmp_path
    shutil.rmtree(tmp_path, ignore_errors=True)


def make_journal(tmpdir, name="t", entries=None):
    j_path = os.path.join(tmpdir, f"{name}.journal")
    j = Journal(
        name=name,
        journal=j_path,
        tagsymbols="@",
        timeformat="%Y-%m-%d %H:%M",
    )
    j.open()
    for i, (date, body) in enumerate(entries or []):
        j.new_entry(f"{date}: {body}")
    j.write()
    return j


# ---------------------------------------------------------------------------
# 1) Batch rename failure -> history stack cleanup & consistency
# ---------------------------------------------------------------------------


class TestBatchHistoryCleanup:
    def test_pending_history_not_committed_before_write(self, tmp_journal_dir):
        j = make_journal(
            tmp_journal_dir,
            entries=[
                ("2024-01-01 10:00", "alpha @fruit"),
                ("2024-01-02 11:00", "beta @fruit"),
                ("2024-01-03 12:00", "gamma @veg"),
            ],
        )
        # rename_tag(commit_history=False) must NOT push to real undo stack
        assert j.can_undo is False
        n, rb = j.rename_tag("@fruit", "@produce", commit_history=False)
        assert n == 2
        assert j.can_undo is False
        assert len(j._pending_history) == 1

    def test_commit_pending_flushes_to_undo_stack(self, tmp_journal_dir):
        j = make_journal(
            tmp_journal_dir,
            entries=[
                ("2024-01-01 10:00", "alpha @fruit"),
                ("2024-01-02 11:00", "beta @fruit"),
            ],
        )
        j.rename_tag("@fruit", "@produce", commit_history=False)
        assert j.can_undo is False

        committed = j._commit_pending_history()
        assert committed == 1
        assert j.can_undo is True
        assert j.history.undo_count == 1
        assert len(j._pending_history) == 0

    def test_abort_pending_clears_queue(self, tmp_journal_dir):
        j = make_journal(
            tmp_journal_dir,
            entries=[
                ("2024-01-01 10:00", "alpha @fruit"),
            ],
        )
        j.rename_tag("@fruit", "@produce", commit_history=False)
        discarded = j._abort_pending_history()
        assert discarded == 1
        assert j.can_undo is False
        assert len(j._pending_history) == 0

    def test_abort_pending_also_pops_last_n_from_stack(self, tmp_journal_dir):
        j = make_journal(
            tmp_journal_dir,
            entries=[
                ("2024-01-01 10:00", "alpha @fruit"),
                ("2024-01-02 11:00", "beta @fruit"),
                ("2024-01-03 12:00", "gamma @veg"),
            ],
        )
        # Simulate: batch of 3 journals, but only 2 got committed before
        # failure. 3rd (pending) must be discarded + pop 2 from real stack.
        j.rename_tag("@fruit", "@produce")  # commit #1
        j.rename_tag("@veg", "@veggie")  # commit #2
        j.rename_tag("@veggie", "@grocery", commit_history=False)  # pending #3
        assert j.history.undo_count == 2
        assert len(j._pending_history) == 1

        discarded = j._abort_pending_history(also_pop_last_n=2)
        assert discarded == 3
        assert j.history.undo_count == 0
        assert j.can_redo is False  # pop should also clear redo stack

    def test_write_failure_leaves_history_clean(self, tmp_journal_dir, monkeypatch):
        """Simulate the exact postconfig_rename_tag flow on one journal."""
        j = make_journal(
            tmp_journal_dir,
            entries=[
                ("2024-01-01 10:00", "alpha @fruit"),
                ("2024-01-02 11:00", "beta @fruit"),
            ],
        )

        modified, rollback = j.rename_tag("@fruit", "@produce", commit_history=False)
        assert modified == 2
        assert j.can_undo is False

        # Simulate j.write() failing -> caller must abort pending + rollback
        j.rollback_tag_rename(rollback)
        j.search_index.rename_tag_in_index("@produce", "@fruit", verbose=False)
        discarded = j._abort_pending_history()

        # State fully clean: no pending, no undo, fruit count restored
        assert discarded == 1
        assert j.can_undo is False
        assert j.count_tag_occurrences("@fruit") == 2
        assert j.count_tag_occurrences("@produce") == 0

    def test_committed_then_cross_journal_rollback(self, tmp_journal_dir):
        """When 2 journals commit successfully and the 3rd fails, the first
        two must still have their in-memory undo entries popped after
        rollback (since their on-disk state was reverted by rollback).
        """
        j1 = make_journal(
            tmp_journal_dir,
            name="j1",
            entries=[("2024-01-01 10:00", "A @old")],
        )
        j2 = make_journal(
            tmp_journal_dir,
            name="j2",
            entries=[("2024-01-02 11:00", "B @old")],
        )
        # j1 + j2 commit; simulate cross-journal failure afterwards
        j1.rename_tag("@old", "@new", commit_history=False)
        j1.write()
        j1._commit_pending_history()

        j2.rename_tag("@old", "@new", commit_history=False)
        j2.write()
        j2._commit_pending_history()

        # Caller performs rollback (files reverted + memory reverted)
        # then pops the stale undo entries
        for j in (j1, j2):
            # (In real flow this happens via _perform_rollback which
            # reverts j.entries + j.search_index in-memory state.)
            j._abort_pending_history(also_pop_last_n=1)

        assert j1.history.undo_count == 0
        assert j2.history.undo_count == 0
        assert j1.can_redo is False
        assert j2.can_redo is False


# ---------------------------------------------------------------------------
# 2) Emoji / presentation-selector normalization
# ---------------------------------------------------------------------------


class TestEmojiNormalization:
    def test_tag_regex_matches_emoji(self):
        text = "today @😀 I found a @🍎 and a @🚀-fast"
        regex = Entry.tag_regex("@")
        matches = regex.findall(text)
        assert "@😀" in matches
        assert "@🍎" in matches
        assert "@🚀-fast" in matches

    def test_tag_regex_matches_zwj_emoji_sequence(self):
        # U+1F468 U+200D U+1F469 U+200D U+1F467 = family: man, woman, girl
        family = "\U0001F468\u200D\U0001F469\u200D\U0001F467"
        text = f"today @{family} is family day"
        regex = Entry.tag_regex("@")
        matches = regex.findall(text)
        assert len(matches) == 1
        assert matches[0].startswith("@")
        assert "\U0001F468" in matches[0]
        assert "\u200D" in matches[0]

    def test_tag_regex_matches_cjk_and_emoji_in_same_tag(self):
        text = "@日本語日本🍣 sushi night"
        regex = Entry.tag_regex("@")
        matches = regex.findall(text)
        assert matches and matches[0].startswith("@日本語日本🍣")

    def test_normalize_strips_emoji_presentation_variants(self):
        # VS-15 (text) and VS-16 (emoji) should be equivalent
        plain = "@😀"
        vs_text = "@😀\ufe0e"
        vs_emoji = "@😀\ufe0f"
        assert normalize_tag(plain) == normalize_tag(vs_text)
        assert normalize_tag(plain) == normalize_tag(vs_emoji)
        assert tags_match(vs_text, vs_emoji) is True

    def test_normalize_mixed_emoji_and_text_case_fold(self):
        # emoji portion stays, text portion case-folds
        tag = "@🍎HELLO"
        expected_prefix = "@🍎hello"
        assert normalize_tag(tag) == expected_prefix

    def test_emoji_tag_survives_parse_through_entry(self, tmp_journal_dir):
        """Round-trip: parse tag via Entry._parse_tags, reload Journal."""
        j = make_journal(
            tmp_journal_dir,
            entries=[("2024-01-01 10:00", "tagged @😀 happy @🍎day")],
        )
        all_tags = {t.name for t in j.tags}
        assert normalize_tag("@😀") in all_tags
        # @🍎day == @🍎day (case folds to lowercase day)
        assert normalize_tag("@🍎day") in all_tags

        reload = Journal(
            name="t2",
            journal=j.config["journal"],
            tagsymbols="@",
            timeformat="%Y-%m-%d %H:%M",
        )
        reload.open()
        assert reload.count_tag_occurrences("@😀") == 1
        assert reload.count_tag_occurrences("@🍎DAY") == 1

    def test_keycap_emoji_tag_works(self):
        # "1️⃣" = '1' + FE0F + 20E3
        keycap = "1\ufe0f\u20e3"
        regex = Entry.tag_regex("@")
        matches = regex.findall(f"@{keycap} one")
        assert len(matches) == 1
        assert normalize_tag(matches[0]) == normalize_tag(f"@{keycap}")


# ---------------------------------------------------------------------------
# 3) Search index rebuild -> immediate query consistency / latency sanity
# ---------------------------------------------------------------------------


class TestSearchIndexRebuildConsistency:
    @staticmethod
    def _entries_with_tag(n, tag_prefix, seed_offset=0):
        """Generate n entries each with a random-ish body, containing a
        specific tag."""
        result = []
        for i in range(n):
            tag = f"@{tag_prefix}{i % 10}"
            date = f"2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d} 10:{i % 60:02d}"
            body = f"entry body number {i} {tag} lorem ipsum dolor sit amet"
            result.append((date, body))
        return result

    def test_rebuild_latency_is_sublinear_for_1000_entries(self, tmp_journal_dir):
        """Sanity check: rebuild on 1000 entries / ~10 unique tags should
        take < 0.5 s on a modern machine. (Not a strict perf SLA, mainly
        catches accidental O(n^2) bugs in rebuild.)
        """
        j = make_journal(
            tmp_journal_dir,
            entries=self._entries_with_tag(1000, "t"),
        )
        t0 = time.perf_counter()
        j.search_index.rebuild(verbose=False)
        elapsed = time.perf_counter() - t0
        # generous but catches catastrophic regressions
        assert elapsed < 0.5, f"rebuild took {elapsed:.2f}s, expected <0.5s"

    def test_rebuild_after_add_returns_all_matches(self, tmp_journal_dir):
        """After rebuild, entries_with_tag must return the same count as a
        naive scan over entries.
        """
        j = make_journal(
            tmp_journal_dir,
            entries=self._entries_with_tag(300, "tag"),
        )
        unique_tags = {
            t.name for t in j.tags if t.name.startswith("@tag")
        }
        for tag in unique_tags:
            via_index = len(j.search_index.entries_with_tag(tag))
            via_scan = sum(
                1 for e in j.entries if normalize_tag(tag) in e.tags
            )
            assert via_index == via_scan, (
                f"mismatch for {tag}: index={via_index} scan={via_scan}"
            )

    def test_rebuild_dirty_flag_reflects_subsequent_changes(self, tmp_journal_dir):
        j = make_journal(
            tmp_journal_dir,
            entries=[
                ("2024-01-01 10:00", "a @foo"),
                ("2024-01-02 11:00", "b @bar"),
            ],
        )
        j.search_index.rebuild(verbose=False)
        assert j.search_index.is_dirty is False

        j.rename_tag("@foo", "@baz")
        # rename_tag_in_index keeps index in sync, not dirty
        assert j.search_index.is_dirty is False
        assert len(j.search_index.entries_with_tag("@baz")) == 1
        assert len(j.search_index.entries_with_tag("@foo")) == 0

    def test_immediate_query_after_rebuild_matches_full_scan(self, tmp_journal_dir):
        """Critical consistency test: immediately after a force rebuild the
        results of entries_with_tag over every unique tag must be identical
        to a brute force scan over Journal.entries.tags (using normalized
        matching).
        """
        j = make_journal(
            tmp_journal_dir,
            entries=[
                ("2024-01-01 10:00", "X @alpha @beta"),
                ("2024-01-02 11:00", "Y @beta @gamma"),
                ("2024-01-03 12:00", "Z @gamma @delta @alpha"),
                ("2024-01-04 13:00", "W @epsilon"),
                ("2024-01-05 14:00", "V @alpha @epsilon @alpha"),
            ],
        )

        # Force rebuild
        j.search_index.mark_dirty()
        assert j.search_index.is_dirty is True
        j.search_index.rebuild(verbose=False)
        assert j.search_index.is_dirty is False

        expected_by_tag = {}
        for t in {t.name for t in j.tags}:
            expected_by_tag[t] = {
                idx
                for idx, e in enumerate(j.entries)
                if normalize_tag(t) in e.tags
            }

        for t, expected in expected_by_tag.items():
            got = j.search_index.entries_with_tag(t)
            assert got == expected, (
                f"Tag {t}: expected {sorted(expected)} got {sorted(got)}"
            )

    def test_rename_tag_updates_index_incrementally(self, tmp_journal_dir):
        """rename_tag_in_index + pending rename_tag path must produce the
        same index state a full rebuild would.
        """
        j = make_journal(
            tmp_journal_dir,
            entries=[
                ("2024-01-01 10:00", "@red @blue"),
                ("2024-01-02 11:00", "@red @green"),
                ("2024-01-03 12:00", "@blue @green"),
            ],
        )
        j.search_index.rebuild(verbose=False)
        j.rename_tag("@red", "@crimson")
        j.rename_tag("@green", "@moss")

        # Snapshot incremental index state
        via_incr = {
            "@crimson": sorted(j.search_index.entries_with_tag("@crimson")),
            "@moss": sorted(j.search_index.entries_with_tag("@moss")),
            "@blue": sorted(j.search_index.entries_with_tag("@blue")),
            "@red": sorted(j.search_index.entries_with_tag("@red")),
        }

        # Rebuild and compare
        j.search_index.rebuild(verbose=False)
        assert sorted(j.search_index.entries_with_tag("@crimson")) == via_incr["@crimson"]
        assert sorted(j.search_index.entries_with_tag("@moss")) == via_incr["@moss"]
        assert sorted(j.search_index.entries_with_tag("@blue")) == via_incr["@blue"]
        assert sorted(j.search_index.entries_with_tag("@red")) == via_incr["@red"]
        assert len(via_incr["@red"]) == 0  # no leftover @red entries
