"""
docthu — template-based message extraction engine.

Quick start::

    from docthu import parse, Template

    result = parse(template_str, message_str)

    # Or compile once, reuse:
    tpl = Template(template_str)
    result = tpl.match(message_str)
"""

from __future__ import annotations

from .coercion import CoercionError
from .matcher import MatchError, extract
from .tokenizer import (
    AssignmentToken,
    EndToken,
    ListToken,
    TemplateParseError,
    VariableToken,
    tokenize,
)

__all__ = [
    "Template",
    "parse",
    "variables",
    "TemplateParseError",
    "MatchError",
    "CoercionError",
]


class Template:
    """
    A compiled extraction template.

    Compile once; call :meth:`match` many times.

    Parameters
    ----------
    template:
        Template string using ``{{ var }}`` / ``{{ var:type }}`` /
        ``{% var = 'value' %}`` / ``{% list: name %}`` … ``{% end %}`` syntax.
    flexible:
        When *True* (default), whitespace differences between the template
        and the message are ignored.
    """

    def __init__(self, template: str, *, flexible: bool = True) -> None:
        self._tokens = tokenize(template)
        self._flexible = flexible

    def variables(self) -> list[dict]:
        """
        Return the variables defined in this template as a list of dicts.

        Each dict has the keys:

        - ``name``      — dotted variable name (or list block name)
        - ``type``      — coercion type (``"str"``, ``"int"``, ``"float"``,
          ``"date"``, ``"datetime"``, or ``"list"`` for list blocks)
        - ``kind``  — ``"extract"`` for ``{{ var }}`` tokens,
          ``"static_assign"`` for ``{% var = 'value' %}`` tokens, or
          ``"list"`` for ``{% list: name %}`` blocks
        - ``value`` — present only when ``kind == "static_assign"``
        - ``fields`` — present only when ``kind == "list"``: list of field
          descriptors (each with ``name``, ``type``, ``kind``)

        Items are returned in template (document) order.
        """
        return _variables(self._tokens)

    def match(self, message: str, *, stop_on_filled: list[str] | None = None) -> dict:
        """
        Extract variables from *message* using this template.

        Returns a (possibly nested) dict of extracted values.

        *stop_on_filled* — list of variable names the caller requires.  The
        engine truncates the template at the rightmost listed variable and
        stops matching there, skipping the rest of the template.  Raises
        ``ValueError`` if any name is absent from the template or refers to a
        loop-body variable; raises :class:`MatchError` if a required variable
        is not captured.

        Raises :class:`MatchError` if the message doesn't fit the template.
        Raises :class:`CoercionError` if a typed variable can't be converted.
        """
        return extract(self._tokens, message, flexible=self._flexible, stop_on_filled=stop_on_filled)


def _variables(tokens) -> list[dict]:
    result = []
    current_list: dict | None = None
    for token in tokens:
        if isinstance(token, ListToken):
            current_list = {
                "name": token.name,
                "type": "list",
                "kind": "list",
                "fields": [],
            }
            result.append(current_list)
        elif isinstance(token, EndToken):
            current_list = None
        elif isinstance(token, VariableToken):
            if current_list is not None:
                field_name = token.name[len(current_list["name"]) + 1:]
                current_list["fields"].append(
                    {"name": field_name, "type": token.type, "kind": "extract"}
                )
            else:
                result.append({"name": token.name, "type": token.type, "kind": "extract"})
        elif isinstance(token, AssignmentToken):
            result.append(
                {"name": token.name, "type": token.type, "kind": "static_assign", "value": token.value}
            )
    return result


def variables(template: str) -> list[dict]:
    """
    Return the variables defined in *template* as a list of dicts.

    Convenience wrapper around ``Template.variables()`` for one-shot use.
    """
    return _variables(tokenize(template))


def parse(template: str, message: str, *, flexible: bool = True, stop_on_filled: list[str] | None = None) -> dict:
    """
    One-shot convenience wrapper: tokenize *template* and extract from *message*.

    For repeated use against the same template, prefer :class:`Template` to
    avoid re-parsing the template on every call.

    *stop_on_filled* — see :meth:`Template.match`.
    """
    tokens = tokenize(template)
    return extract(tokens, message, flexible=flexible, stop_on_filled=stop_on_filled)
