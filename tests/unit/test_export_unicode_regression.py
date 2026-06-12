# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import datetime
import json
import os
from xml.dom import minidom

import pytest

from jrnl.journals.Entry import Entry
from jrnl.journals.Journal import Journal
from jrnl.plugins import get_exporter
from jrnl.plugins.fancy_exporter import FancyExporter
from jrnl.plugins.json_exporter import JSONExporter
from jrnl.plugins.markdown_exporter import MarkdownExporter
from jrnl.plugins.pretty_exporter import PrettyExporter
from jrnl.plugins.xml_exporter import XMLExporter
from jrnl.plugins.yaml_exporter import YAMLExporter


BASELINE_DIR = os.path.join(os.path.dirname(__file__), "export_baselines")

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
    "colors": {
        "body": "none",
        "date": "none",
        "tags": "none",
        "title": "none",
    },
}


def _read_bytes(name):
    path = os.path.join(BASELINE_DIR, name)
    with open(path, "rb") as f:
        return f.read()


@pytest.fixture()
def unicode_journal():
    j = Journal("test")
    j.config = JOURNAL_CONFIG
    j.entries = [
        Entry(
            j,
            date=datetime.datetime(2023, 3, 15, 10, 0),
            text="今日心情很好！😀😅🎉 完成了重要任务 @done @happy",
            starred=False,
        ),
        Entry(
            j,
            date=datetime.datetime(2023, 4, 20, 14, 30),
            text=(
                "Python 代码示例。\n\n"
                "```python\n"
                "def hello():\n"
                "    print('Hello, World!')\n"
                "    return True\n"
                "```\n"
                "\n"
                "以上是示例代码。\n"
                "代码结束。 @code @python"
            ),
            starred=True,
        ),
        Entry(
            j,
            date=datetime.datetime(2023, 5, 10, 9, 15),
            text=(
                "中文日记记录。\n"
                "日本語の日記です。\n"
                "한국어 일기입니다.\n"
                "混合字符：测试にほんご한국어\n"
                "宽字符测试：表情符号 🌟✨🌈 @i18n @unicode"
            ),
            starred=False,
        ),
    ]
    return j


class TestUnicodePrettyExporterRegression:
    """Pretty 格式：确定性格式，逐字节比对基准文件 + 注册入口一致性。"""

    def test_export_journal_byte_exact_baseline(self, unicode_journal):
        expected_bytes = _read_bytes("unicode_pretty_journal.txt")
        actual_bytes = PrettyExporter.export_journal(unicode_journal).encode("utf-8")
        assert actual_bytes == expected_bytes

    def test_export_journal_via_registry_byte_exact(self, unicode_journal):
        direct_bytes = PrettyExporter.export_journal(unicode_journal).encode("utf-8")
        via_registry_bytes = (
            get_exporter("pretty").export_journal(unicode_journal).encode("utf-8")
        )
        assert via_registry_bytes == direct_bytes

    def test_export_journal_matches_journal_pprint_bytes(self, unicode_journal):
        exporter_bytes = PrettyExporter.export_journal(unicode_journal).encode("utf-8")
        pprint_bytes = unicode_journal.pprint().encode("utf-8")
        assert exporter_bytes == pprint_bytes

    def test_emoji_and_cjk_bytes_preserved(self, unicode_journal):
        result_bytes = PrettyExporter.export_journal(unicode_journal).encode("utf-8")
        assert b"\xf0\x9f\x98\x80" in result_bytes  # 😀
        assert b"\xf0\x9f\x98\x85" in result_bytes  # 😅
        assert b"\xf0\x9f\x8e\x89" in result_bytes  # 🎉
        assert b"\xf0\x9f\x8c\x9f" in result_bytes  # 🌟
        assert b"\xe2\x9c\xa8" in result_bytes  # ✨
        assert b"\xf0\x9f\x8c\x88" in result_bytes  # 🌈
        assert b"\xe4\xbb\x8a\xe6\x97\xa5" in result_bytes  # 今日
        assert b"\xe6\x97\xa5\xe6\x9c\xac" in result_bytes  # 日本
        assert b"\xed\x95\x9c\xea\xb5\xad" in result_bytes  # 한국


class TestUnicodeFancyExporterRegression:
    """Fancy 格式：确定性格式，逐字节比对基准文件 + 注册入口一致性。"""

    def test_export_journal_byte_exact_baseline(self, unicode_journal):
        expected_bytes = _read_bytes("unicode_fancy_journal.txt")
        actual_bytes = FancyExporter.export_journal(unicode_journal).encode("utf-8")
        assert actual_bytes == expected_bytes

    def test_export_journal_via_registry_byte_exact(self, unicode_journal):
        direct_bytes = FancyExporter.export_journal(unicode_journal).encode("utf-8")
        for name in ("fancy", "boxed"):
            via_registry_bytes = (
                get_exporter(name).export_journal(unicode_journal).encode("utf-8")
            )
            assert via_registry_bytes == direct_bytes

    def test_code_block_bytes_preserved(self, unicode_journal):
        result_bytes = FancyExporter.export_journal(unicode_journal).encode("utf-8")
        assert b"```python" in result_bytes
        assert b"def hello():" in result_bytes
        assert b"print('Hello, World!')" in result_bytes
        assert b"return True" in result_bytes


class TestUnicodeMarkdownExporterRegression:
    """Markdown 格式：确定性格式，逐字节比对基准文件 + 注册入口一致性。"""

    def test_export_journal_byte_exact_baseline(self, unicode_journal):
        expected_bytes = _read_bytes("unicode_markdown_journal.md")
        actual_bytes = MarkdownExporter.export_journal(unicode_journal).encode("utf-8")
        assert actual_bytes == expected_bytes

    def test_export_journal_via_registry_byte_exact(self, unicode_journal):
        direct_bytes = MarkdownExporter.export_journal(unicode_journal).encode("utf-8")
        for name in ("md", "markdown"):
            via_registry_bytes = (
                get_exporter(name).export_journal(unicode_journal).encode("utf-8")
            )
            assert via_registry_bytes == direct_bytes

    def test_markdown_code_block_bytes_preserved(self, unicode_journal):
        result_bytes = MarkdownExporter.export_journal(unicode_journal).encode("utf-8")
        assert b"```python" in result_bytes
        assert b"def hello():" in result_bytes
        assert b"print('Hello, World!')" in result_bytes
        assert b"return True" in result_bytes
        assert b"```" in result_bytes

    def test_cjk_emoji_bytes_preserved(self, unicode_journal):
        result_bytes = MarkdownExporter.export_journal(unicode_journal).encode("utf-8")
        assert b"\xe4\xb8\xad\xe6\x96\x87" in result_bytes  # 中文
        assert b"\xe6\x97\xa5\xe6\x9c\xac\xe8\xaa\x9e" in result_bytes  # 日本語
        assert b"\xed\x95\x9c\xea\xb5\xad\xec\x96\xb4" in result_bytes  # 한국어
        assert b"\xf0\x9f\x98\x80" in result_bytes  # 😀
        assert b"\xf0\x9f\x98\x85" in result_bytes  # 😅
        assert b"\xf0\x9f\x8e\x89" in result_bytes  # 🎉
        assert b"\xf0\x9f\x8c\x9f" in result_bytes  # 🌟
        assert b"\xe2\x9c\xa8" in result_bytes  # ✨
        assert b"\xf0\x9f\x8c\x88" in result_bytes  # 🌈


class TestUnicodeJSONExporterRegression:
    """JSON 格式：tag 排序受 set 非确定性影响，使用结构化比对 + 字节级入口一致性验证。"""

    def test_export_journal_is_valid_json(self, unicode_journal):
        output = JSONExporter.export_journal(unicode_journal)
        json.loads(output)  # must not raise

    def test_export_journal_structure(self, unicode_journal):
        output = JSONExporter.export_journal(unicode_journal)
        parsed = json.loads(output)
        assert "entries" in parsed
        assert "tags" in parsed
        assert len(parsed["entries"]) == 3

        # Verify tag counts
        assert set(parsed["tags"].keys()) == {
            "@done",
            "@happy",
            "@code",
            "@python",
            "@i18n",
            "@unicode",
        }
        assert all(parsed["tags"][t] == 1 for t in parsed["tags"])

    def test_export_journal_entry_emoji_and_cjk(self, unicode_journal):
        output = JSONExporter.export_journal(unicode_journal)
        parsed = json.loads(output)

        entry_emoji = parsed["entries"][0]
        assert "😀😅🎉 完成了重要任务" in entry_emoji["body"]
        assert "今日心情很好！" in entry_emoji["title"]
        assert set(entry_emoji["tags"]) == {"@done", "@happy"}
        assert entry_emoji["starred"] is False

        entry_code = parsed["entries"][1]
        assert "```python" in entry_code["body"]
        assert "def hello():" in entry_code["body"]
        assert "print('Hello, World!')" in entry_code["body"]
        assert "return True" in entry_code["body"]
        assert set(entry_code["tags"]) == {"@code", "@python"}
        assert entry_code["starred"] is True

        entry_wide = parsed["entries"][2]
        assert "中文日记记录。" in entry_wide["title"]
        assert "日本語の日記です。" in entry_wide["body"]
        assert "한국어 일기입니다." in entry_wide["body"]
        assert "混合字符：测试にほんご한국어" in entry_wide["body"]
        assert "🌟✨🌈" in entry_wide["body"]
        assert set(entry_wide["tags"]) == {"@i18n", "@unicode"}

    def test_export_journal_via_registry_byte_exact(self, unicode_journal):
        """注册入口输出与直接调用字节级完全一致。"""
        direct_bytes = JSONExporter.export_journal(unicode_journal).encode("utf-8")
        via_registry_bytes = (
            get_exporter("json").export_journal(unicode_journal).encode("utf-8")
        )
        assert via_registry_bytes == direct_bytes


class TestUnicodeYAMLExporterRegression:
    """YAML 格式：tag 顺序受 set 非确定性影响，使用结构化比对 + 字节级入口一致性验证。"""

    @pytest.mark.parametrize(
        "entry_idx,expected_title,expected_tags,expected_starred",
        [
            (0, "今日心情很好！", {"done", "happy"}, False),
            (1, "Python 代码示例。", {"code", "python"}, True),
            (2, "中文日记记录。", {"i18n", "unicode"}, False),
        ],
    )
    def test_export_entry_structure(
        self, unicode_journal, entry_idx, expected_title, expected_tags, expected_starred
    ):
        output = YAMLExporter.export_entry(unicode_journal.entries[entry_idx])
        assert output.startswith("---\n")
        assert output.endswith("...")
        assert f"title: {expected_title}\n" in output
        assert f"starred: {expected_starred}\n" in output

        tags_line = [l for l in output.split("\n") if l.startswith("tags:")][0]
        tags_value = tags_line.split(":", 1)[1].strip()
        tags = {t.strip() for t in tags_value.split(",")}
        assert tags == expected_tags

    def test_export_entry_emoji_and_cjk_bytes(self, unicode_journal):
        output_bytes = YAMLExporter.export_entry(unicode_journal.entries[0]).encode(
            "utf-8"
        )
        assert b"\xe4\xbb\x8a\xe6\x97\xa5\xe5\xbf\x83\xe6\x83\x85" in output_bytes
        assert b"\xf0\x9f\x98\x80" in output_bytes  # 😀
        assert b"\xf0\x9f\x98\x85" in output_bytes  # 😅
        assert b"\xf0\x9f\x8e\x89" in output_bytes  # 🎉

    def test_export_entry_code_block_bytes(self, unicode_journal):
        output_bytes = YAMLExporter.export_entry(unicode_journal.entries[1]).encode(
            "utf-8"
        )
        assert b"def hello():" in output_bytes
        assert b"print('Hello, World!')" in output_bytes
        assert b"return True" in output_bytes

    def test_export_entry_multilang_bytes(self, unicode_journal):
        output_bytes = YAMLExporter.export_entry(unicode_journal.entries[2]).encode(
            "utf-8"
        )
        assert b"\xe4\xb8\xad\xe6\x96\x87" in output_bytes  # 中文
        assert b"\xe6\x97\xa5\xe6\x9c\xac\xe8\xaa\x9e" in output_bytes  # 日本語
        assert b"\xed\x95\x9c\xea\xb5\xad\xec\x96\xb4" in output_bytes  # 한국어
        assert b"\xf0\x9f\x8c\x9f" in output_bytes  # 🌟

    @pytest.mark.parametrize("entry_idx", [0, 1, 2])
    def test_export_entry_via_registry_byte_exact(self, unicode_journal, entry_idx):
        """注册入口输出与直接调用字节级完全一致。"""
        direct_bytes = YAMLExporter.export_entry(
            unicode_journal.entries[entry_idx]
        ).encode("utf-8")
        via_registry_bytes = get_exporter("yaml").export_entry(
            unicode_journal.entries[entry_idx]
        ).encode("utf-8")
        assert via_registry_bytes == direct_bytes

    @pytest.mark.parametrize("entry_idx", [0, 1, 2])
    def test_export_entry_byte_exact_within_process(self, unicode_journal, entry_idx):
        """同进程内两次调用结果字节级完全一致（tag 顺序在同一进程中稳定）。"""
        call1 = YAMLExporter.export_entry(unicode_journal.entries[entry_idx]).encode(
            "utf-8"
        )
        call2 = YAMLExporter.export_entry(unicode_journal.entries[entry_idx]).encode(
            "utf-8"
        )
        assert call1 == call2


class TestUnicodeXMLExporterRegression:
    """XML 格式：tag 顺序受 set 非确定性影响，使用结构化比对 + 字节级入口一致性验证。"""

    @staticmethod
    def _render_entry_to_xml(entry):
        doc = minidom.Document()
        entry_el = XMLExporter.entry_to_xml(entry, doc)
        # Work around pre-existing bool attribute bug
        if entry_el.hasAttribute("starred"):
            entry_el.setAttribute("starred", str(entry_el.getAttribute("starred")))
        doc.appendChild(entry_el)
        return doc.toprettyxml()

    def test_entry0_structure(self, unicode_journal):
        output = self._render_entry_to_xml(unicode_journal.entries[0])
        assert '<entry date="2023-03-15T10:00:00"' in output
        assert "今日心情很好！" in output
        assert "😀😅🎉 完成了重要任务" in output

        doc = minidom.parseString(output)
        entry_el = doc.getElementsByTagName("entry")[0]
        tag_names = {
            el.getAttribute("name") for el in entry_el.getElementsByTagName("tag")
        }
        assert tag_names == {"@done", "@happy"}

    def test_entry1_code_block_bytes(self, unicode_journal):
        output_bytes = self._render_entry_to_xml(unicode_journal.entries[1]).encode(
            "utf-8"
        )
        assert b"```python" in output_bytes
        assert b"def hello():" in output_bytes
        assert b"print('Hello, World!')" in output_bytes

    def test_entry2_cjk_emoji_bytes(self, unicode_journal):
        output_bytes = self._render_entry_to_xml(unicode_journal.entries[2]).encode(
            "utf-8"
        )
        assert b"\xe4\xb8\xad\xe6\x96\x87" in output_bytes  # 中文
        assert b"\xe6\x97\xa5\xe6\x9c\xac\xe8\xaa\x9e" in output_bytes  # 日本語
        assert b"\xed\x95\x9c\xea\xb5\xad\xec\x96\xb4" in output_bytes  # 한국어
        assert b"\xf0\x9f\x8c\x9f" in output_bytes  # 🌟

    @pytest.mark.parametrize("entry_idx", [0, 1, 2])
    def test_entry_xml_via_registry_byte_exact(self, unicode_journal, entry_idx):
        """注册入口输出与直接调用字节级完全一致。"""

        def _render(exporter_cls):
            doc = minidom.Document()
            entry_el = exporter_cls.entry_to_xml(unicode_journal.entries[entry_idx], doc)
            if entry_el.hasAttribute("starred"):
                entry_el.setAttribute(
                    "starred", str(entry_el.getAttribute("starred"))
                )
            doc.appendChild(entry_el)
            return doc.toprettyxml().encode("utf-8")

        direct_bytes = _render(XMLExporter)
        via_registry_bytes = _render(get_exporter("xml"))
        assert via_registry_bytes == direct_bytes

    @pytest.mark.parametrize("entry_idx", [0, 1, 2])
    def test_entry_xml_byte_exact_within_process(self, unicode_journal, entry_idx):
        """同进程内两次调用结果字节级完全一致。"""
        call1 = self._render_entry_to_xml(unicode_journal.entries[entry_idx]).encode(
            "utf-8"
        )
        call2 = self._render_entry_to_xml(unicode_journal.entries[entry_idx]).encode(
            "utf-8"
        )
        assert call1 == call2
