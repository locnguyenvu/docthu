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
from .tokenizer import TemplateParseError, tokenize

__all__ = [
    "Template",
    "parse",
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

    def match(self, message: str) -> dict:
        """
        Extract variables from *message* using this template.

        Returns a (possibly nested) dict of extracted values.

        Raises :class:`MatchError` if the message doesn't fit the template.
        Raises :class:`CoercionError` if a typed variable can't be converted.
        """
        return extract(self._tokens, message, flexible=self._flexible)


def parse(template: str, message: str, *, flexible: bool = True) -> dict:
    """
    One-shot convenience wrapper: tokenize *template* and extract from *message*.

    For repeated use against the same template, prefer :class:`Template` to
    avoid re-parsing the template on every call.
    """
    tokens = tokenize(template)
    return extract(tokens, message, flexible=flexible)
