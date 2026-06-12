# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import datetime
import re
import time

import pytest

from jrnl.journals.Entry import Entry
from jrnl.journals.Journal import Journal
from jrnl.plugins.fancy_exporter import FancyExporter
from jrnl.plugins.pretty_exporter import PrettyExporter


def _base_config(linewrap, indent_character="|"):
    return {
        "journal": "journal.txt",
        "encrypt": False,
        "default_hour": 9,
        "default_minute": 0,
        "timeformat": "%Y-%m-%d %H:%M",
        "tagsymbols": "@",
        "highlight": False,
        "linewrap": linewrap,
        "indent_character": indent_character,
        "colors": {"body": "none", "date": "none", "tags": "none", "title": "none"},
    }


def _strip_ansi(text):
    """Remove ANSI escape sequences from the given text."""
    ansi_escape = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
    return ansi_escape.sub("", text)


def _max_line_len_visual(text):
    """Return the maximum visual line length (ANSI stripped)."""
    return max(len(_strip_ansi(line)) for line in text.split("\n")) if text else 0


def _make_journal(linewrap, entries_data):
    j = Journal("test")
    j.config = _base_config(linewrap)
    j.entries = [
        Entry(j, date=d, text=t, starred=s) for d, t, s in entries_data
    ]
    return j


def _long_text_and_body():
    return (
        "This is a very very very very very very very very very very very very "
        "very very very very long title that needs to be wrapped properly by the "
        "terminal formatter so that it does not exceed the configured line width, "
        "yeah.\n"
        "And here is the body, which also contains extremely long sentences that "
        "must be wrapped according to the same column width configuration, with "
        "some 中文日本語한국어 mixed in to ensure CJK wide characters are handled "
        "without breaking the layout @test @long @wrapped"
    )


# ---------------------------------------------------------------------------
# Pretty format tests
# ---------------------------------------------------------------------------


class TestPrettyLineWrapBehavior:
    """Pretty 格式在不同终端宽度下的行宽、自动换行、列宽稳定性测试。"""

    @pytest.mark.parametrize("linewrap", [40, 60, 80, 100, 120, 200])
    def test_max_visual_line_width_respects_linewrap(self, linewrap):
        """任意行的视觉宽度（去除 ANSI 后）不应超过 linewrap 配置。"""
        journal = _make_journal(
            linewrap,
            [
                (
                    datetime.datetime(2023, 1, 1, 10, 0),
                    _long_text_and_body(),
                    False,
                )
            ],
        )
        output = PrettyExporter.export_journal(journal)
        max_len = _max_line_len_visual(output)
        assert max_len <= linewrap, (
            f"Pretty output max visual line length {max_len} exceeds "
            f"linewrap={linewrap}"
        )

    @pytest.mark.parametrize("linewrap", [40, 60, 80, 120])
    def test_body_lines_are_indented(self, linewrap):
        """Pretty 格式正文行必须以缩进字符开头。"""
        journal = _make_journal(
            linewrap,
            [
                (
                    datetime.datetime(2023, 1, 1, 10, 0),
                    "Title line.\nBody line one.\nBody line two with more text.",
                    False,
                )
            ],
        )
        output = PrettyExporter.export_journal(journal)
        lines = [_strip_ansi(l) for l in output.split("\n")]
        # Skip the title line (first non-empty line) and empty trailing lines.
        nonempty = [l for l in lines if l.strip()]
        # Title line starts with the date, body lines start with the indent char.
        title_line = nonempty[0]
        assert not title_line.startswith("| "), "Title line should not be indented"
        body_lines = nonempty[1:]
        for bl in body_lines:
            assert bl.startswith("| "), (
                f"Pretty body line does not start with indent: {bl!r}"
            )

    @pytest.mark.parametrize("linewrap", [40, 60, 80, 120])
    def test_output_deterministic_bytes(self, linewrap):
        """相同配置下两次导出字节级一致。"""
        journal = _make_journal(
            linewrap,
            [
                (
                    datetime.datetime(2023, 1, 1, 10, 0),
                    _long_text_and_body(),
                    False,
                ),
                (
                    datetime.datetime(2023, 1, 2, 11, 0),
                    "Another entry.\nMore body text here.",
                    True,
                ),
            ],
        )
        out1 = PrettyExporter.export_journal(journal).encode("utf-8")
        out2 = PrettyExporter.export_journal(journal).encode("utf-8")
        assert out1 == out2

    @pytest.mark.parametrize(
        "linewrap,indent",
        [(80, "|"), (80, ">"), (80, ""), (100, "|")],
    )
    def test_indent_character_config_applied(self, linewrap, indent):
        """缩进字符配置必须正确应用。"""
        cfg = _base_config(linewrap, indent_character=indent)
        j = Journal("test")
        j.config = cfg
        j.entries = [
            Entry(
                j,
                date=datetime.datetime(2023, 1, 1),
                text="Title.\nBody line here.",
                starred=False,
            )
        ]
        output = PrettyExporter.export_journal(j)
        plain = _strip_ansi(output)
        lines = [l for l in plain.split("\n") if l.strip()]
        if indent:
            prefix = indent.rstrip() + " "
            # body lines must start with the prefix
            for bl in lines[1:]:
                assert bl.startswith(prefix), (
                    f"Body line {bl!r} does not start with indent {prefix!r}"
                )
        else:
            # No indent: body lines should not start with "| "
            for bl in lines[1:]:
                assert not bl.startswith("| "), (
                    f"Body line {bl!r} has unexpected indent when indent_character='' "
                )

    def test_matches_journal_pprint(self):
        """PrettyExporter 输出必须与 Journal.pprint() 逐字节一致。"""
        journal = _make_journal(
            80,
            [
                (datetime.datetime(2023, 1, 1, 10, 0), "Entry one.\nBody.", False),
                (datetime.datetime(2023, 1, 2, 11, 0), "Entry two.\nBody.", True),
            ],
        )
        assert (
            PrettyExporter.export_journal(journal).encode("utf-8")
            == journal.pprint().encode("utf-8")
        )


class TestPrettyMassRender:
    """Pretty 格式在大体量日记下的输出稳定性与渲染速度测试。"""

    NUM_ENTRIES = 100

    @pytest.fixture(scope="class")
    def mass_journal(self):
        j = Journal("test")
        j.config = _base_config(80)
        base = datetime.datetime(2023, 1, 1)
        entries = []
        for i in range(self.NUM_ENTRIES):
            if i % 5 == 0:
                text = (
                    f"Long title entry #{i} that should cause wrapping because "
                    f"it has many many many many many many many many words in it "
                    f"so that the linewrap logic triggers.\n"
                    f"And the body also has some content that might need wrapping "
                    f"too depending on how long we make this sentence go on and on "
                    f"until it reaches the configured column limit @tag{i} @long"
                )
            else:
                text = f"Short entry {i}. Some body text here @tag{i} @short"
            entries.append(
                Entry(j, date=base + datetime.timedelta(hours=i), text=text, starred=(i % 11 == 0))
            )
        j.entries = entries
        return j

    def test_mass_render_max_line_width(self, mass_journal):
        """100 条日记渲染后，任意视觉行宽不超过 linewrap=80。"""
        output = PrettyExporter.export_journal(mass_journal)
        max_len = _max_line_len_visual(output)
        assert max_len <= 80, f"Max visual line width {max_len} exceeds 80"

    def test_mass_render_line_count_sanity(self, mass_journal):
        """100 条日记至少 200 行输出（每条至少 title+body）。"""
        output = PrettyExporter.export_journal(mass_journal)
        line_count = len(output.split("\n"))
        assert line_count >= self.NUM_ENTRIES * 2, (
            f"Only {line_count} lines for {self.NUM_ENTRIES} entries"
        )

    def test_mass_render_time_budget(self, mass_journal):
        """100 条日记 pretty 渲染必须在 3 秒内完成。"""
        start = time.perf_counter()
        PrettyExporter.export_journal(mass_journal)
        elapsed = time.perf_counter() - start
        assert elapsed < 3.0, f"Pretty render of {self.NUM_ENTRIES} entries took {elapsed:.2f}s"

    def test_mass_render_all_tags_present(self, mass_journal):
        """每条日记的 @tag{i} 都必须出现在输出中。"""
        output = PrettyExporter.export_journal(mass_journal)
        for i in range(self.NUM_ENTRIES):
            assert f"@tag{i}" in output, f"@tag{i} missing from pretty output"

    def test_mass_render_output_nonempty_for_each_entry(self, mass_journal):
        """每条日记的标题必须在输出中可识别。"""
        output = PrettyExporter.export_journal(mass_journal)
        for i in (0, 10, 50, 99):
            assert str(i) in output, f"Entry index {i} not present in output"


# ---------------------------------------------------------------------------
# Fancy format tests
# ---------------------------------------------------------------------------


class TestFancyLineWrapBehavior:
    """Fancy 格式在不同终端宽度下的行宽、自动换行、列宽稳定性测试。"""

    @pytest.mark.parametrize("linewrap", [40, 60, 80, 100, 120, 200])
    def test_every_line_exactly_linewrap_chars(self, linewrap):
        """Fancy 格式每一行（盒子边框）的字符数必须精确等于 linewrap。"""
        journal = _make_journal(
            linewrap,
            [
                (
                    datetime.datetime(2023, 1, 1, 10, 0),
                    _long_text_and_body(),
                    False,
                )
            ],
        )
        output = FancyExporter.export_journal(journal)
        for idx, line in enumerate(output.split("\n")):
            if line:
                assert len(line) == linewrap, (
                    f"Fancy line #{idx} length={len(line)} != linewrap={linewrap}: "
                    f"{line!r}"
                )

    @pytest.mark.parametrize("linewrap", [40, 60, 80, 120])
    def test_output_deterministic_bytes(self, linewrap):
        """相同配置下两次导出字节级一致。"""
        journal = _make_journal(
            linewrap,
            [
                (
                    datetime.datetime(2023, 1, 1, 10, 0),
                    _long_text_and_body(),
                    False,
                ),
                (
                    datetime.datetime(2023, 1, 2, 11, 0),
                    "Another entry.\nMore body text.",
                    True,
                ),
            ],
        )
        out1 = FancyExporter.export_journal(journal).encode("utf-8")
        out2 = FancyExporter.export_journal(journal).encode("utf-8")
        assert out1 == out2

    @pytest.mark.parametrize("linewrap", [40, 60, 80, 120])
    def test_box_structure_has_borders(self, linewrap):
        """Fancy 盒子必须含有关键边框字符。"""
        journal = _make_journal(
            linewrap,
            [
                (
                    datetime.datetime(2023, 1, 1, 10, 0),
                    "Title here.\nBody content here.",
                    False,
                )
            ],
        )
        output = FancyExporter.export_journal(journal)
        assert "┎" in output  # top-left corner
        assert "╮" in output  # top-right corner
        assert "┖" in output  # bottom-left corner
        assert "┘" in output  # bottom-right corner
        assert "┃" in output  # left vertical
        assert "│" in output  # right vertical
        assert "╌" in output  # horizontal separator

    @pytest.mark.parametrize("linewrap", [60, 80, 120])
    def test_body_content_present_inside_box(self, linewrap):
        """Fancy 盒子内必须包含原始日记内容。"""
        journal = _make_journal(
            linewrap,
            [
                (
                    datetime.datetime(2023, 1, 1, 10, 0),
                    "UniqueKeywordXYZ.\nUniqueBodyABC here.",
                    False,
                )
            ],
        )
        output = FancyExporter.export_journal(journal)
        assert "UniqueKeywordXYZ" in output
        assert "UniqueBodyABC" in output
        assert "2023-01-01 10:00" in output

    def test_linewrap_too_small_for_date_raises(self):
        """linewrap 过小（无法容纳日期）必须抛出异常。"""
        from jrnl.exception import JrnlException

        journal = _make_journal(
            10,
            [
                (
                    datetime.datetime(2023, 1, 1, 10, 0),
                    "Short title.",
                    False,
                )
            ],
        )
        with pytest.raises(JrnlException):
            FancyExporter.export_journal(journal)


class TestFancyMassRender:
    """Fancy 格式在大体量日记下的输出稳定性与渲染速度测试。"""

    NUM_ENTRIES = 100

    @pytest.fixture(scope="class")
    def mass_journal(self):
        j = Journal("test")
        j.config = _base_config(80)
        base = datetime.datetime(2023, 1, 1)
        entries = []
        for i in range(self.NUM_ENTRIES):
            if i % 5 == 0:
                text = (
                    f"Long title entry #{i} that should cause wrapping because "
                    f"it has many many many many many many many many words in it "
                    f"so that the linewrap logic triggers.\n"
                    f"And the body also has some content that might need wrapping "
                    f"too depending on how long we make this sentence go on and on "
                    f"until it reaches the configured column limit @tag{i} @long"
                )
            else:
                text = f"Short entry {i}. Some body text here @tag{i} @short"
            entries.append(
                Entry(j, date=base + datetime.timedelta(hours=i), text=text, starred=(i % 11 == 0))
            )
        j.entries = entries
        return j

    def test_mass_render_every_line_exactly_80(self, mass_journal):
        """100 条 fancy 渲染后，任意非空行字符数精确等于 linewrap=80。"""
        output = FancyExporter.export_journal(mass_journal)
        for idx, line in enumerate(output.split("\n")):
            if line:
                assert len(line) == 80, (
                    f"Fancy line #{idx} length={len(line)} != 80: {line!r}"
                )

    def test_mass_render_time_budget(self, mass_journal):
        """100 条日记 fancy 渲染必须在 3 秒内完成。"""
        start = time.perf_counter()
        FancyExporter.export_journal(mass_journal)
        elapsed = time.perf_counter() - start
        assert elapsed < 3.0, f"Fancy render of {self.NUM_ENTRIES} entries took {elapsed:.2f}s"

    def test_mass_render_box_count_matches_entries(self, mass_journal):
        """100 条 fancy 渲染必须产生 100 个盒子（通过底部左角计数）。"""
        output = FancyExporter.export_journal(mass_journal)
        box_count = output.count("┖")
        assert box_count == self.NUM_ENTRIES, (
            f"Expected {self.NUM_ENTRIES} boxes, got {box_count}"
        )

    def test_mass_render_all_tags_present(self, mass_journal):
        """每条日记的 @tag{i} 都必须出现在输出中。"""
        output = FancyExporter.export_journal(mass_journal)
        for i in range(self.NUM_ENTRIES):
            assert f"@tag{i}" in output, f"@tag{i} missing from fancy output"

    def test_mass_render_line_count_sanity(self, mass_journal):
        """100 条 fancy 渲染至少 500 行（每个盒子至少 5 行结构线）。"""
        output = FancyExporter.export_journal(mass_journal)
        line_count = len(output.split("\n"))
        assert line_count >= self.NUM_ENTRIES * 5, (
            f"Only {line_count} lines for {self.NUM_ENTRIES} fancy entries"
        )
