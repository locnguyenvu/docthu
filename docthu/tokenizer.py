"""
Lexer: parses a template string into a flat list of tokens.

Token types:
  LiteralToken    — static text fragment
  VariableToken   — {{ name }} or {{ name:type }}
  AssignmentToken — {% name = 'value' %}
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Supported coercion type names
VALID_TYPES = {"str", "int", "float", "date", "datetime"}

# Matches {% name = 'value' %}  (single-quoted value only)
_RE_ASSIGN = re.compile(r"\{%\s*([\w.]+)\s*=\s*'([^']*)'\s*%\}")
# Matches {{ name }} or {{ name:type }}
_RE_VAR = re.compile(r"\{{\s*([\w.]+)(?::(\w+))?\s*\}\}")
# Combined scanner — assignment first so it takes priority
_RE_TOKEN = re.compile(
    r"(\{%\s*[\w.]+\s*=\s*'[^']*'\s*%\})|(\{{\s*[\w.]+(?::\w+)?\s*\}\})"
)


@dataclass
class LiteralToken:
    text: str


@dataclass
class VariableToken:
    name: str  # dotted path, e.g. "sender.account_number"
    type: str = "str"  # coercion type


@dataclass
class AssignmentToken:
    name: str  # dotted path
    value: str  # raw string value


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
            value = am.group(2)

            # If the assignment sits alone on its line, absorb the newline
            # so we don't produce an empty line in the compiled regex.
            before_stripped, after_stripped = _absorb_assignment_line(
                template, pos, m.start(), m.end()
            )
            if before_stripped is not None:
                if before_stripped:
                    tokens.append(LiteralToken(before_stripped))
                tokens.append(AssignmentToken(name=name, value=value))
                pos = m.end() + after_stripped
                continue

            if before:
                tokens.append(LiteralToken(before))
            tokens.append(AssignmentToken(name=name, value=value))

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
