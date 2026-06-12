# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import datetime
import os
import time
import tracemalloc
from xml.dom import minidom

import pytest

from jrnl.journals.Entry import Entry
from jrnl.journals.Journal import Journal
from jrnl.plugins.fancy_exporter import FancyExporter
from jrnl.plugins.json_exporter import JSONExporter
from jrnl.plugins.markdown_exporter import MarkdownExporter
from jrnl.plugins.pretty_exporter import PrettyExporter
from jrnl.plugins.xml_exporter import XMLExporter
from jrnl.plugins.yaml_exporter import YAMLExporter


JOURNAL_CONFIG = {
    "journal": "journal.txt",
    "encrypt": False,
    "default_hour": 9,
    "default_minute": 0,
    "timeformat": "%Y-%m-%d %H:%M",
    "tagsymbols": "@",
    "highlight": False,
    "linewrap": 80,
    "indent_character": "|",
    "colors": {"body": "none", "date": "none", "tags": "none", "title": "none"},
}

# Use a generous factor over baseline measurements to avoid flaky tests.
# Baseline (200 entries, ~34KB chars):
#   pretty: 619 ms / 0.68 MB
#   fancy:  107 ms / 1.04 MB
#   markdown: 20 ms / 0.31 MB
#   json:  25 ms / 0.56 MB
#   yaml:  50 ms / 0.41 MB
#   xml:   32 ms / 1.31 MB
#
# Baseline (1 very long entry, ~400KB chars):
#   each format roughly O(n) in size.
#
# Thresholds are set to ~5x of the per-byte rate, to absorb CI noise.

TIME_BUDGET_MS = {
    "pretty": 5000,
    "fancy": 2000,
    "markdown": 500,
    "json": 1000,
    "yaml": 1000,
    "xml": 1000,
}

MEMORY_BUDGET_MB = {
    "pretty": 15,
    "fancy": 20,
    "markdown": 10,
    "json": 15,
    "yaml": 15,
    "xml": 30,
}

NUM_MANY_ENTRIES = 200

ONE_LONG_ENTRY_CHARS = 200_000


def _build_many_entries_journal():
    journal = Journal("test")
    journal.config = JOURNAL_CONFIG
    entries = []
    base = datetime.datetime(2022, 1, 1, 0, 0)
    for i in range(NUM_MANY_ENTRIES):
        dt = base + datetime.timedelta(hours=i)
        if i % 10 == 0:
            body_lines = [f"Long entry #{i} with lots of content."]
            for j in range(30):
                body_lines.append(
                    f"Line {j}: 中文日本語한국어 😀😅🎉 🌟✨🌈 some text here."
                )
            body_lines.append("```python")
            body_lines.append("def hello():")
            body_lines.append("    return True")
            body_lines.append("```")
            text = "\n".join(body_lines) + f" @tag{i} @long"
            starred = i % 20 == 0
        else:
            text = f"Short entry {i}. 测试日本語한국어 😀 @short @tag{i}"
            starred = False
        entries.append(Entry(journal, date=dt, text=text, starred=starred))
    journal.entries = entries
    return journal


def _build_one_long_entry_journal():
    journal = Journal("test")
    journal.config = JOURNAL_CONFIG
    repeating_unit = "这是一段中文，with some English, 日本語テスト, 한국어, 😀😅🎉 🌟✨🌈. "
    needed_units = ONE_LONG_ENTRY_CHARS // len(repeating_unit) + 1
    long_body = (repeating_unit * needed_units)[:ONE_LONG_ENTRY_CHARS]
    text = (
        "Title for the super long entry.\n\n"
        + long_body
        + "\n\nEnd of long entry. @longentry @huge"
    )
    entry = Entry(
        journal,
        date=datetime.datetime(2023, 1, 1, 12, 0),
        text=text,
        starred=True,
    )
    journal.entries = [entry]
    return journal


@pytest.fixture(scope="module")
def many_entries_journal():
    return _build_many_entries_journal()


@pytest.fixture(scope="module")
def one_long_entry_journal():
    return _build_one_long_entry_journal()


def _time_and_memory(fn):
    tracemalloc.start()
    start = time.perf_counter()
    result = fn()
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    peak_mb = peak_bytes / (1024 * 1024)
    output_size = len(result.encode("utf-8")) if isinstance(result, str) else len(result)
    return result, elapsed_ms, peak_mb, output_size


def _render_xml_journal(journal):
    doc = minidom.Document()
    root = doc.createElement("journal")
    doc.appendChild(root)
    for entry in journal.entries:
        el = XMLExporter.entry_to_xml(entry, doc)
        if el.hasAttribute("starred"):
            el.setAttribute("starred", str(el.getAttribute("starred")))
        root.appendChild(el)
    return doc.toprettyxml()


def _render_yaml_journal(journal):
    return "".join(YAMLExporter.export_entry(e) for e in journal.entries)


# ---------------------------------------------------------------------------
# many entries: 200 entries, ~34KB chars
# ---------------------------------------------------------------------------


class TestManyEntriesPerformance:
    """多条堆叠日记（200 条，混合长短）场景的性能和内存回归测试。"""

    @pytest.mark.parametrize(
        "fmt_name,export_fn",
        [
            ("pretty", lambda j: PrettyExporter.export_journal(j)),
            ("markdown", lambda j: MarkdownExporter.export_journal(j)),
            ("json", lambda j: JSONExporter.export_journal(j)),
            ("fancy", lambda j: FancyExporter.export_journal(j)),
            ("yaml", _render_yaml_journal),
            ("xml", _render_xml_journal),
        ],
    )
    def test_time_budget(self, many_entries_journal, fmt_name, export_fn):
        _, elapsed_ms, _, _ = _time_and_memory(lambda: export_fn(many_entries_journal))
        assert elapsed_ms < TIME_BUDGET_MS[fmt_name], (
            f"Format '{fmt_name}' took {elapsed_ms:.1f} ms on {NUM_MANY_ENTRIES} "
            f"entries, exceeds budget {TIME_BUDGET_MS[fmt_name]} ms"
        )

    @pytest.mark.parametrize(
        "fmt_name,export_fn",
        [
            ("pretty", lambda j: PrettyExporter.export_journal(j)),
            ("markdown", lambda j: MarkdownExporter.export_journal(j)),
            ("json", lambda j: JSONExporter.export_journal(j)),
            ("fancy", lambda j: FancyExporter.export_journal(j)),
            ("yaml", _render_yaml_journal),
            ("xml", _render_xml_journal),
        ],
    )
    def test_memory_budget(self, many_entries_journal, fmt_name, export_fn):
        _, _, peak_mb, _ = _time_and_memory(lambda: export_fn(many_entries_journal))
        assert peak_mb < MEMORY_BUDGET_MB[fmt_name], (
            f"Format '{fmt_name}' peak memory {peak_mb:.2f} MB exceeds budget "
            f"{MEMORY_BUDGET_MB[fmt_name]} MB"
        )

    @pytest.mark.parametrize(
        "fmt_name,export_fn",
        [
            ("pretty", lambda j: PrettyExporter.export_journal(j)),
            ("markdown", lambda j: MarkdownExporter.export_journal(j)),
            ("json", lambda j: JSONExporter.export_journal(j)),
            ("fancy", lambda j: FancyExporter.export_journal(j)),
            ("yaml", _render_yaml_journal),
            ("xml", _render_xml_journal),
        ],
    )
    def test_output_nonempty_and_sane_size(
        self, many_entries_journal, fmt_name, export_fn
    ):
        result, _, _, output_size = _time_and_memory(
            lambda: export_fn(many_entries_journal)
        )
        assert isinstance(result, str) and len(result) > 0
        # 200 entries -> output must be at least a few KB
        assert output_size >= 2000, (
            f"Format '{fmt_name}' output only {output_size} bytes for "
            f"{NUM_MANY_ENTRIES} entries"
        )

    @pytest.mark.parametrize(
        "fmt_name,export_fn",
        [
            ("pretty", lambda j: PrettyExporter.export_journal(j)),
            ("markdown", lambda j: MarkdownExporter.export_journal(j)),
            ("json", lambda j: JSONExporter.export_journal(j)),
            ("fancy", lambda j: FancyExporter.export_journal(j)),
            ("yaml", _render_yaml_journal),
            ("xml", _render_xml_journal),
        ],
    )
    def test_deterministic_output_bytes(
        self, many_entries_journal, fmt_name, export_fn
    ):
        """同一份 journal 连续两次导出必须字节级一致（防止随数据量增大出现非确定性）。"""
        out1 = export_fn(many_entries_journal).encode("utf-8")
        out2 = export_fn(many_entries_journal).encode("utf-8")
        assert out1 == out2, (
            f"Format '{fmt_name}' produced different bytes on consecutive "
            f"exports for same {NUM_MANY_ENTRIES}-entry journal"
        )

    def test_all_entries_present_pretty(self, many_entries_journal):
        result = PrettyExporter.export_journal(many_entries_journal)
        # Each entry contains "@tag<idx>", so check a representative sample
        for i in (0, 50, 100, 150, 199):
            assert f"@tag{i}" in result

    def test_all_entries_present_json(self, many_entries_journal):
        import json as _json

        result = JSONExporter.export_journal(many_entries_journal)
        parsed = _json.loads(result)
        assert len(parsed["entries"]) == NUM_MANY_ENTRIES
        # Each entry body contains @tag<i>
        for i, entry in enumerate(parsed["entries"]):
            assert f"@tag{i}" in (entry["title"] + " " + entry["body"])

    def test_all_entries_present_markdown(self, many_entries_journal):
        result = MarkdownExporter.export_journal(many_entries_journal)
        for i in (0, 50, 100, 150, 199):
            assert f"@tag{i}" in result


# ---------------------------------------------------------------------------
# one long entry: single ~400KB character entry
# ---------------------------------------------------------------------------


class TestOneLongEntryPerformance:
    """单条超长日记（~200KB chars）场景的性能和内存回归测试。"""

    @pytest.mark.parametrize(
        "fmt_name,export_fn",
        [
            ("pretty", lambda j: PrettyExporter.export_journal(j)),
            ("markdown", lambda j: MarkdownExporter.export_journal(j)),
            ("json", lambda j: JSONExporter.export_journal(j)),
            ("fancy", lambda j: FancyExporter.export_journal(j)),
            ("yaml", _render_yaml_journal),
            ("xml", _render_xml_journal),
        ],
    )
    def test_time_budget(self, one_long_entry_journal, fmt_name, export_fn):
        _, elapsed_ms, _, _ = _time_and_memory(
            lambda: export_fn(one_long_entry_journal)
        )
        assert elapsed_ms < TIME_BUDGET_MS[fmt_name], (
            f"Format '{fmt_name}' took {elapsed_ms:.1f} ms on one long entry "
            f"({ONE_LONG_ENTRY_CHARS} chars), exceeds budget "
            f"{TIME_BUDGET_MS[fmt_name]} ms"
        )

    @pytest.mark.parametrize(
        "fmt_name,export_fn",
        [
            ("pretty", lambda j: PrettyExporter.export_journal(j)),
            ("markdown", lambda j: MarkdownExporter.export_journal(j)),
            ("json", lambda j: JSONExporter.export_journal(j)),
            ("fancy", lambda j: FancyExporter.export_journal(j)),
            ("yaml", _render_yaml_journal),
            ("xml", _render_xml_journal),
        ],
    )
    def test_memory_budget(self, one_long_entry_journal, fmt_name, export_fn):
        _, _, peak_mb, _ = _time_and_memory(
            lambda: export_fn(one_long_entry_journal)
        )
        assert peak_mb < MEMORY_BUDGET_MB[fmt_name], (
            f"Format '{fmt_name}' peak memory {peak_mb:.2f} MB exceeds budget "
            f"{MEMORY_BUDGET_MB[fmt_name]} MB on one long entry"
        )

    @pytest.mark.parametrize(
        "fmt_name,export_fn",
        [
            ("pretty", lambda j: PrettyExporter.export_journal(j)),
            ("markdown", lambda j: MarkdownExporter.export_journal(j)),
            ("json", lambda j: JSONExporter.export_journal(j)),
            ("fancy", lambda j: FancyExporter.export_journal(j)),
            ("yaml", _render_yaml_journal),
            ("xml", _render_xml_journal),
        ],
    )
    def test_output_proportional_size(
        self, one_long_entry_journal, fmt_name, export_fn
    ):
        """输出至少达到输入数据量级的合理比例，防止大段内容被错误丢弃。"""
        result, _, _, output_size = _time_and_memory(
            lambda: export_fn(one_long_entry_journal)
        )
        assert isinstance(result, str)
        # JSON may add overhead, but all formats should retain at least the input
        # size (minus markup/compression allowance of 0.5x).
        min_expected = ONE_LONG_ENTRY_CHARS // 2
        assert output_size >= min_expected, (
            f"Format '{fmt_name}' produced only {output_size} bytes for "
            f"{ONE_LONG_ENTRY_CHARS}-char input (>= {min_expected} expected)"
        )

    def test_long_entry_content_preserved_pretty(self, one_long_entry_journal):
        result = PrettyExporter.export_journal(one_long_entry_journal)
        assert "@longentry" in result
        assert "@huge" in result
        assert "这是一段中文" in result

    def test_long_entry_content_preserved_json(self, one_long_entry_journal):
        import json as _json

        result = JSONExporter.export_journal(one_long_entry_journal)
        parsed = _json.loads(result)
        assert len(parsed["entries"]) == 1
        entry = parsed["entries"][0]
        combined = entry["title"] + " " + entry["body"]
        assert "@longentry" in combined
        assert "@huge" in combined
        assert "这是一段中文" in combined

    def test_long_entry_content_preserved_markdown(self, one_long_entry_journal):
        result = MarkdownExporter.export_journal(one_long_entry_journal)
        assert "@longentry" in result
        assert "@huge" in result
        assert "这是一段中文" in result

    def test_long_entry_content_preserved_fancy(self, one_long_entry_journal):
        result = FancyExporter.export_journal(one_long_entry_journal)
        assert "@longentry" in result
        assert "@huge" in result
        assert "这是一段中文" in result
