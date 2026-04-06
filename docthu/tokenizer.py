"""
Lexer: parses a template string into a flat list of tokens.

Token types:
  LiteralToken    — static text fragment
  VariableToken   — {{ name }} or {{ name:type }}
  AssignmentToken — {% name = 'value' %} or {% name:type = value %}
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Supported coercion type names
VALID_TYPES = {"str", "int", "float", "date", "datetime"}

# Matches {% name = value %} or {% name:type = value %}
# Value may be: single-quoted string, float literal, int literal, or bool literal
_RE_ASSIGN = re.compile(
    r"\{%\s*([\w.]+)(?::(\w+))?\s*=\s*"
    r"(?:'([^']*)'|(-?\d+\.\d+)|(-?\d+)|(true|false))"
    r"\s*%\}"
)
# Matches {{ name }} or {{ name:type }}
_RE_VAR = re.compile(r"\{{\s*([\w.]+)(?::(\w+))?\s*\}\}")
# Combined scanner — assignment first so it takes priority
_RE_TOKEN = re.compile(
    r"(\{%\s*[\w.]+(?::\w+)?\s*=\s*(?:'[^']*'|-?\d+\.\d+|-?\d+|true|false)\s*%\})"
    r"|(\{{\s*[\w.]+(?::\w+)?\s*\}\})"
)
# Detects any {% ... %} block (used to catch invalid/unsupported syntax)
_RE_BLOCK_ATTEMPT = re.compile(r"\{%.*?%\}")


@dataclass
class LiteralToken:
    text: str


@dataclass
class VariableToken:
    name: str  # dotted path, e.g. "sender.account_number"
    type: str = "str"  # coercion type


@dataclass
class AssignmentToken:
    name: str   # dotted path
    value: str  # raw string representation of the value
    type: str = field(default="str")  # coercion type


class TemplateParseError(Exception):
    pass


def tokenize(template: str) -> list[LiteralToken | VariableToken | AssignmentToken]:
    """
    Parse *template* into an ordered list of tokens.

    Assignment blocks that occupy an entire line (possibly with surrounding
    whitespace) are consumed together with their newline so they don't leave
    a blank-line artifact in the adjacent LiteralTokens.
    """
    tokens: list[LiteralToken | VariableToken | AssignmentToken] = []
    pos = 0
    length = len(template)

    while pos < length:
        m = _RE_TOKEN.search(template, pos)
        if m is None:
            # Rest is literal
            tail = template[pos:]
            if tail:
                tokens.append(LiteralToken(tail))
            break

        # Literal text before the match
        before = template[pos : m.start()]

        if m.group(1):
            # AssignmentToken — strip its line from the surrounding literals
            am = _RE_ASSIGN.fullmatch(m.group(1).strip())
            name = am.group(1)
            explicit_type = am.group(2)   # type annotation, may be None
            str_val = am.group(3)         # single-quoted string
            float_val = am.group(4)       # unquoted float literal
            int_val = am.group(5)         # unquoted int literal
            bool_val = am.group(6)        # true/false literal

            if str_val is not None:
                value, inferred_type = str_val, "str"
            elif float_val is not None:
                value, inferred_type = float_val, "float"
            elif int_val is not None:
                value, inferred_type = int_val, "int"
            else:
                value, inferred_type = bool_val, "str"  # store bool as string

            if explicit_type is not None:
                if explicit_type not in VALID_TYPES:
                    raise TemplateParseError(
                        f"Unknown type '{explicit_type}' in assignment '{{{{% {name}:{explicit_type} = ... %}}}}'. "
                        f"Valid types: {sorted(VALID_TYPES)}"
                    )
                type_ = explicit_type
            else:
                type_ = inferred_type

            # If the assignment sits alone on its line, absorb the newline
            # so we don't produce an empty line in the compiled regex.
            before_stripped, after_stripped = _absorb_assignment_line(
                template, pos, m.start(), m.end()
            )
            if before_stripped is not None:
                if before_stripped:
                    tokens.append(LiteralToken(before_stripped))
                tokens.append(AssignmentToken(name=name, value=value, type=type_))
                pos = m.end() + after_stripped
                continue

            if before:
                tokens.append(LiteralToken(before))
            tokens.append(AssignmentToken(name=name, value=value, type=type_))

        elif m.group(2):
            # VariableToken
            vm = _RE_VAR.fullmatch(m.group(2).strip())
            name = vm.group(1)
            type_ = vm.group(2) or "str"
            if type_ not in VALID_TYPES:
                raise TemplateParseError(
                    f"Unknown type '{type_}' in variable '{{{{{name}:{type_}}}}}'. "
                    f"Valid types: {sorted(VALID_TYPES)}"
                )
            if before:
                tokens.append(LiteralToken(before))
            tokens.append(VariableToken(name=name, type=type_))

        pos = m.end()

    # Detect {% ... %} blocks that didn't match the assignment pattern
    for bm in _RE_BLOCK_ATTEMPT.finditer(template):
        block = bm.group(0)
        if not _RE_ASSIGN.fullmatch(block.strip()):
            raise TemplateParseError(
                f"Invalid assignment syntax: {block!r}. "
                "Expected: {{% name = 'value' %}} or {{% name:type = value %}}"
            )

    # Validate: no two VariableTokens are adjacent (no literal between them)
    for i in range(len(tokens) - 1):
        if isinstance(tokens[i], VariableToken) and isinstance(
            tokens[i + 1], VariableToken
        ):
            raise TemplateParseError(
                f"Adjacent variables '{{{{ {tokens[i].name} }}}}' and "
                f"'{{{{ {tokens[i + 1].name} }}}}' have no separator between them. "
                "Add literal text between them or merge into one variable."
            )

    return tokens


def _absorb_assignment_line(
    template: str, pos: int, start: int, end: int
) -> tuple[str | None, int]:
    """
    If the assignment block sits alone on its line (only whitespace before it
    on that line and the line ends right after it), return:
      (text_from_pos_to_line_start, chars_to_skip_after_end)
    Otherwise return (None, 0).
    """
    # Check what's before `start` back to the previous newline
    line_start = template.rfind("\n", 0, start)
    line_start = 0 if line_start == -1 else line_start + 1
    before_on_line = template[line_start:start]
    if before_on_line.strip():
        return None, 0  # Non-whitespace content before on same line

    # Check what's after `end` up to the next newline
    after_chars = 0
    i = end
    while i < len(template) and template[i] in (" ", "\t"):
        i += 1
    if i < len(template) and template[i] == "\n":
        after_chars = i - end + 1  # consume through the newline

    # Return only the text from the current scan position to the line start
    text_before = template[pos:line_start]
    return text_before, after_chars
