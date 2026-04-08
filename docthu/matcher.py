"""
Compile a token list into a regex pattern, match it against a message,
and build the nested output dict.
"""

from __future__ import annotations

import re
from typing import Any

from .coercion import CoercionError, coerce  # noqa: F401 — re-exported for convenience
from .tokenizer import AssignmentToken, LiteralToken, VariableToken

# Public so __init__.py can import it
__all__ = ["MatchError", "compile_tokens", "extract"]


class MatchError(Exception):
    pass


# ---------------------------------------------------------------------------
# Regex compilation
# ---------------------------------------------------------------------------

# In flexible mode, any run of whitespace in a literal becomes \s+
_WS_RUN = re.compile(r"\s+")


def _literal_to_pattern(text: str, flexible: bool, is_tail: bool = False) -> str:
    escaped = re.escape(text)
    if flexible:
        # Replace escaped whitespace sequences with \s+
        escaped = re.sub(r"(?:\\[ \t\r\n])+", r"\\s+", escaped)
        if is_tail:
            # The trailing whitespace of the last suffix literal must be
            # optional: in HTML emails the character immediately after a literal
            # (e.g. a dot) may be a tag like <br> with no preceding whitespace.
            # extract() already appends a space to the message, so \s* still
            # anchors purely-whitespace suffixes correctly.
            escaped = re.sub(r"\\s\+$", r"\\s*", escaped)
    return escaped


def _var_group_name(dotted_name: str) -> str:
    """Convert dotted variable name to a valid regex group name."""
    return dotted_name.replace(".", "__")


def compile_tokens(
    tokens: list[LiteralToken | VariableToken | AssignmentToken],
    flexible: bool = True,
) -> re.Pattern:
    """
    Convert a token list to a compiled regex.

    Variables become named capture groups; literals become escaped text.
    AssignmentTokens are ignored (they don't contribute to the pattern).
    """
    # Collect only the tokens that produce regex output (literals + variables)
    active = [t for t in tokens if not isinstance(t, AssignmentToken)]

    # Index of the last LiteralToken in active (used to mark the tail literal)
    last_literal_idx = max(
        (i for i, t in enumerate(active) if isinstance(t, LiteralToken)),
        default=-1,
    )

    parts: list[str] = []
    for i, token in enumerate(active):
        if isinstance(token, LiteralToken):
            is_tail = i == last_literal_idx
            parts.append(_literal_to_pattern(token.text, flexible, is_tail=is_tail))
        elif isinstance(token, VariableToken):
            group = _var_group_name(token.name)
            # Last active token that is a variable gets greedy match
            is_last_var = not any(isinstance(t, VariableToken) for t in active[i + 1 :])
            # Also check if anything follows after this variable
            has_following_literal = any(
                isinstance(t, LiteralToken) and t.text.strip() for t in active[i + 1 :]
            )
            if is_last_var and not has_following_literal:
                quantifier = r"[\s\S]+"  # greedy, consumes rest
            else:
                quantifier = r"[\s\S]+?"  # non-greedy

            parts.append(f"(?P<{group}>{quantifier})")

    pattern = "".join(parts)
    try:
        return re.compile(pattern, re.DOTALL)
    except re.error as exc:
        raise ValueError(f"Failed to compile template regex: {exc}") from exc


# ---------------------------------------------------------------------------
# Nested dict builder
# ---------------------------------------------------------------------------


def _set_nested(d: dict, dotted_key: str, value: Any) -> None:
    keys = dotted_key.split(".")
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = value


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------


def extract(
    tokens: list[LiteralToken | VariableToken | AssignmentToken],
    message: str,
    *,
    flexible: bool = True,
    stop_on_filled: list[str] | None = None,
) -> dict:
    """
    Match *message* against the compiled token pattern and return a nested dict.

    Raises MatchError if the message doesn't conform to the template structure.
    Raises CoercionError if a typed variable cannot be converted.

    *stop_on_filled* — when given, the engine truncates the token list at the
    rightmost variable in the set (by template order) and only matches up to
    that point.  Every name in *stop_on_filled* must exist as a variable in the
    template; raises ValueError otherwise.  After matching, raises MatchError if
    any declared variable is absent from the result.
    """
    if stop_on_filled:
        req_names = set(stop_on_filled)
        template_var_names = {t.name for t in tokens if isinstance(t, VariableToken)}
        missing = req_names - template_var_names
        if missing:
            raise ValueError(
                f"stop_on_filled variable(s) {sorted(missing)!r} not found in template"
            )
        last_idx = max(
            i for i, t in enumerate(tokens)
            if isinstance(t, VariableToken) and t.name in req_names
        )
        # Include a short anchor after the cutoff so the last required variable
        # gets a non-greedy quantifier instead of consuming the rest of the
        # message.  Use only text up to the first newline so we don't require
        # template-specific varying content (dates, amounts, …) that follows
        # the stop point to be identical in every message.
        anchor = next(
            (t for t in tokens[last_idx + 1:] if isinstance(t, LiteralToken)),
            None,
        )
        tokens = tokens[:last_idx + 1]
        if anchor is not None:
            # Skip leading whitespace so an anchor like "\n\t</td>\n" doesn't
            # reduce to just "\n" (which is useless as a bounding constraint).
            lead_len = len(anchor.text) - len(anchor.text.lstrip())
            newline_pos = anchor.text.find("\n", lead_len)
            anchor_text = (
                anchor.text[: newline_pos + 1] if newline_pos >= 0 else anchor.text
            )
            tokens = [*tokens, LiteralToken(anchor_text)]

    pattern = compile_tokens(tokens, flexible=flexible)

    # Normalise message whitespace in flexible mode before matching
    msg = message.strip()
    if flexible:
        msg = _WS_RUN.sub(" ", msg)
        msg = msg + " "  # ensure trailing \s+ in the pattern can always match

    m = pattern.search(msg)
    if m is None:
        raise MatchError(
            "Message does not match the template. "
            "Check that the template's static text matches the message."
        )

    result: dict = {}

    # Process captured variables
    var_tokens = {
        _var_group_name(t.name): t for t in tokens if isinstance(t, VariableToken)
    }
    for group_name, raw_value in m.groupdict().items():
        token = var_tokens[group_name]
        value = coerce(token.name, raw_value.strip(), token.type)
        _set_nested(result, token.name, value)

    # Process static assignments
    for token in tokens:
        if isinstance(token, AssignmentToken):
            coerced = coerce(token.name, token.value, token.type)
            _set_nested(result, token.name, coerced)

    # Guarantee all stop_on_filled variables are present in the result
    if stop_on_filled:
        for name in stop_on_filled:
            node: Any = result
            try:
                for k in name.split("."):
                    node = node[k]
            except KeyError:
                raise MatchError(
                    f"Required variable '{name}' was not captured from the message."
                )

    return result
