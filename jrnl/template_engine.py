# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import re
from typing import Any

from ruamel.yaml import YAML


class TemplateEngine:
    """轻量级模板引擎，支持变量、循环、条件和过滤器。

    语法示例：
        {{ entry.title }}              - 变量输出
        {{ entry.body[:100] }}         - 切片/索引访问
        {{ entry.date | date:"%Y-%m-%d" }}  - 过滤器
        {% for entry in entries %}     - 循环
        {% if entry.starred %}         - 条件
    """

    VAR_PATTERN = re.compile(r"\{\{\s*(.+?)\s*\}\}")
    BLOCK_START_PATTERN = re.compile(r"\{%\s*(.+?)\s*%\}")
    FRONT_MATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

    def __init__(self):
        self.filters = {
            "date": self._filter_date,
            "length": self._filter_length,
            "lower": self._filter_lower,
            "upper": self._filter_upper,
            "strip": self._filter_strip,
            "truncate": self._filter_truncate,
            "join": self._filter_join,
            "firstline": self._filter_firstline,
        }

    def parse(self, template: str) -> tuple[dict, str]:
        """解析模板，分离 YAML front matter 和模板主体。"""
        metadata = {}
        match = self.FRONT_MATTER_PATTERN.match(template)
        if match:
            yaml_content = match.group(1)
            yaml = YAML(typ="safe")
            metadata = yaml.load(yaml_content) or {}
            template = template[match.end() :]
        return metadata, template

    def render(self, template: str, context: dict[str, Any]) -> str:
        """渲染模板，返回处理后的字符串。"""
        metadata, template_body = self.parse(template)
        if metadata:
            context["_template_metadata"] = metadata
        return self._render_blocks(template_body, context)

    def _render_blocks(self, template: str, context: dict[str, Any]) -> str:
        """处理模板块（for 循环、if 条件）。"""
        tokens = self._tokenize(template)
        result, _ = self._process_tokens(tokens, context)
        return result

    def _tokenize(self, template: str) -> list[tuple[str, str]]:
        """将模板转换为 token 列表。"""
        tokens = []
        pos = 0
        while pos < len(template):
            block_match = self.BLOCK_START_PATTERN.search(template, pos)
            if block_match:
                if block_match.start() > pos:
                    tokens.append(("text", template[pos : block_match.start()]))
                tokens.append(("block", block_match.group(1).strip()))
                pos = block_match.end()
            else:
                tokens.append(("text", template[pos:]))
                break
        return tokens

    def _process_tokens(
        self, tokens: list[tuple[str, str]], context: dict[str, Any]
    ) -> tuple[str, int]:
        """处理 token 列表，支持嵌套的 for/if 块。
        返回 (渲染结果字符串, 下一个要处理的 token 索引)
        """
        output = []
        i = 0
        while i < len(tokens):
            token_type, token_value = tokens[i]

            if token_type == "text":
                output.append(self._render_vars(token_value, context))
                i += 1
            elif token_type == "block":
                if token_value.startswith("for "):
                    block_result, i = self._process_for(tokens, i, context)
                    output.append(block_result)
                elif token_value.startswith("if "):
                    block_result, i = self._process_if(tokens, i, context)
                    output.append(block_result)
                elif token_value in ("endfor", "endif"):
                    return "".join(output), i + 1
                else:
                    i += 1
            else:
                i += 1
        return "".join(output), i

    def _extract_block(
        self, tokens: list[tuple[str, str]], start: int, end_token: str
    ) -> tuple[list[tuple[str, str]], int]:
        """提取嵌套块，返回块内 tokens 和结束位置。"""
        block_tokens = []
        depth = 1
        i = start + 1
        while i < len(tokens) and depth > 0:
            token_type, token_value = tokens[i]
            if token_type == "block":
                if token_value.startswith("for ") or token_value.startswith("if "):
                    depth += 1
                elif token_value == end_token:
                    depth -= 1
                    if depth == 0:
                        return block_tokens, i + 1
            block_tokens.append(tokens[i])
            i += 1
        return block_tokens, i

    def _process_for(
        self,
        tokens: list[tuple[str, str]],
        start: int,
        context: dict[str, Any],
    ) -> tuple[str, int]:
        """处理 for 循环。"""
        for_stmt = tokens[start][1]
        match = re.match(r"for\s+(\w+)\s+in\s+(.+)", for_stmt)
        if not match:
            return "", start + 1

        var_name = match.group(1)
        iterable_expr = match.group(2).strip()

        try:
            iterable = self._resolve_expression(iterable_expr, context)
        except Exception:
            iterable = []

        block_tokens, next_i = self._extract_block(tokens, start, "endfor")

        results = []
        if hasattr(iterable, "__iter__"):
            for idx, item in enumerate(iterable):
                loop_context = context.copy()
                loop_context[var_name] = item
                loop_context["loop"] = {
                    "index": idx + 1,
                    "index0": idx,
                    "first": idx == 0,
                    "last": idx == len(list(iterable)) - 1
                    if hasattr(iterable, "__len__")
                    else False,
                }
                result, _ = self._process_tokens(block_tokens, loop_context)
                results.append(result)
        return "".join(results), next_i

    def _process_if(
        self,
        tokens: list[tuple[str, str]],
        start: int,
        context: dict[str, Any],
    ) -> tuple[str, int]:
        """处理 if 条件。"""
        if_stmt = tokens[start][1]
        condition = if_stmt[3:].strip()

        # 处理 not 前缀
        negate = False
        if condition.startswith("not "):
            negate = True
            condition = condition[4:].strip()

        try:
            condition_result = bool(self._resolve_expression(condition, context))
            if negate:
                condition_result = not condition_result
        except Exception:
            condition_result = False if not negate else True

        block_tokens, next_i = self._extract_block(tokens, start, "endif")
        true_tokens = []
        else_tokens = []
        current = true_tokens
        has_else = False

        for token in block_tokens:
            token_type, token_value = token
            if token_type == "block" and token_value == "else":
                has_else = True
                current = else_tokens
                continue
            current.append(token)

        active_tokens = true_tokens if condition_result else else_tokens
        result, _ = self._process_tokens(active_tokens, context)
        return result, next_i

    def _render_vars(self, text: str, context: dict[str, Any]) -> str:
        """处理变量输出 {{ ... }}。"""

        def replace_var(match):
            expression = match.group(1).strip()
            try:
                value = self._resolve_with_filters(expression, context)
                return str(value) if value is not None else ""
            except Exception:
                return ""

        return self.VAR_PATTERN.sub(replace_var, text)

    def _resolve_with_filters(self, expression: str, context: dict[str, Any]) -> Any:
        """解析带过滤器的表达式。"""
        parts = [p.strip() for p in expression.split("|")]
        value = self._resolve_expression(parts[0], context)
        for filter_part in parts[1:]:
            filter_name, _, filter_args = filter_part.partition(":")
            filter_name = filter_name.strip()
            args = []
            if filter_args:
                args = [self._parse_literal(a.strip()) for a in self._split_args(filter_args)]
            if filter_name in self.filters:
                value = self.filters[filter_name](value, *args)
        return value

    def _split_args(self, args_str: str) -> list[str]:
        """分割逗号分隔的参数，考虑引号。"""
        args = []
        current = ""
        in_quote = False
        quote_char = None
        for char in args_str:
            if char in ('"', "'") and not in_quote:
                in_quote = True
                quote_char = char
                current += char
            elif char == quote_char and in_quote:
                in_quote = False
                quote_char = None
                current += char
            elif char == "," and not in_quote:
                args.append(current.strip())
                current = ""
            else:
                current += char
        if current.strip():
            args.append(current.strip())
        return args

    def _parse_literal(self, s: str) -> Any:
        """解析字面量（字符串、数字、布尔值）。"""
        if (s.startswith('"') and s.endswith('"')) or (
            s.startswith("'") and s.endswith("'")
        ):
            return s[1:-1]
        if s == "True":
            return True
        if s == "False":
            return False
        if s == "None":
            return None
        try:
            return int(s)
        except ValueError:
            pass
        try:
            return float(s)
        except ValueError:
            pass
        return s

    def _resolve_expression(self, expr: str, context: dict[str, Any]) -> Any:
        """解析属性访问、切片、索引等表达式。"""
        expr = expr.strip()
        if not expr:
            return ""

        # 处理切片/索引语法: name[start:end] 或 name[index]
        slice_match = re.match(r"^(\w+(?:\.\w+)*)\s*\[(.+)\]$", expr)
        if slice_match:
            base_expr = slice_match.group(1)
            slice_expr = slice_match.group(2)
            base = self._resolve_simple(base_expr, context)
            return self._apply_slice(base, slice_expr)

        return self._resolve_simple(expr, context)

    def _resolve_simple(self, expr: str, context: dict[str, Any]) -> Any:
        """解析简单的变量和属性访问。"""
        parts = expr.split(".")
        value = context.get(parts[0])
        for part in parts[1:]:
            if value is None:
                return None
            if isinstance(value, dict):
                value = value.get(part)
            else:
                value = getattr(value, part, None)
        return value

    def _apply_slice(self, obj: Any, slice_str: str) -> Any:
        """应用切片或索引。"""
        try:
            if ":" in slice_str:
                parts = slice_str.split(":")
                start = int(parts[0]) if parts[0] else None
                stop = int(parts[1]) if len(parts) > 1 and parts[1] else None
                step = int(parts[2]) if len(parts) > 2 and parts[2] else None
                return obj[start:stop:step] if step is not None else obj[start:stop]
            else:
                return obj[int(slice_str)]
        except Exception:
            return obj

    def _filter_date(self, value: Any, fmt: str = "%Y-%m-%d %H:%M") -> str:
        """日期格式化过滤器。"""
        if hasattr(value, "strftime"):
            return value.strftime(fmt)
        return str(value) if value else ""

    def _filter_length(self, value: Any) -> int:
        """长度过滤器。"""
        if value is None:
            return 0
        return len(value) if hasattr(value, "__len__") else len(str(value))

    def _filter_lower(self, value: Any) -> str:
        """转小写过滤器。"""
        return str(value).lower() if value else ""

    def _filter_upper(self, value: Any) -> str:
        """转大写过滤器。"""
        return str(value).upper() if value else ""

    def _filter_strip(self, value: Any) -> str:
        """去除首尾空白过滤器。"""
        return str(value).strip() if value else ""

    def _filter_truncate(self, value: Any, length: int = 100, suffix: str = "...") -> str:
        """截断文本过滤器。"""
        text = str(value) if value else ""
        if len(text) <= length:
            return text
        return text[:length] + suffix

    def _filter_join(self, value: Any, separator: str = ", ") -> str:
        """列表连接过滤器。"""
        if value is None:
            return ""
        if hasattr(value, "__iter__") and not isinstance(value, str):
            return separator.join(str(item) for item in value)
        return str(value)

    def _filter_firstline(self, value: Any) -> str:
        """获取第一行过滤器。"""
        text = str(value) if value else ""
        lines = text.splitlines()
        return lines[0] if lines else ""
