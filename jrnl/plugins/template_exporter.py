# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import logging
import os
from typing import TYPE_CHECKING
from typing import Any

from jrnl.editor import read_template_file
from jrnl.exception import JrnlException
from jrnl.messages import Message
from jrnl.messages import MsgStyle
from jrnl.messages import MsgText
from jrnl.plugins.text_exporter import TextExporter
from jrnl.template_engine import TemplateEngine

if TYPE_CHECKING:
    from jrnl.journals import Entry
    from jrnl.journals import Journal


DEFAULT_TEMPLATE = """---
extension: txt
---
{% for entry in entries %}
[{{ entry.date | date:"%Y-%m-%d %H:%M" }}] {{ entry.title }}
{% if entry.starred %} *{% endif %}
{% if entry.tags %}
标签: {{ entry.tags | join:", " }}
{% endif %}
{% if entry.body %}
{{ entry.body }}
{% endif %}

{% endfor %}
"""


class TemplateExporter(TextExporter):
    """使用自定义模板导出日记的导出器。

    支持通过 --export-template 参数或配置文件中的 export_template 指定模板路径。
    模板语法详见 TemplateEngine 类。
    """

    names = ["template", "tpl"]
    extension = "txt"

    _engine = TemplateEngine()
    _template_cache: dict[str, str] = {}

    @classmethod
    def _get_template(cls, journal: "Journal", template_path: str | None = None) -> str:
        """获取模板内容。

        优先级：
        1. 显式传入的 template_path
        2. journal.config 中的 export_template
        3. 默认模板
        """
        config_template = journal.config.get("export_template") if hasattr(journal, "config") else None
        effective_path = template_path or config_template

        if not effective_path:
            return DEFAULT_TEMPLATE

        if effective_path in cls._template_cache:
            return cls._template_cache[effective_path]

        try:
            template_content = read_template_file(effective_path)
            cls._template_cache[effective_path] = template_content
            return template_content
        except JrnlException:
            logging.warning(
                f"无法读取模板文件 {effective_path}，使用默认模板"
            )
            return DEFAULT_TEMPLATE

    @classmethod
    def _build_entry_context(cls, entry: "Entry") -> dict[str, Any]:
        """为单条目构建上下文字典。"""
        return {
            "title": entry.title,
            "body": entry.body,
            "date": entry.date,
            "tags": entry.tags,
            "starred": entry.starred,
            "uuid": getattr(entry, "uuid", None),
            "fulltext": entry.fulltext if hasattr(entry, "fulltext") else "",
        }

    @classmethod
    def _build_journal_context(cls, journal: "Journal") -> dict[str, Any]:
        """为整个日记构建上下文字典。"""
        entries = [cls._build_entry_context(e) for e in journal.entries]
        all_tags: dict[str, int] = {}
        for entry_ctx in entries:
            for tag in entry_ctx["tags"]:
                all_tags[tag] = all_tags.get(tag, 0) + 1

        sorted_tags = sorted(all_tags.items(), key=lambda x: (-x[1], x[0]))

        return {
            "entries": entries,
            "journal": {
                "name": journal.name if hasattr(journal, "name") else "",
                "entry_count": len(entries),
                "tags": sorted_tags,
            },
        }

    @classmethod
    def _apply_template_extension(cls, template: str) -> None:
        """从模板的 front matter 中读取扩展名并应用。"""
        metadata, _ = cls._engine.parse(template)
        if metadata and "extension" in metadata:
            cls.extension = metadata["extension"]

    @classmethod
    def export_entry(
        cls,
        entry: "Entry",
        template_path: str | None = None,
    ) -> str:
        """使用模板导出单条目。"""
        journal = entry.journal
        template = cls._get_template(journal, template_path)
        cls._apply_template_extension(template)

        context = {
            "entry": cls._build_entry_context(entry),
            "entries": [cls._build_entry_context(entry)],
            "journal": {
                "name": journal.name if hasattr(journal, "name") else "",
                "entry_count": 1,
            },
        }
        return cls._engine.render(template, context)

    @classmethod
    def export_journal(
        cls,
        journal: "Journal",
        template_path: str | None = None,
    ) -> str:
        """使用模板导出整个日记。"""
        template = cls._get_template(journal, template_path)
        cls._apply_template_extension(template)
        context = cls._build_journal_context(journal)
        return cls._engine.render(template, context)

    @classmethod
    def export(
        cls,
        journal: "Journal",
        output: str | None = None,
        template_path: str | None = None,
    ) -> str:
        """导出日记，支持单文件或多文件输出。"""
        template = cls._get_template(journal, template_path)
        cls._apply_template_extension(template)

        if output and os.path.isdir(output):
            return cls.write_files(journal, output, template_path)
        elif output:
            return cls.write_file(journal, output, template_path)
        else:
            return cls.export_journal(journal, template_path)

    @classmethod
    def write_file(
        cls,
        journal: "Journal",
        path: str,
        template_path: str | None = None,
    ) -> str:
        """将日记导出到单个文件。"""
        export_str = cls.export_journal(journal, template_path)
        with open(path, "w", encoding="utf-8") as f:
            f.write(export_str)
        from jrnl.output import print_msg

        print_msg(
            Message(
                MsgText.JournalExportedTo,
                MsgStyle.NORMAL,
                {
                    "path": path,
                },
            )
        )
        return ""

    @classmethod
    def write_files(
        cls,
        journal: "Journal",
        path: str,
        template_path: str | None = None,
    ) -> str:
        """将日记导出为多个文件（每个条目一个文件）。"""
        import errno
        import re
        import unicodedata

        for entry in journal.entries:
            entry_is_written = False
            while not entry_is_written:
                full_path = os.path.join(path, cls.make_filename(entry))
                try:
                    with open(full_path, "w", encoding="utf-8") as f:
                        f.write(cls.export_entry(entry, template_path))
                        entry_is_written = True
                except OSError as oserr:
                    title_length = len(str(entry.title))
                    if (
                        oserr.errno == errno.ENAMETOOLONG
                        or oserr.errno == errno.ENOENT
                        or oserr.errno == errno.EINVAL
                    ) and title_length > 1:
                        shorter_file_length = title_length // 2
                        entry.title = str(entry.title)[:shorter_file_length]
                    else:
                        raise

        from jrnl.output import print_msg

        print_msg(
            Message(
                MsgText.JournalExportedTo,
                MsgStyle.NORMAL,
                {"path": path},
            )
        )
        return ""
