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
from .tokenizer import AssignmentToken, TemplateParseError, VariableToken, tokenize

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
        ``{% var = 'value' %}`` syntax.
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

        - ``name``      — dotted variable name
        - ``type``      — coercion type (``"str"``, ``"int"``, ``"float"``,
          ``"date"``, ``"datetime"``)
        - ``kind``  — ``"extract"`` for ``{{ var }}`` tokens or
          ``"static_assign"`` for ``{% var = 'value' %}`` tokens
        - ``value`` — present only when ``kind == "static_assign"``

        Items are returned in template (document) order.
        """
        return _variables(self._tokens)

    def match(self, message: str) -> dict:
        """
        Extract variables from *message* using this template.

        Returns a (possibly nested) dict of extracted values.

        Raises :class:`MatchError` if the message doesn't fit the template.
        Raises :class:`CoercionError` if a typed variable can't be converted.
        """
        return extract(self._tokens, message, flexible=self._flexible)


def _variables(tokens) -> list[dict]:
    result = []
    for token in tokens:
        if isinstance(token, VariableToken):
            result.append({"name": token.name, "type": token.type, "kind": "extract"})
        elif isinstance(token, AssignmentToken):
            result.append({"name": token.name, "type": "str", "kind": "static_assign", "value": token.value})
    return result


def variables(template: str) -> list[dict]:
    """
    Return the variables defined in *template* as a list of dicts.

    Convenience wrapper around ``Template.variables()`` for one-shot use.
    """
    return _variables(tokenize(template))


def parse(template: str, message: str, *, flexible: bool = True) -> dict:
    """
    One-shot convenience wrapper: tokenize *template* and extract from *message*.

    For repeated use against the same template, prefer :class:`Template` to
    avoid re-parsing the template on every call.
    """
    tokens = tokenize(template)
    return extract(tokens, message, flexible=flexible)
