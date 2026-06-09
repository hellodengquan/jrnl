# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import re
from typing import Any

from ruamel.yaml import YAML


class TemplateError(Exception):
    """模板相关错误的基类。"""

    def __init__(
        self,
        message: str,
        template_name: str = "<template>",
        line_number: int = 0,
        line_content: str = "",
        hint: str = "",
    ):
        super().__init__(message)
        self.message = message
        self.template_name = template_name
        self.line_number = line_number
        self.line_content = line_content
        self.hint = hint


class TemplateUnclosedBlockError(TemplateError):
    """未关闭的块错误（缺少 endfor/endif）。"""

    def __init__(
        self,
        block_type: str,
        expected_closer: str,
        template_name: str = "<template>",
        line_number: int = 0,
        line_content: str = "",
    ):
        message = f"Unclosed '{block_type}' block - expected '{expected_closer}'"
        super().__init__(message, template_name, line_number, line_content)
        self.block_type = block_type
        self.expected_closer = expected_closer


class TemplateUnexpectedCloserError(TemplateError):
    """多余的结束标签错误。"""

    def __init__(
        self,
        closer: str,
        template_name: str = "<template>",
        line_number: int = 0,
        line_content: str = "",
    ):
        message = f"Unexpected '{closer}' - no matching opening block"
        super().__init__(message, template_name, line_number, line_content)
        self.closer = closer


class TemplateUnknownFilterError(TemplateError):
    """未知过滤器错误。"""

    def __init__(
        self,
        filter_name: str,
        available_filters: list[str],
        template_name: str = "<template>",
        line_number: int = 0,
        line_content: str = "",
    ):
        message = f"Unknown filter '{filter_name}'"
        hint = f"Available filters: {', '.join(sorted(available_filters))}"
        super().__init__(message, template_name, line_number, line_content, hint)
        self.filter_name = filter_name
        self.available_filters = available_filters


class TemplateUnknownVariableError(TemplateError):
    """未知变量/属性错误。"""

    def __init__(
        self,
        expression: str,
        available_vars: list[str],
        template_name: str = "<template>",
        line_number: int = 0,
        line_content: str = "",
    ):
        message = f"Cannot resolve expression '{expression}'"
        hint = f"Available top-level variables: {', '.join(sorted(available_vars))}"
        super().__init__(message, template_name, line_number, line_content, hint)
        self.expression = expression
        self.available_vars = available_vars


class TemplateInvalidSyntaxError(TemplateError):
    """语法无效错误。"""

    def __init__(
        self,
        tag_content: str,
        reason: str,
        template_name: str = "<template>",
        line_number: int = 0,
        line_content: str = "",
    ):
        message = f"Invalid syntax '{tag_content}': {reason}"
        super().__init__(message, template_name, line_number, line_content)
        self.tag_content = tag_content
        self.reason = reason


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
    BLOCK_PATTERN = re.compile(r"\{%\s*(.+?)\s*%\}")
    FRONT_MATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

    VALID_BLOCK_STARTS = ("for ", "if ", "endif", "endfor", "else")
    VALID_CLOSERS = {"endfor", "endif"}
    BLOCK_CLOSERS = {"for": "endfor", "if": "endif"}

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
        self.template_name = "<template>"

    def _get_line_number(self, full_template: str, pos: int) -> int:
        """根据字符位置计算行号（从1开始）。"""
        return full_template.count("\n", 0, pos) + 1

    def _get_line_content(
        self, full_template: str, line_number: int
    ) -> str:
        """根据行号获取该行内容（去除首尾空格）。"""
        lines = full_template.splitlines()
        if 0 < line_number <= len(lines):
            return lines[line_number - 1].strip()
        return ""

    def parse(self, template: str) -> tuple[dict, str]:
        """解析模板，分离 YAML front matter 和模板主体。"""
        metadata = {}
        match = self.FRONT_MATTER_PATTERN.match(template)
        if match:
            yaml_content = match.group(1)
            yaml = YAML(typ="safe")
            try:
                metadata = yaml.load(yaml_content) or {}
            except Exception as e:
                line_number = yaml_content.count("\n", 0, getattr(e, "pos", 0)) + 1
                line_content = ""
                lines = yaml_content.splitlines()
                if 0 < line_number <= len(lines):
                    line_content = lines[line_number - 1]
                raise TemplateInvalidSyntaxError(
                    "YAML front matter",
                    f"YAML parse error: {e}",
                    self.template_name,
                    line_number,
                    line_content,
                ) from e
            template = template[match.end():]
        return metadata, template

    def render(
        self,
        template: str,
        context: dict[str, Any],
        template_name: str = "<template>",
    ) -> str:
        """渲染模板，返回处理后的字符串。

        Args:
            template: 模板字符串
            context: 上下文字典
            template_name: 模板名称（用于错误信息）

        Raises:
            TemplateError: 模板语法或渲染错误
        """
        self.template_name = template_name
        try:
            metadata, template_body = self.parse(template)
        except TemplateError as e:
            e.template_name = template_name
            raise

        if metadata:
            context["_template_metadata"] = metadata

        return self._render_blocks(template_body, context, template, template_name)

    def _tokenize(
        self, template: str, full_template: str
    ) -> list[tuple[str, str, int, str]]:
        """将模板转换为 token 列表，附带行号信息。

        Returns:
            list of (token_type, token_value, line_number, line_content)
        """
        tokens = []
        pos = 0
        while pos < len(template):
            block_match = self.BLOCK_PATTERN.search(template, pos)
            if block_match:
                if block_match.start() > pos:
                    text_content = template[pos:block_match.start()]
                    line_num = self._get_line_number(full_template, pos)
                    line_content = self._get_line_content(full_template, line_num)
                    tokens.append(("text", text_content, line_num, line_content))
                tag_content = block_match.group(1).strip()
                line_num = self._get_line_number(
                    full_template, block_match.start()
                )
                line_content = self._get_line_content(full_template, line_num)
                tokens.append(("block", tag_content, line_num, line_content))
                pos = block_match.end()
            else:
                text_content = template[pos:]
                line_num = self._get_line_number(full_template, pos)
                line_content = self._get_line_content(full_template, line_num)
                tokens.append(("text", text_content, line_num, line_content))
                break
        return tokens

    def _validate_block_tag(
        self, tag_content: str, line_num: int, line_content: str
    ) -> None:
        """验证块标签语法是否有效。"""
        # 检查是否是有效的标签开头
        is_valid = False
        for start in self.VALID_BLOCK_STARTS:
            if tag_content == start.rstrip() or tag_content.startswith(start):
                is_valid = True
                break

        if not is_valid:
            raise TemplateInvalidSyntaxError(
                f"{{% {tag_content} %}}",
                "Unknown block tag. Valid tags are: for, if, else, endfor, endif",
                self.template_name,
                line_num,
                line_content,
            )

        # 验证 for 语法 (支持: for var in ..., for a, b in ...)
        if tag_content.startswith("for "):
            for_pattern = re.compile(
                r"for\s+(\w+(?:\s*,\s*\w+)*)\s+in\s+(.+)"
            )
            if not for_pattern.match(tag_content):
                raise TemplateInvalidSyntaxError(
                    f"{{% {tag_content} %}}",
                    "Invalid for loop syntax. Expected: {% for var in iterable %} "
                    "or {% for a, b in iterable %}",
                    self.template_name,
                    line_num,
                    line_content,
                )

        # 验证 if 语法
        if tag_content.startswith("if "):
            condition = tag_content[3:].strip()
            if not condition:
                raise TemplateInvalidSyntaxError(
                    f"{{% {tag_content} %}}",
                    "Empty condition in if statement. Expected: {% if condition %}",
                    self.template_name,
                    line_num,
                    line_content,
                )

    def _validate_blocks(
        self, tokens: list[tuple[str, str, int, str]]
    ) -> None:
        """验证所有块是否正确配对。"""
        stack: list[tuple[str, int, str]] = []  # (block_type, line_num, line_content)

        for token_type, token_value, line_num, line_content in tokens:
            if token_type != "block":
                continue

            self._validate_block_tag(token_value, line_num, line_content)

            if token_value.startswith("for "):
                stack.append(("for", line_num, line_content))
            elif token_value.startswith("if "):
                stack.append(("if", line_num, line_content))
            elif token_value == "endfor":
                if not stack:
                    raise TemplateUnexpectedCloserError(
                        "endfor", self.template_name, line_num, line_content
                    )
                block_type, _, _ = stack[-1]
                if block_type != "for":
                    expected = self.BLOCK_CLOSERS[block_type]
                    actual = "endfor"
                    _, open_line, open_content = stack[-1]
                    raise TemplateInvalidSyntaxError(
                        f"{{% {token_value} %}}",
                        f"Mismatched block: expected '{expected}' to close "
                        f"'{block_type}' block opened at line {open_line}, "
                        f"got '{actual}'",
                        self.template_name,
                        line_num,
                        line_content,
                    )
                stack.pop()
            elif token_value == "endif":
                if not stack:
                    raise TemplateUnexpectedCloserError(
                        "endif", self.template_name, line_num, line_content
                    )
                block_type, _, _ = stack[-1]
                if block_type != "if":
                    expected = self.BLOCK_CLOSERS[block_type]
                    actual = "endif"
                    _, open_line, open_content = stack[-1]
                    raise TemplateInvalidSyntaxError(
                        f"{{% {token_value} %}}",
                        f"Mismatched block: expected '{expected}' to close "
                        f"'{block_type}' block opened at line {open_line}, "
                        f"got '{actual}'",
                        self.template_name,
                        line_num,
                        line_content,
                    )
                stack.pop()

        # 检查是否有未关闭的块
        if stack:
            block_type, line_num, line_content = stack[-1]
            expected_closer = self.BLOCK_CLOSERS[block_type]
            raise TemplateUnclosedBlockError(
                block_type,
                expected_closer,
                self.template_name,
                line_num,
                line_content,
            )

    def _render_blocks(
        self,
        template: str,
        context: dict[str, Any],
        full_template: str,
        template_name: str,
    ) -> str:
        """处理模板块（for 循环、if 条件）。"""
        self.template_name = template_name
        tokens = self._tokenize(template, full_template)
        self._validate_blocks(tokens)
        result, _ = self._process_tokens(tokens, context)
        return result

    def _process_tokens(
        self,
        tokens: list[tuple[str, str, int, str]],
        context: dict[str, Any],
    ) -> tuple[str, int]:
        """处理 token 列表，支持嵌套的 for/if 块。
        返回 (渲染结果字符串, 下一个要处理的 token 索引)
        """
        output = []
        i = 0
        while i < len(tokens):
            token_type, token_value, line_num, line_content = tokens[i]

            if token_type == "text":
                try:
                    rendered = self._render_vars(
                        token_value, context, line_num, line_content
                    )
                    output.append(rendered)
                except TemplateError as e:
                    e.template_name = self.template_name
                    raise
                i += 1
            elif token_type == "block":
                if token_value.startswith("for "):
                    try:
                        block_result, i = self._process_for(tokens, i, context)
                    except TemplateError as e:
                        e.template_name = self.template_name
                        raise
                    output.append(block_result)
                elif token_value.startswith("if "):
                    try:
                        block_result, i = self._process_if(tokens, i, context)
                    except TemplateError as e:
                        e.template_name = self.template_name
                        raise
                    output.append(block_result)
                elif token_value in ("endfor", "endif"):
                    return "".join(output), i + 1
                else:
                    i += 1
            else:
                i += 1
        return "".join(output), i

    def _extract_block(
        self,
        tokens: list[tuple[str, str, int, str]],
        start: int,
        end_token: str,
    ) -> tuple[list[tuple[str, str, int, str]], int]:
        """提取嵌套块，返回块内 tokens 和结束位置。"""
        block_tokens = []
        depth = 1
        i = start + 1
        while i < len(tokens) and depth > 0:
            token_type, token_value, _, _ = tokens[i]
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
        tokens: list[tuple[str, str, int, str]],
        start: int,
        context: dict[str, Any],
    ) -> tuple[str, int]:
        """处理 for 循环。"""
        _, for_stmt, line_num, line_content = tokens[start]
        for_pattern = re.compile(
            r"for\s+(\w+(?:\s*,\s*\w+)*)\s+in\s+(.+)"
        )
        match = for_pattern.match(for_stmt)
        if not match:
            raise TemplateInvalidSyntaxError(
                f"{{% {for_stmt} %}}",
                "Invalid for loop syntax. Expected: {% for var in iterable %} "
                "or {% for a, b in iterable %}",
                self.template_name,
                line_num,
                line_content,
            )

        var_names = [v.strip() for v in match.group(1).split(",")]
        iterable_expr = match.group(2).strip()

        try:
            iterable = self._resolve_expression(
                iterable_expr, context, line_num, line_content
            )
        except TemplateUnknownVariableError as e:
            e.template_name = self.template_name
            raise
        except TemplateError:
            raise
        except Exception:
            iterable = []

        block_tokens, next_i = self._extract_block(tokens, start, "endfor")

        results = []
        if hasattr(iterable, "__iter__"):
            iterable_list = list(iterable)
            for idx, item in enumerate(iterable_list):
                loop_context = context.copy()
                # 支持解包: for a, b in ...
                if len(var_names) > 1:
                    if hasattr(item, "__len__") and len(item) >= len(var_names):
                        for i, vn in enumerate(var_names):
                            loop_context[vn] = item[i]
                    else:
                        # 不匹配时用 None 填充
                        for i, vn in enumerate(var_names):
                            loop_context[vn] = (
                                item[i]
                                if hasattr(item, "__getitem__")
                                and i < len(item)
                                else None
                            )
                else:
                    loop_context[var_names[0]] = item
                loop_context["loop"] = {
                    "index": idx + 1,
                    "index0": idx,
                    "first": idx == 0,
                    "last": idx == len(iterable_list) - 1,
                    "length": len(iterable_list),
                }
                result, _ = self._process_tokens(block_tokens, loop_context)
                results.append(result)
        return "".join(results), next_i

    def _process_if(
        self,
        tokens: list[tuple[str, str, int, str]],
        start: int,
        context: dict[str, Any],
    ) -> tuple[str, int]:
        """处理 if 条件。"""
        _, if_stmt, line_num, line_content = tokens[start]
        condition = if_stmt[3:].strip()

        negate = False
        if condition.startswith("not "):
            negate = True
            condition = condition[4:].strip()

        try:
            condition_result = bool(
                self._resolve_expression(
                    condition, context, line_num, line_content
                )
            )
            if negate:
                condition_result = not condition_result
        except TemplateUnknownVariableError:
            condition_result = False if not negate else True
        except TemplateError:
            raise
        except Exception:
            condition_result = False if not negate else True

        block_tokens, next_i = self._extract_block(tokens, start, "endif")
        true_tokens = []
        else_tokens = []
        current = true_tokens

        for token in block_tokens:
            token_type, token_value, _, _ = token
            if token_type == "block" and token_value == "else":
                current = else_tokens
                continue
            current.append(token)

        active_tokens = true_tokens if condition_result else else_tokens
        result, _ = self._process_tokens(active_tokens, context)
        return result, next_i

    def _render_vars(
        self,
        text: str,
        context: dict[str, Any],
        line_num: int,
        line_content: str,
    ) -> str:
        """处理变量输出 {{ ... }}。"""

        def replace_var(match):
            expression = match.group(1).strip()
            try:
                value = self._resolve_with_filters(
                    expression, context, line_num, line_content
                )
                return str(value) if value is not None else ""
            except TemplateUnknownFilterError as e:
                e.line_number = line_num
                e.line_content = line_content
                e.template_name = self.template_name
                raise
            except TemplateUnknownVariableError as e:
                e.line_number = line_num
                e.line_content = line_content
                e.template_name = self.template_name
                raise
            except TemplateError:
                raise
            except Exception:
                return ""

        return self.VAR_PATTERN.sub(replace_var, text)

    def _resolve_with_filters(
        self,
        expression: str,
        context: dict[str, Any],
        line_num: int,
        line_content: str,
    ) -> Any:
        """解析带过滤器的表达式。"""
        parts = [p.strip() for p in expression.split("|")]
        try:
            value = self._resolve_expression(
                parts[0], context, line_num, line_content
            )
        except TemplateUnknownVariableError:
            raise
        except TemplateError:
            raise
        except Exception:
            value = ""

        for filter_part in parts[1:]:
            filter_name, _, filter_args = filter_part.partition(":")
            filter_name = filter_name.strip()

            if filter_name not in self.filters:
                raise TemplateUnknownFilterError(
                    filter_name,
                    list(self.filters.keys()),
                    self.template_name,
                    line_num,
                    line_content,
                )

            args = []
            if filter_args:
                try:
                    args = [
                        self._parse_literal(a.strip())
                        for a in self._split_args(filter_args)
                    ]
                except Exception as e:
                    raise TemplateInvalidSyntaxError(
                        f"filter {filter_name}",
                        f"Invalid filter arguments: {e}",
                        self.template_name,
                        line_num,
                        line_content,
                    ) from e
            try:
                value = self.filters[filter_name](value, *args)
            except TemplateError:
                raise
            except TypeError as e:
                raise TemplateInvalidSyntaxError(
                    f"filter {filter_name}",
                    f"Wrong number of arguments: {e}",
                    self.template_name,
                    line_num,
                    line_content,
                ) from e
            except Exception as e:
                raise TemplateError(
                    f"Error in filter '{filter_name}': {e}",
                    self.template_name,
                    line_num,
                    line_content,
                ) from e
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

    def _resolve_expression(
        self,
        expr: str,
        context: dict[str, Any],
        line_num: int = 0,
        line_content: str = "",
    ) -> Any:
        """解析属性访问、切片、索引等表达式。"""
        expr = expr.strip()
        if not expr:
            return ""

        # 处理切片/索引语法: name[start:end] 或 name[index]
        slice_match = re.match(r"^(\w+(?:\.\w+)*)\s*\[(.+)\]$", expr)
        if slice_match:
            base_expr = slice_match.group(1)
            slice_expr = slice_match.group(2)
            base = self._resolve_simple(
                base_expr, context, line_num, line_content
            )
            return self._apply_slice(base, slice_expr)

        return self._resolve_simple(expr, context, line_num, line_content)

    def _resolve_simple(
        self,
        expr: str,
        context: dict[str, Any],
        line_num: int = 0,
        line_content: str = "",
    ) -> Any:
        """解析简单的变量和属性访问。"""
        parts = expr.split(".")
        top_level = parts[0]

        if top_level not in context and top_level not in (
            "loop",
            "_template_metadata",
        ):
            available = [k for k in context.keys() if not k.startswith("_")]
            available.extend(["loop", "(entry attributes)"])
            raise TemplateUnknownVariableError(
                expr,
                available,
                self.template_name,
                line_num,
                line_content,
            )

        value = context.get(parts[0])
        for part in parts[1:]:
            if value is None:
                return None
            if isinstance(value, dict):
                if part not in value:
                    # 不抛出错误，只返回 None，保持向后兼容
                    return None
                value = value.get(part)
            else:
                if not hasattr(value, part):
                    return None
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
                if step is not None:
                    return obj[start:stop:step]
                return obj[start:stop]
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

    def _filter_truncate(
        self, value: Any, length: int = 100, suffix: str = "..."
    ) -> str:
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
