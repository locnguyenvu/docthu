"""
Compile a token list into a regex pattern, match it against a message,
and build the nested output dict.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .coercion import CoercionError, coerce  # noqa: F401 — re-exported for convenience
from .tokenizer import AssignmentToken, EndToken, LiteralToken, ListToken, VariableToken

# Public so __init__.py can import it
__all__ = ["MatchError", "compile_tokens", "extract"]


class MatchError(Exception):
    pass


# ---------------------------------------------------------------------------
# Regex compilation
# ---------------------------------------------------------------------------

# In flexible mode, any run of whitespace in a literal becomes \s+
_WS_RUN = re.compile(r"\s+")


def _literal_to_pattern(text: str, flexible: bool, is_tail: bool = False, is_head: bool = False) -> str:
    escaped = re.escape(text)
    if flexible:
        # Replace escaped whitespace sequences with \s+
        escaped = re.sub(r"(?:\\[ \t\r\n])+", r"\\s+", escaped)
        if is_head:
            # Leading whitespace of the first literal must be optional: the
            # content may start directly with the first non-whitespace character
            # (e.g. when a {% %} assignment tag precedes <html> in the template).
            escaped = re.sub(r"^\\s\+", r"\\s*", escaped)
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


# ---------------------------------------------------------------------------
# Compiled template structures
# ---------------------------------------------------------------------------


@dataclass
class LoopSpec:
    name: str                        # collection key and object prefix, e.g. "item"
    blob_group: str                  # regex group name in the main pattern, e.g. "__list_item"
    body_pattern: re.Pattern         # sub-regex applied per-item via finditer
    body_var_tokens: list            # VariableToken list for variables inside the loop body


@dataclass
class CompiledTemplate:
    pattern: re.Pattern
    loop_specs: list                 # list[LoopSpec]
    outer_var_tokens: dict           # group_name → VariableToken (non-loop vars)
    assignment_tokens: list          # list[AssignmentToken]


# ---------------------------------------------------------------------------
# Segmentation helpers
# ---------------------------------------------------------------------------


def _split_loop_blocks(tokens):
    """
    Partition the flat token list into segments:
      ('outer', [tokens])
      ('loop',  ListToken, [body_tokens])
    """
    segments = []
    outer_buf = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if isinstance(token, ListToken):
            if outer_buf:
                segments.append(("outer", outer_buf))
                outer_buf = []
            j = i + 1
            body = []
            while j < len(tokens) and not isinstance(tokens[j], EndToken):
                body.append(tokens[j])
                j += 1
            segments.append(("loop", token, body))
            i = j + 1  # skip EndToken
        elif isinstance(token, EndToken):
            i += 1  # already consumed by ListToken handler; skip stray EndToken
        else:
            outer_buf.append(token)
            i += 1
    if outer_buf:
        segments.append(("outer", outer_buf))
    return segments


def _outer_tokens(tokens):
    """Return only the tokens that live outside any list block."""
    result = []
    in_loop = False
    for t in tokens:
        if isinstance(t, ListToken):
            in_loop = True
        elif isinstance(t, EndToken):
            in_loop = False
        elif not in_loop:
            result.append(t)
    return result


def _loop_var_names(tokens):
    """Return the set of VariableToken names that live inside list blocks."""
    names = set()
    in_loop = False
    for t in tokens:
        if isinstance(t, ListToken):
            in_loop = True
        elif isinstance(t, EndToken):
            in_loop = False
        elif in_loop and isinstance(t, VariableToken):
            names.add(t.name)
    return names


# ---------------------------------------------------------------------------
# Body sub-pattern compilation
# ---------------------------------------------------------------------------


def _compile_body_tokens(body_tokens, list_name: str, flexible: bool) -> re.Pattern:
    """
    Compile the loop-body tokens into a sub-regex for use with finditer.

    Variable names like ``item.name`` have their ``item.`` prefix stripped;
    the group name becomes ``name``.  All variables use non-greedy quantifiers
    when any literal follows them (even whitespace-only), so finditer can
    correctly delimit individual items.
    """
    prefix = list_name + "."
    active = [t for t in body_tokens if not isinstance(t, AssignmentToken)]

    first_literal_idx = next(
        (i for i, t in enumerate(active) if isinstance(t, LiteralToken)), -1
    )
    last_literal_idx = max(
        (i for i, t in enumerate(active) if isinstance(t, LiteralToken)), default=-1
    )

    parts: list[str] = []
    for i, token in enumerate(active):
        if isinstance(token, LiteralToken):
            # No is_head/is_tail treatment for body literals — the body is a
            # repeated unit and doesn't need BOM or HTML-tag workarounds.
            parts.append(_literal_to_pattern(token.text, flexible))
        elif isinstance(token, VariableToken):
            field_name = (
                token.name[len(prefix):]
                if token.name.startswith(prefix)
                else token.name
            )
            group = _var_group_name(field_name)
            is_last_var = not any(isinstance(t, VariableToken) for t in active[i + 1:])
            # For body patterns: ANY following literal (even whitespace-only) is
            # enough to bound the match, so we use non-greedy +? in that case.
            has_following_literal = any(isinstance(t, LiteralToken) for t in active[i + 1:])
            if is_last_var and not has_following_literal:
                quantifier = r"[\s\S]+"
            else:
                quantifier = r"[\s\S]+?"
            parts.append(f"(?P<{group}>{quantifier})")

    pattern_str = "".join(parts)
    try:
        return re.compile(pattern_str, re.DOTALL)
    except re.error as exc:
        raise ValueError(f"Failed to compile loop body regex: {exc}") from exc


# ---------------------------------------------------------------------------
# Main compile_tokens
# ---------------------------------------------------------------------------


def compile_tokens(
    tokens: list,
    flexible: bool = True,
) -> CompiledTemplate:
    """
    Convert a token list to a :class:`CompiledTemplate`.

    For templates without list blocks the result behaves like the former
    ``re.Pattern`` return value (accessible via ``.pattern``).
    """
    segments = _split_loop_blocks(tokens)

    # Build a flat list of "main-pattern elements" for position-aware compilation
    # Each element is one of:
    #   ('literal',  LiteralToken)
    #   ('variable', VariableToken)
    #   ('blob',     ListToken, body_tokens)
    main_elements = []
    for seg in segments:
        if seg[0] == "outer":
            for t in seg[1]:
                if isinstance(t, LiteralToken):
                    main_elements.append(("literal", t))
                elif isinstance(t, VariableToken):
                    main_elements.append(("variable", t))
                # AssignmentToken: skip — contributes no regex pattern
        elif seg[0] == "loop":
            main_elements.append(("blob", seg[1], seg[2]))

    first_lit_idx = next(
        (i for i, e in enumerate(main_elements) if e[0] == "literal"), -1
    )
    last_lit_idx = max(
        (i for i, e in enumerate(main_elements) if e[0] == "literal"), default=-1
    )

    parts: list[str] = []
    outer_var_tokens: dict = {}
    loop_specs: list[LoopSpec] = []
    assignment_tokens: list[AssignmentToken] = [
        t
        for seg in segments
        if seg[0] == "outer"
        for t in seg[1]
        if isinstance(t, AssignmentToken)
    ]

    for i, elem in enumerate(main_elements):
        kind = elem[0]

        if kind == "literal":
            is_head = i == first_lit_idx
            is_tail = i == last_lit_idx
            parts.append(
                _literal_to_pattern(elem[1].text, flexible, is_tail=is_tail, is_head=is_head)
            )

        elif kind == "variable":
            token = elem[1]
            group = _var_group_name(token.name)
            outer_var_tokens[group] = token

            is_last_active = not any(
                e[0] in ("variable", "blob") for e in main_elements[i + 1:]
            )
            has_following_literal = any(
                e[0] == "literal" and e[1].text.strip()
                for e in main_elements[i + 1:]
            )
            if is_last_active and not has_following_literal:
                quantifier = r"[\s\S]+"
            else:
                quantifier = r"[\s\S]+?"
            parts.append(f"(?P<{group}>{quantifier})")

        elif kind == "blob":
            list_token = elem[1]
            body_tokens = elem[2]
            blob_group = f"__list_{list_token.name}"

            is_last_active = not any(
                e[0] in ("variable", "blob") for e in main_elements[i + 1:]
            )
            has_following_literal = any(
                e[0] == "literal" and e[1].text.strip()
                for e in main_elements[i + 1:]
            )
            # Use * (zero-or-more) to allow empty lists
            if is_last_active and not has_following_literal:
                quantifier = r"[\s\S]*"
            else:
                quantifier = r"[\s\S]*?"
            parts.append(f"(?P<{blob_group}>{quantifier})")

            body_pattern = _compile_body_tokens(body_tokens, list_token.name, flexible)
            body_var_tokens = [t for t in body_tokens if isinstance(t, VariableToken)]

            loop_specs.append(
                LoopSpec(
                    name=list_token.name,
                    blob_group=blob_group,
                    body_pattern=body_pattern,
                    body_var_tokens=body_var_tokens,
                )
            )

    pattern_str = "".join(parts)
    try:
        main_pattern = re.compile(pattern_str, re.DOTALL)
    except re.error as exc:
        raise ValueError(f"Failed to compile template regex: {exc}") from exc

    return CompiledTemplate(
        pattern=main_pattern,
        loop_specs=loop_specs,
        outer_var_tokens=outer_var_tokens,
        assignment_tokens=assignment_tokens,
    )


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
    tokens: list,
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
    that point.  Every name in *stop_on_filled* must exist as a non-loop
    variable in the template; raises ValueError otherwise.  After matching,
    raises MatchError if any declared variable is absent from the result.
    Loop-body variables cannot be used in *stop_on_filled*.
    """
    if stop_on_filled:
        req_names = set(stop_on_filled)

        loop_vars = _loop_var_names(tokens)
        loop_stop = req_names & loop_vars
        if loop_stop:
            raise ValueError(
                f"stop_on_filled cannot reference loop-body variables: {sorted(loop_stop)!r}"
            )

        outer = _outer_tokens(tokens)
        template_var_names = {t.name for t in outer if isinstance(t, VariableToken)}
        template_assign_names = {t.name for t in outer if isinstance(t, AssignmentToken)}
        missing = req_names - template_var_names - template_assign_names
        if missing:
            raise ValueError(
                f"stop_on_filled variable(s) {sorted(missing)!r} not found in template"
            )

        extract_req_names = req_names - template_assign_names
        if extract_req_names:
            last_idx = max(
                i for i, t in enumerate(outer)
                if isinstance(t, VariableToken) and t.name in extract_req_names
            )
            anchor = next(
                (t for t in outer[last_idx + 1:] if isinstance(t, LiteralToken)),
                None,
            )
            tokens = outer[:last_idx + 1]
            if anchor is not None:
                lead_len = len(anchor.text) - len(anchor.text.lstrip())
                newline_pos = anchor.text.find("\n", lead_len)
                anchor_text = (
                    anchor.text[: newline_pos + 1] if newline_pos >= 0 else anchor.text
                )
                tokens = [*tokens, LiteralToken(anchor_text)]
        else:
            tokens = outer

    compiled = compile_tokens(tokens, flexible=flexible)

    # Normalise message whitespace in flexible mode before matching
    msg = message.strip()
    if flexible:
        msg = _WS_RUN.sub(" ", msg)
        msg = msg + " "  # ensure trailing \s+ in the pattern can always match

    m = compiled.pattern.search(msg)
    if m is None:
        raise MatchError(
            "Message does not match the template. "
            "Check that the template's static text matches the message."
        )

    result: dict = {}

    # Process outer (non-loop) captured variables
    for group_name, raw_value in m.groupdict().items():
        if group_name.startswith("__list_"):
            continue  # handled in phase 2 below
        token = compiled.outer_var_tokens[group_name]
        value = coerce(token.name, raw_value.strip(), token.type)
        _set_nested(result, token.name, value)

    # Process static assignments
    for token in compiled.assignment_tokens:
        coerced = coerce(token.name, token.value, token.type)
        _set_nested(result, token.name, coerced)

    # Phase 2: apply the body sub-pattern to each loop blob
    prefix_len_cache: dict[str, int] = {}
    for loop_spec in compiled.loop_specs:
        blob = m.group(loop_spec.blob_group) or ""
        prefix = loop_spec.name + "."
        prefix_len = len(prefix)
        items = []
        for item_match in loop_spec.body_pattern.finditer(blob):
            item_dict: dict = {}
            for var_token in loop_spec.body_var_tokens:
                field_name = (
                    var_token.name[prefix_len:]
                    if var_token.name.startswith(prefix)
                    else var_token.name
                )
                group = _var_group_name(field_name)
                raw = item_match.group(group)
                coerced = coerce(var_token.name, raw.strip(), var_token.type)
                _set_nested(item_dict, field_name, coerced)
            items.append(item_dict)
        result[loop_spec.name] = items

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
