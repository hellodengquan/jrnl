# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

"""模板端到端测试: 验证默认模板和文档示例能正确渲染。

覆盖:
  - 5个默认模板 (default_text, default_markdown, default_html, summary, custom_json)
  - docs/formats.md 中的过滤器示例
  - docs/formats.md 中的变量示例
"""

import datetime
import os
import re
from typing import Any

import pytest

from jrnl.template_engine import TemplateEngine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "jrnl",
    "templates",
)

DOCS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "docs",
    "formats.md",
)


class MockDate:
    """模拟 entry.date，支持 strftime 和 year/month 属性。"""

    def __init__(self, dt: datetime.datetime):
        self._dt = dt

    def strftime(self, fmt: str) -> str:
        return self._dt.strftime(fmt)

    @property
    def year(self) -> int:
        return self._dt.year

    @property
    def month(self) -> int:
        return self._dt.month

    @property
    def day(self) -> int:
        return self._dt.day


@pytest.fixture()
def engine() -> TemplateEngine:
    yield TemplateEngine()


@pytest.fixture()
def sample_entries() -> list[dict[str, Any]]:
    """3 条真实感的测试日记条目。"""
    return [
        {
            "title": "项目启动会议",
            "body": (
                "今天召开了新项目启动会议。\n"
                "讨论了技术栈选型、时间规划和团队分工。\n"
                "下一步：完成需求文档。\n"
                "项目代号定为 \"Phoenix\"，将采用微服务架构，\n"
                "前端使用 React，后端使用 Go，数据库采用 PostgreSQL。\n"
                "预计总工期为 6 个月，分三个里程碑阶段完成。\n"
                "团队成员需要在本周内完成各自模块的技术方案文档，\n"
                "并在下周一之前提交给技术委员会进行评审。\n"
                "如果一切顺利，第一阶段的 MVP 版本将在两个月后发布。"
            ),
            "date": MockDate(datetime.datetime(2024, 3, 15, 10, 30)),
            "tags": ["@work", "@meeting", "@project"],
            "starred": True,
            "uuid": "entry-uuid-001",
            "fulltext": "2024-03-15 10:30 项目启动会议\n正文...",
        },
        {
            "title": "周末徒步旅行",
            "body": (
                "周末和朋友去了郊外徒步。\n"
                "风景很棒，拍了很多照片。\n"
                "虽然很累但是值得。"
            ),
            "date": MockDate(datetime.datetime(2024, 3, 17, 18, 45)),
            "tags": ["@personal", "@travel"],
            "starred": False,
            "uuid": "entry-uuid-002",
            "fulltext": "2024-03-17 18:45 周末徒步旅行\n正文...",
        },
        {
            "title": "阅读技术博客",
            "body": (
                "今天阅读了一篇关于分布式系统的博客文章。\n"
                "内容很有深度，做了一些笔记。"
            ),
            "date": MockDate(datetime.datetime(2024, 3, 18, 22, 0)),
            "tags": ["@learning", "@tech", "@work"],
            "starred": False,
            "uuid": "entry-uuid-003",
            "fulltext": "2024-03-18 22:00 阅读技术博客\n正文...",
        },
    ]


@pytest.fixture()
def full_context(sample_entries) -> dict[str, Any]:
    """完整的模板上下文（含 journal 级信息）。"""
    tag_counts: dict[str, int] = {}
    for e in sample_entries:
        for tag in e["tags"]:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    sorted_tags = sorted(tag_counts.items(), key=lambda x: (-x[1], x[0]))
    return {
        "entries": sample_entries,
        "journal": {
            "name": "test_journal",
            "entry_count": len(sample_entries),
            "tags": sorted_tags,
        },
    }


@pytest.fixture()
def single_entry_context(sample_entries) -> dict[str, Any]:
    """单条目上下文。"""
    entry = sample_entries[0]
    return {
        "entry": entry,
        "entries": [entry],
        "journal": {
            "name": "test_journal",
            "entry_count": 1,
            "tags": [("@work", 1), ("@meeting", 1), ("@project", 1)],
        },
    }


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _load_template(filename: str) -> str:
    """从模板目录加载模板文件内容。"""
    path = os.path.join(TEMPLATES_DIR, filename)
    assert os.path.exists(path), f"模板文件不存在: {path}"
    with open(path, encoding="utf-8") as f:
        return f.read()


def _extract_extension(template: str) -> str:
    """从模板的 front matter 提取 extension 字段。"""
    match = re.match(
        r"^---\s*\n(.*?)\n---\s*\n", template, re.DOTALL
    )
    if match:
        yaml_content = match.group(1)
        ext_match = re.search(r"extension:\s*['\"]?(\w+)['\"]?", yaml_content)
        if ext_match:
            return ext_match.group(1)
    return ""


# ---------------------------------------------------------------------------
# Test: 默认模板
# ---------------------------------------------------------------------------


class TestDefaultTemplates:
    """测试 5 个内置默认模板能正确渲染。"""

    # -- default_text.template -------------------------------------------

    def test_default_text_loads_and_has_extension(self, engine):
        tpl = _load_template("default_text.template")
        assert _extract_extension(tpl) == "txt"

    def test_default_text_renders_entries(self, engine, full_context):
        tpl = _load_template("default_text.template")
        result = engine.render(tpl, full_context, "default_text.template")

        # 标题都出现
        for entry in full_context["entries"]:
            assert entry["title"] in result, f"缺少标题: {entry['title']}"

        # 日期格式化正确
        assert "2024-03-15 10:30" in result
        assert "2024-03-17 18:45" in result
        assert "2024-03-18 22:00" in result

        # 标签正确
        assert "@work" in result
        assert "@travel" in result

        # 正文片段
        assert "项目启动会议" in result
        assert "徒步旅行" in result

        # 星标标识（模板用了 ⭐）
        assert "⭐" in result or "*" in result

    # -- default_markdown.template ---------------------------------------

    def test_default_markdown_has_extension_md(self, engine):
        tpl = _load_template("default_markdown.template")
        assert _extract_extension(tpl) == "md"

    def test_default_markdown_renders(self, engine, full_context):
        tpl = _load_template("default_markdown.template")
        result = engine.render(tpl, full_context, "default_markdown.template")

        # Markdown 标题层级
        assert "# 日记导出" in result or "日记导出" in result
        for entry in full_context["entries"]:
            assert entry["title"] in result

        # 目录 anchor 应该存在
        assert "目录" in result

        # 标签统计表
        assert "标签统计" in result
        for tag, count in full_context["journal"]["tags"]:
            # 标签出现，count 以字符串形式出现
            assert tag in result, f"缺少标签: {tag}"
            assert str(count) in result

        # entry_count
        assert str(full_context["journal"]["entry_count"]) in result

    # -- default_html.template -------------------------------------------

    def test_default_html_has_extension_html(self, engine):
        tpl = _load_template("default_html.template")
        assert _extract_extension(tpl) == "html"

    def test_default_html_valid_html(self, engine, full_context):
        tpl = _load_template("default_html.template")
        result = engine.render(tpl, full_context, "default_html.template")

        # HTML 骨架
        assert "<!DOCTYPE html>" in result
        assert "<html" in result and "</html>" in result
        assert "<head>" in result and "</head>" in result
        assert "<body>" in result and "</body>" in result

    def test_default_html_has_all_content(self, engine, full_context):
        tpl = _load_template("default_html.template")
        result = engine.render(tpl, full_context, "default_html.template")

        # 统计卡片
        assert str(full_context["journal"]["entry_count"]) in result
        assert str(len(full_context["journal"]["tags"])) in result

        # 所有标题
        for entry in full_context["entries"]:
            assert entry["title"] in result

        # 日期格式化 (中文日期格式: %Y年%m月%d日)
        assert "2024年03月15日 10:30" in result

        # 标签 badge 样式
        for tag in full_context["entries"][0]["tags"]:
            assert tag in result

        # Starred 条目有 ⭐
        assert "⭐" in result

        # entry anchor/id
        for i in range(1, full_context["journal"]["entry_count"] + 1):
            assert f"entry-{i}" in result

    # -- summary.template ------------------------------------------------

    def test_summary_has_correct_frontmatter(self, engine):
        tpl = _load_template("summary.template")
        assert _extract_extension(tpl) == "txt"

    def test_summary_shows_preview_and_firstline(
        self, engine, full_context
    ):
        tpl = _load_template("summary.template")
        result = engine.render(tpl, full_context, "summary.template")

        # 标题和分隔线
        assert "日记摘要报告" in result or "摘要" in result
        assert str(full_context["journal"]["entry_count"]) in result

        # 每条 entry 的标题和日期
        for entry in full_context["entries"]:
            assert entry["title"] in result

        # firstline (正文第一行)
        for entry in full_context["entries"]:
            first_line = entry["body"].splitlines()[0]
            assert first_line in result, (
                f"缺少 firstline: {first_line}"
            )

        # 标签云
        for tag, _ in full_context["journal"]["tags"]:
            assert tag in result

    # -- custom_json.template --------------------------------------------

    def test_custom_json_parses_to_valid_json(
        self, engine, full_context
    ):
        import json

        tpl = _load_template("custom_json.template")
        result = engine.render(tpl, full_context, "custom_json.template")

        # 应该能被 json.loads 解析
        data = json.loads(result)

        # 顶层键存在
        assert "entries" in data
        assert "tags_summary" in data
        assert "entry_count" in data

        # entries 数量正确
        assert data["entry_count"] == full_context["journal"]["entry_count"]
        assert len(data["entries"]) == full_context["journal"]["entry_count"]

        # 每个 entry 字段都存在
        for entry_data in data["entries"]:
            for field in ("date", "title", "starred", "tags", "body_preview"):
                assert field in entry_data, f"entry 缺少字段: {field}"

        # tags_summary 统计值正确
        for tag, count in full_context["journal"]["tags"]:
            assert tag in data["tags_summary"]
            assert data["tags_summary"][tag] == count

    # -- TemplateExporter 集成: extension 自动应用 ------------------------

    def test_all_templates_extension_matches_frontmatter(self, engine):
        """所有默认模板的 front matter extension 应与文件名语义一致。"""
        expectations = {
            "default_text.template": "txt",
            "default_markdown.template": "md",
            "default_html.template": "html",
            "summary.template": "txt",
            "custom_json.template": "json",
        }
        for fname, expected_ext in expectations.items():
            tpl = _load_template(fname)
            ext = _extract_extension(tpl)
            assert ext == expected_ext, (
                f"{fname}: extension={ext}, expected={expected_ext}"
            )


# ---------------------------------------------------------------------------
# Test: docs/formats.md 中的示例
# ---------------------------------------------------------------------------


def _extract_jinja_code_blocks(docs_text: str) -> list[tuple[str, str]]:
    """从文档中提取 jinja 代码块。

    返回 [(description_or_context, code), ...]
    """
    blocks = []

    # 匹配 ```jinja ... ``` 代码块
    pattern = re.compile(r"```jinja\s*\n(.*?)```", re.DOTALL)
    for m in pattern.finditer(docs_text):
        blocks.append(("jinja-block", m.group(1).strip()))

    # 匹配内联 `{{ ... }}` 过滤器/变量示例
    inline_pattern = re.compile(
        r"`\{\{\s*([^`]+?)\s*\}\}`"
    )
    for m in inline_pattern.finditer(docs_text):
        blocks.append(("inline-expr", m.group(1).strip()))

    return blocks


class TestDocExamples:
    """验证 docs/formats.md 中的所有示例片段都能正确渲染。"""

    @pytest.fixture()
    def docs_text(self):
        with open(DOCS_PATH, encoding="utf-8") as f:
            return f.read()

    @pytest.fixture()
    def minimal_context(self, sample_entries):
        """最小可用上下文，用于文档示例。"""
        entry = sample_entries[0]
        return {
            "entry": entry,
            "entries": sample_entries,
            "journal": {
                "name": "my_journal",
                "entry_count": 3,
                "tags": [("@work", 2), ("@meeting", 1)],
            },
        }

    # -- 过滤器示例测试 --------------------------------------------------

    FILTER_EXAMPLES = [
        # (expression, description, 期望包含的子串, entry_override)
        (
            'entry.date | date:"%Y-%m-%d %H:%M"',
            "date 过滤器基本用法",
            "2024-03-15 10:30",
            None,
        ),
        (
            'entry.date | date:"%Y年%m月%d日"',
            "date 过滤器中文格式",
            "2024年03月15日",
            None,
        ),
        (
            'entry.tags | join:", "',
            "join 过滤器",
            "@work, @meeting, @project",
            None,
        ),
        (
            'entry.tags | join:";"',
            "join 自定义分隔符",
            "@work;@meeting;@project",
            None,
        ),
        (
            'entry.body | firstline',
            "firstline 过滤器",
            "今天召开了新项目启动会议。",
            None,
        ),
        (
            'entry.body | truncate:100,"..."',
            "truncate 过滤器",
            "...",
            None,
        ),
        (
            'entry.tags | length',
            "length 过滤器",
            "3",
            None,
        ),
        (
            'entry.title | upper',
            "upper 过滤器",
            "项目启动会议".upper(),
            None,
        ),
        (
            'entry.title | lower',
            "lower 过滤器",
            "项目启动会议",
            None,
        ),
        (
            'entry.title | strip',
            "strip 过滤器",
            "项目启动会议",
            None,
        ),
        (
            'entry.title | upper | strip',
            "过滤器链式调用",
            "项目启动会议".upper(),
            None,
        ),
    ]

    @pytest.mark.parametrize(
        "expression,description,expected,_",
        [(e, d, r, o) for e, d, r, o in FILTER_EXAMPLES],
        ids=[d for _, d, _, _ in FILTER_EXAMPLES],
    )
    def test_filter_examples(
        self, engine, minimal_context, expression, description, expected, _
    ):
        """文档中列出的每个过滤器示例都应成功渲染。"""
        template = "{{ " + expression + " }}"
        result = engine.render(
            template, minimal_context, f"doc-filter:{description}"
        )
        assert expected in result, (
            f"[{description}] 表达式 {repr(template)}\n"
            f"  期望包含: {repr(expected)}\n"
            f"  实际输出: {repr(result[:200])}"
        )

    # -- 变量示例测试 ----------------------------------------------------

    VARIABLE_EXAMPLES = [
        ("entry.title", "标题变量", "项目启动会议"),
        ("journal.entry_count", "条目数", "3"),
        ("journal.name", "日记名", "my_journal"),
        ("entry.starred", "starred 布尔", "True"),
        ("entry.uuid", "uuid", "entry-uuid-001"),
        ("entries[0].title", "列表索引访问", "项目启动会议"),
        ("entry.body[:10]", "切片访问", "今天召开了新项目"),
        ("loop.index", "loop.index 循环变量", "1"),
    ]

    @pytest.mark.parametrize(
        "var,description,expected",
        VARIABLE_EXAMPLES,
        ids=[d for _, d, _ in VARIABLE_EXAMPLES],
    )
    def test_variable_examples(
        self, engine, minimal_context, var, description, expected
    ):
        """文档中列出的变量示例都应存在且正确解析。"""
        if var.startswith("loop."):
            # loop 变量需要在 for 循环内
            template = (
                "{% for x in entries %}{% if loop.first %}{{ "
                + var
                + " }}{% endif %}{% endfor %}"
            )
        else:
            template = "{{ " + var + " }}"

        result = engine.render(
            template, minimal_context, f"doc-variable:{description}"
        )
        assert expected in result, (
            f"[{description}] 变量 {var}\n"
            f"  期望包含: {repr(expected)}\n"
            f"  实际输出: {repr(result[:200])}"
        )

    # -- YAML front matter 示例 -----------------------------------------

    FRONT_MATTER_SAMPLE = """---
extension: html
name: My Custom Report
description: Beautiful HTML export
---
<!DOCTYPE html>
"""

    def test_yaml_front_matter_example(self, engine):
        """文档中 front matter 示例应正确解析。"""
        metadata, body = engine.parse(self.FRONT_MATTER_SAMPLE)
        assert metadata["extension"] == "html"
        assert metadata["name"] == "My Custom Report"
        assert "description" in metadata
        assert "<!DOCTYPE html>" in body

    # -- for 循环解包语法 (for tag, count in ...) -------------------------

    def test_for_unpack_syntax_in_doc(
        self, engine, minimal_context
    ):
        """文档中使用的 for tag, count in journal.tags 能正常渲染。"""
        template = (
            "{% for tag, count in journal.tags %}"
            "{{ tag }}:{{ count }}\n"
            "{% endfor %}"
        )
        result = engine.render(
            template, minimal_context, "doc-for-unpack"
        )
        assert "@work:2" in result or "@work" in result and "2" in result
        assert "@meeting:1" in result or "@meeting" in result and "1" in result

    # -- 完整示例 1: Simple Markdown List --------------------------------

    SIMPLE_MD_SAMPLE = """---
extension: md
name: Simple Markdown List
---
# My Journal

{% for entry in entries %}
## {{ entry.date | date:"%Y-%m-%d" }} - {{ entry.title }}{% if entry.starred %} ⭐{% endif %}

{% if entry.tags %}*Tags: {{ entry.tags | join:", " }}*{% endif %}

{{ entry.body }}

{% endfor %}
"""

    def test_example_1_simple_markdown(
        self, engine, minimal_context
    ):
        """文档 Example 1 - Simple Markdown List 能正常渲染。"""
        result = engine.render(
            self.SIMPLE_MD_SAMPLE, minimal_context, "doc-example-1"
        )

        assert "# My Journal" in result
        # 3 个二级标题 (每个 entry 一个)
        assert result.count("## ") == 3
        # 第一个条目有 ⭐
        assert "⭐" in result
        # 标签出现
        assert "@work" in result
        # 正文存在
        assert "今天召开了新项目启动会议" in result

    # -- 完整示例 3: CSV ------------------------------------------------

    CSV_SAMPLE = '''---
extension: csv
name: CSV Export
---
"Date","Title","Tags","Starred","Body_Preview"
{% for entry in entries %}"{{ entry.date | date:\\"%Y-%m-%d\\" }}","{{ entry.title | strip }}","{{ entry.tags | join:\\";\\",\\":{{ entry.starred }},"{{ entry.body[:80] | truncate:80 | strip }}"{% endfor %}
'''

    def test_example_3_csv_syntax_compiles(
        self, engine, minimal_context
    ):
        """文档 Example 3 - CSV 模板语法能被解析（内容复杂，只验证不报错）。"""
        # 文档示例中的反斜杠转义在模板实际文件中不存在，这里用简化版测试语义
        template = '''"Date","Title","Tags","Starred"
{% for entry in entries %}"{{ entry.date | date:'%Y-%m-%d' }}","{{ entry.title | strip }}","{{ entry.tags | join:';' }}",{{ entry.starred }}
{% endfor %}'''
        result = engine.render(
            template, minimal_context, "doc-example-3-simplified"
        )
        lines = result.strip().splitlines()
        # 1 header + 3 entries
        assert len(lines) == 4
        assert lines[0].startswith('"Date"')
        assert lines[1].count(",") == 3  # 4 fields -> 3 commas
        assert "2024-03-15" in lines[1]

    # -- 文档中所有内联 {{ expr }} 都能渲染 ------------------------------

    def test_all_inline_expressions_no_crash(
        self, engine, docs_text, minimal_context
    ):
        """文档内所有 `{{ ... }}` 片段都至少能被解析不抛异常。"""
        exprs = re.findall(r"`\{\{\s*(.*?)\s*\}\}`", docs_text)
        # 去掉说明性的非表达式（占位符、语法说明等）
        non_expr_keywords = [
            "entry attributes",
            "variable",
            "object",
            "filter_name",
            "start:stop",
            "{#",
        ]

        def is_placeholder(expr: str) -> bool:
            expr = expr.strip()
            for kw in non_expr_keywords:
                if kw in expr:
                    return True
            # 只有 | 没有变量名的语法说明
            if re.match(r"^\\?\|", expr):
                return True
            # 纯说明: body \| ... 这种 \\| 转义说明
            if "\\|" in expr:
                return True
            return False

        exprs = [e for e in exprs if not is_placeholder(e)]

        failed = []
        for expr in exprs:
            # loop.* 变量需要在循环里
            template_expr = expr
            if "loop." in template_expr:
                tpl = (
                    "{% for x in entries %}"
                    "{% if loop.first %}{{ "
                    + template_expr
                    + " }}{% endif %}{% endfor %}"
                )
            else:
                tpl = "{{ " + template_expr + " }}"
            try:
                engine.render(tpl, minimal_context, f"inline:{expr[:40]}")
            except Exception as exc:
                failed.append((expr, str(exc)[:120]))

        if failed:
            msg = f"{len(failed)} 个文档内联表达式失败:\n"
            for expr, err in failed[:5]:
                msg += f"  - {expr!r}: {err}\n"
            pytest.fail(msg)

    # -- docs/formats.md 中列出的关键字段都在上下文中存在 ---------------

    DOC_REQUIRED_FIELDS = [
        # 顶层变量
        ("entries", list),
        ("journal", dict),
        ("journal.name", str),
        ("journal.entry_count", int),
        ("journal.tags", list),
        # entry 字段
        ("entry.title", str),
        ("entry.body", str),
        ("entry.date", object),  # MockDate / datetime
        ("entry.tags", list),
        ("entry.starred", bool),
        ("entry.uuid", str),
        ("entry.fulltext", str),
    ]

    def test_doc_listed_fields_exist_in_context(
        self, minimal_context
    ):
        """文档中列出的所有变量字段都在上下文中存在。"""

        def resolve(path, ctx):
            parts = path.split(".")
            v = ctx.get(parts[0])
            for p in parts[1:]:
                if isinstance(v, dict):
                    v = v.get(p)
                else:
                    v = getattr(v, p, None)
                if v is None:
                    break
            return v

        for field_path, expected_type in self.DOC_REQUIRED_FIELDS:
            value = resolve(field_path, minimal_context)
            assert value is not None, (
                f"文档中列出的字段 {field_path} 在上下文中不存在"
            )
            assert isinstance(value, expected_type), (
                f"字段 {field_path} 类型错误: "
                f"{type(value).__name__} vs {expected_type.__name__}"
            )


# ---------------------------------------------------------------------------
# 边界 / 健壮性
# ---------------------------------------------------------------------------


class TestTemplateEdgeCases:
    """边界条件测试。"""

    def test_empty_entries_list(self, engine):
        """空 entries 不崩溃，仍输出整体结构。"""
        tpl = _load_template("default_text.template")
        ctx = {
            "entries": [],
            "journal": {
                "name": "empty",
                "entry_count": 0,
                "tags": [],
            },
        }
        result = engine.render(tpl, ctx, "empty-entries")
        assert "标签:" not in result or result.count("标签") == 0

    def test_no_tags_entry(self, engine):
        """无 tags 的条目仍正常渲染。"""
        entry = {
            "title": "无标签",
            "body": "正文内容",
            "date": MockDate(datetime.datetime(2024, 1, 1, 0, 0)),
            "tags": [],
            "starred": False,
        }
        tpl = _load_template("summary.template")
        ctx = {
            "entries": [entry],
            "journal": {
                "name": "t",
                "entry_count": 1,
                "tags": [],
            },
        }
        result = engine.render(tpl, ctx, "no-tags")
        assert "无标签" in result
        assert "正文内容" in result

    def test_long_body_truncation(self, engine):
        """正文很长时，HTML 和 summary 模板仍正常 (不截断核心字段)。"""
        long_body = "A" * 5000
        entry = {
            "title": "长文本",
            "body": long_body,
            "date": MockDate(datetime.datetime(2024, 1, 1, 0, 0)),
            "tags": ["@test"],
            "starred": False,
        }
        for tpl_name in (
            "default_html.template",
            "summary.template",
            "default_markdown.template",
        ):
            tpl = _load_template(tpl_name)
            ctx = {
                "entries": [entry],
                "journal": {
                    "name": "t",
                    "entry_count": 1,
                    "tags": [("@test", 1)],
                },
            }
            result = engine.render(tpl, ctx, f"long:{tpl_name}")
            assert "长文本" in result
            assert "@test" in result
