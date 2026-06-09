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
from jrnl.template_engine import (
    TemplateEngine,
    TemplateError,
    TemplateInvalidSyntaxError,
    TemplateUnclosedBlockError,
    TemplateUnexpectedCloserError,
    TemplateUnknownFilterError,
    TemplateUnknownVariableError,
)

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
    模板语法详见 TemplateEngine 类和 docs/formats.md 文档。
    """

    names = ["template", "tpl"]
    extension = "txt"

    _engine = TemplateEngine()
    _template_cache: dict[str, str] = {}

    @classmethod
    def _format_template_error(
        cls, err: TemplateError, template_path: str = "<inline>"
    ) -> str:
        """将 TemplateError 格式化为用户友好的错误信息。"""
        from jrnl.output import print_msg

        name = err.template_name or template_path
        line_num = err.line_number
        line_content = err.line_content or "(no content)"

        FOR_OPEN = "{%"
        FOR_CLOSE = "%}"
        TIP_FOR = FOR_OPEN + " for " + FOR_CLOSE
        TIP_ENDFOR = FOR_OPEN + " endfor " + FOR_CLOSE
        TIP_IF = FOR_OPEN + " if " + FOR_CLOSE
        TIP_ENDIF = FOR_OPEN + " endif " + FOR_CLOSE

        if isinstance(err, TemplateUnclosedBlockError):
            expected = FOR_OPEN + " " + err.expected_closer + " " + FOR_CLOSE
            msg = (
                "\n⚠️  模板语法错误: 未关闭的 '{btype}' 块\n"
                "   模板文件: {name}\n"
                "   第 {ln} 行: {lc}\n"
                "   缺少对应的 '{exp}' 标签\n"
                "\n   提示: 每个 '{tip_for}' 需要匹配 '{tip_endfor}',\n"
                "         每个 '{tip_if}' 需要匹配 '{tip_endif}'。"
            ).format(
                btype=err.block_type,
                name=name,
                ln=line_num,
                lc=line_content,
                exp=expected,
                tip_for=TIP_FOR,
                tip_endfor=TIP_ENDFOR,
                tip_if=TIP_IF,
                tip_endif=TIP_ENDIF,
            )
        elif isinstance(err, TemplateUnexpectedCloserError):
            closer = FOR_OPEN + " " + err.closer + " " + FOR_CLOSE
            msg = (
                "\n⚠️  模板语法错误: 多余的结束标签 '{cls}'\n"
                "   模板文件: {name}\n"
                "   第 {ln} 行: {lc}\n"
                "\n   提示: 确保 '{cls}' 有对应的\n"
                "         '{tip_for}' 或 '{tip_if}' 在前。"
            ).format(
                cls=closer,
                name=name,
                ln=line_num,
                lc=line_content,
                tip_for=TIP_FOR,
                tip_if=TIP_IF,
            )
        elif isinstance(err, TemplateUnknownFilterError):
            available = ", ".join(sorted(err.available_filters))
            msg = (
                "\n⚠️  模板语法错误: 未知的过滤器 '{fname}'\n"
                "   模板文件: {name}\n"
                "   第 {ln} 行: {lc}\n"
                "\n   可用过滤器: {avail}\n"
                "\n   请查阅 docs/formats.md 了解完整的过滤器列表。"
            ).format(
                fname=err.filter_name,
                name=name,
                ln=line_num,
                lc=line_content,
                avail=available,
            )
        elif isinstance(err, TemplateUnknownVariableError):
            available = ", ".join(sorted(err.available_vars))
            msg = (
                "\n⚠️  模板语法错误: 无法解析表达式 '{expr}'\n"
                "   模板文件: {name}\n"
                "   第 {ln} 行: {lc}\n"
                "\n   可用的顶层变量: {avail}\n"
                "\n   提示: 如果访问嵌套属性，请确认父变量存在\n"
                "         且属性名称正确（区分大小写）。"
            ).format(
                expr=err.expression,
                name=name,
                ln=line_num,
                lc=line_content,
                avail=available,
            )
        elif isinstance(err, TemplateInvalidSyntaxError):
            msg = (
                "\n⚠️  模板语法错误: {reason}\n"
                "   模板文件: {name}\n"
                "   第 {ln} 行: {lc}\n"
                "   问题标签: {tag}"
            ).format(
                reason=err.reason,
                name=name,
                ln=line_num,
                lc=line_content,
                tag=err.tag_content,
            )
        else:
            msg = (
                "\n⚠️  模板渲染错误: {msg}\n"
                "   模板文件: {name}\n"
                "   第 {ln} 行: {lc}"
            ).format(
                msg=err.message,
                name=name,
                ln=line_num,
                lc=line_content,
            )
            if err.hint:
                msg += f"\n   提示: {err.hint}"

        return msg

    @classmethod
    def _get_template(
        cls, journal: "Journal", template_path: str | None = None
    ) -> tuple[str, str]:
        """获取模板内容和模板名称。

        返回: (template_content, template_name)
        """
        config_template = (
            journal.config.get("export_template")
            if hasattr(journal, "config")
            else None
        )
        effective_path = template_path or config_template

        if not effective_path:
            return DEFAULT_TEMPLATE, "(built-in default)"

        if effective_path in cls._template_cache:
            return cls._template_cache[effective_path], effective_path

        try:
            template_content = read_template_file(effective_path)
            cls._template_cache[effective_path] = template_content
            return template_content, effective_path
        except JrnlException as e:
            from jrnl.output import print_msg

            logging.warning(
                f"无法读取模板文件 {effective_path}，使用默认模板"
            )
            print_msg(
                Message(
                    MsgText.CantReadTemplate,
                    MsgStyle.WARNING,
                    {"template_path": effective_path},
                )
            )
            return DEFAULT_TEMPLATE, "(built-in default - fallback)"

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
        try:
            metadata, _ = cls._engine.parse(template)
            if metadata and "extension" in metadata:
                cls.extension = metadata["extension"]
        except TemplateError:
            pass

    @classmethod
    def _safe_render(
        cls,
        template: str,
        context: dict[str, Any],
        template_name: str,
    ) -> str:
        """安全地渲染模板，捕获并格式化错误。"""
        try:
            return cls._engine.render(template, context, template_name)
        except TemplateError as e:
            from jrnl.output import print_msg

            error_msg = cls._format_template_error(e, template_name)
            print_msg(error_msg, MsgStyle.ERROR)
            raise JrnlException(f"Template rendering failed: {e.message}") from e

    @classmethod
    def export_entry(
        cls,
        entry: "Entry",
        template_path: str | None = None,
    ) -> str:
        """使用模板导出单条目。"""
        journal = entry.journal
        template, template_name = cls._get_template(journal, template_path)
        cls._apply_template_extension(template)

        context = {
            "entry": cls._build_entry_context(entry),
            "entries": [cls._build_entry_context(entry)],
            "journal": {
                "name": journal.name if hasattr(journal, "name") else "",
                "entry_count": 1,
            },
        }
        return cls._safe_render(template, context, template_name)

    @classmethod
    def export_journal(
        cls,
        journal: "Journal",
        template_path: str | None = None,
    ) -> str:
        """使用模板导出整个日记。"""
        template, template_name = cls._get_template(journal, template_path)
        cls._apply_template_extension(template)
        context = cls._build_journal_context(journal)
        return cls._safe_render(template, context, template_name)

    @classmethod
    def export(
        cls,
        journal: "Journal",
        output: str | None = None,
        template_path: str | None = None,
    ) -> str:
        """导出日记，支持单文件或多文件输出。"""
        template, template_name = cls._get_template(journal, template_path)
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
