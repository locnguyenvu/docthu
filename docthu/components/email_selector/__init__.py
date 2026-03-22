"""
Streamlit custom component — renders email content with interactive
text-selection → variable assignment.

Returns: {"text": str, "name": str, "type": str} when the user confirms
a new variable, else None.
"""

from __future__ import annotations

import os

import streamlit.components.v1 as _components

_COMPONENT_DIR = os.path.dirname(os.path.abspath(__file__))
_email_selector = _components.declare_component("email_selector", path=_COMPONENT_DIR)


def email_selector(
    content: str,
    *,
    is_html: bool = False,
    height: int = 520,
    key: str | None = None,
) -> dict | None:
    """Render *content* with variable-selection UX.

    Parameters
    ----------
    content:
        HTML source or plain text to display (current template state, so
        ``{{ }}`` tokens are already embedded and will be highlighted).
    is_html:
        True → render as HTML.  False → render as pre-wrapped plain text.
    height:
        Iframe height in pixels.
    key:
        Streamlit widget key.
    """
    return _email_selector(
        content=content,
        is_html=is_html,
        height=height,
        key=key,
        default=None,
    )
