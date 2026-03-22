"""
Streamlit app — load an .eml file and build an extraction template.

The template format matches the email format:
  • HTML email  → template is the HTML source with {{ }} tokens embedded.
    Future emails of the same type are parsed against their HTML source.
  • Plain-text email → template is plain text with {{ }} tokens.

Workflow:
  1. Upload an .eml in the sidebar.
  2. Left column: rendered email preview. Select text → "Add Variable" → modal.
     Defined variables appear as pills above the preview.
  3. Right column: raw template editor + extraction tester + download.
"""

from __future__ import annotations

import html
import re
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser

import streamlit as st

from docthu.components.email_selector import email_selector
from docthu import CoercionError, MatchError, TemplateParseError, parse

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Template Builder",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── .eml parsing ─────────────────────────────────────────────────────────────
class _Stripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self._buf: list[str] = []

    def handle_data(self, data: str) -> None:
        self._buf.append(data)

    def get_text(self) -> str:
        return "".join(self._buf)


def _strip_html(s: str) -> str:
    p = _Stripper()
    p.feed(s)
    return p.get_text()


def extract_parts(raw: bytes) -> tuple[str, str | None]:
    """Return (plain_text, html_source | None)."""
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    plain = html_src = None
    for part in list(msg.walk()) if msg.is_multipart() else [msg]:
        ct = part.get_content_type()
        if ct == "text/plain" and plain is None:
            plain = part.get_content()
        if ct == "text/html" and html_src is None:
            html_src = part.get_content()
    text = (plain or _strip_html(html_src or "")).strip()
    return text, html_src


# ── Template helpers ──────────────────────────────────────────────────────────
_VAR_RE = re.compile(r"\{\{\s*([\w.]+)(?::(\w+))?\s*\}\}")
_ASSIGN_RE = re.compile(r"\{%\s*([\w.]+)\s*=\s*'([^']*)'\s*%\}")


def detected_variables(tmpl: str) -> list[dict]:
    return [
        {"name": m.group(1), "type": m.group(2) or "str"}
        for m in _VAR_RE.finditer(tmpl)
    ]


def highlight_template(tmpl: str) -> str:
    """Return HTML-escaped template with {{ }} tokens highlighted."""
    esc = html.escape(tmpl)
    hi = re.sub(
        r"\{\{[^}]*\}\}|\{%[^%]*%\}",
        lambda m: (
            f'<mark style="background:#fef08a;border:1px solid #fde047;border-radius:4px;'
            f'padding:1px 4px;font-family:monospace;font-size:.85em;color:#854d0e">'
            f"{html.escape(m.group(0))}</mark>"
        ),
        esc,
    )
    return f'<pre style="white-space:pre-wrap;font-size:13px;line-height:1.7;margin:0">{hi}</pre>'


def _make_token(name: str, type_: str) -> str:
    return f"{{{{ {name}:{type_} }}}}" if type_ != "str" else f"{{{{ {name} }}}}"


# ── Session state ─────────────────────────────────────────────────────────────
def _init_state(filename: str, plain: str, html_src: str | None, raw: bytes) -> None:
    if st.session_state.get("_file") == filename:
        return
    # "template" is the HTML source for HTML emails, plain text otherwise.
    # "_eml_raw" holds the original .eml bytes used for test-extraction.
    initial = html_src if html_src is not None else plain
    st.session_state["_file"] = filename
    st.session_state["template"] = initial
    st.session_state["_orig"] = initial
    st.session_state["_is_html"] = html_src is not None
    st.session_state["_plain_body"] = plain
    st.session_state["_eml_raw"] = raw
    st.session_state["_var_map"] = {}  # name → original text value


# ── Sidebar ───────────────────────────────────────────────────────────────────
plain_body: str = ""
html_src: str | None = None

with st.sidebar:
    st.title("Template Builder")

    _has_file = "_file" in st.session_state
    with st.expander("Upload .eml file", expanded=not _has_file):
        st.caption("Upload an .eml file to get started.")
        uploaded = st.file_uploader("Choose an .eml file", type=["eml"])

    if uploaded:
        _raw = uploaded.getvalue()
        plain_body, html_src = extract_parts(_raw)
        _init_state(uploaded.name, plain_body, html_src, _raw)

    if "_file" in st.session_state:
        st.divider()
        st.subheader("Email metadata")
        if uploaded:
            _msg = BytesParser(policy=policy.default).parsebytes(uploaded.getvalue())
            st.write(f"**From:** {_msg.get('From', '—')}")
            st.write(f"**Subject:** {_msg.get('Subject', '—')}")
            st.write(f"**Date:** {_msg.get('Date', '—')}")
        st.caption(f"File: `{st.session_state['_file']}`")
        st.caption(
            f"Format: {'HTML' if st.session_state.get('_is_html') else 'Plain text'}"
        )

        st.divider()
        if st.button("Reset template", use_container_width=True):
            st.session_state["template"] = st.session_state["_orig"]
            st.session_state["_var_map"] = {}
            st.rerun()

# ── Guard ─────────────────────────────────────────────────────────────────────
if "template" not in st.session_state:
    st.markdown(
        """
        ## Template Builder

        **How to use:**
        1. Upload an `.eml` file in the sidebar.
        2. **Select** any text in the email preview — an *Add Variable* button appears.
        3. Click it, enter a name (e.g. `sender.account_number`) and optional type, confirm.
        4. The token is highlighted in the preview; defined variables appear above it.
        5. **Test Extraction** to verify the JSON output, then **Download** the template.

        The template format matches the email: HTML emails produce an HTML template,
        plain-text emails produce a plain-text template.
        """
    )
    st.stop()

is_html = st.session_state["_is_html"]
template = st.session_state["template"]

# ── Layout ────────────────────────────────────────────────────────────────────
col_preview, col_editor = st.columns([3, 2], gap="large")

# ── Left column: email preview + variable selection ───────────────────────────
with col_preview:
    st.subheader("Email Preview")

    # Variable pills above preview
    variables = detected_variables(template)
    assignments = [
        {"name": m.group(1), "value": m.group(2)} for m in _ASSIGN_RE.finditer(template)
    ]

    if variables or assignments:
        var_map = st.session_state.get("_var_map", {})

        for v in variables:
            label = (
                f"{{{{ {v['name']}{':' + v['type'] if v['type'] != 'str' else ''} }}}}"
            )
            orig = var_map.get(v["name"])
            col_pill, col_btn = st.columns([9, 1])
            with col_pill:
                st.markdown(
                    f'<span style="display:inline-flex;align-items:center;'
                    f"background:#dbeafe;color:#1d4ed8;border:1px solid #bfdbfe;"
                    f"border-radius:999px;padding:3px 12px;font-size:12px;"
                    f'font-family:ui-monospace,monospace">{html.escape(label)}</span>'
                    + (
                        f'<span style="font-size:11px;color:#94a3b8;margin-left:6px">'
                        f"← {html.escape(orig)}</span>"
                        if orig
                        else ""
                    ),
                    unsafe_allow_html=True,
                )
            with col_btn:
                if st.button(
                    "✕", key=f"rm_{v['name']}", help="Remove and restore original value"
                ):
                    token = _make_token(v["name"], v["type"])
                    restore = st.session_state["_var_map"].pop(v["name"], "")
                    st.session_state["template"] = st.session_state["template"].replace(
                        token, restore, 1
                    )
                    st.rerun()

        for a in assignments:
            col_pill, col_btn = st.columns([9, 1])
            with col_pill:
                st.markdown(
                    f'<span style="display:inline-flex;align-items:center;'
                    f"background:#dcfce7;color:#15803d;border:1px solid #bbf7d0;"
                    f"border-radius:999px;padding:3px 12px;font-size:12px;"
                    f'font-family:ui-monospace,monospace;margin-top:2px">'
                    f"{html.escape(a['name'])} = '{html.escape(a['value'])}'"
                    f"</span>",
                    unsafe_allow_html=True,
                )
            with col_btn:
                if st.button(
                    "✕", key=f"rm_assign_{a['name']}", help="Remove static assignment"
                ):
                    tag = f"{{% {a['name']} = '{a['value']}' %}}\n"
                    st.session_state["template"] = st.session_state["template"].replace(
                        tag, "", 1
                    )
                    st.rerun()

        st.write("")  # spacing before preview

    result = email_selector(
        content=template,
        is_html=is_html,
        height=520,
        key="email_sel",
    )

    # Guard: only process each result once (component value persists across reruns)
    if result and result.get("_id") != st.session_state.get("_last_result_id"):
        st.session_state["_last_result_id"] = result["_id"]

        sel_text = result["text"]
        new_name = result["name"]
        token = _make_token(new_name, result["type"])

        existing_names = {v["name"] for v in variables} | {
            a["name"] for a in assignments
        }
        if new_name in existing_names:
            st.error(
                f'Variable name "{new_name}" is already defined. Choose a different name.'
            )
        elif sel_text in st.session_state["template"]:
            st.session_state["template"] = st.session_state["template"].replace(
                sel_text, token, 1
            )
            st.session_state["_var_map"][new_name] = sel_text
            st.rerun()
        else:
            st.warning(
                f'"{sel_text}" was not found verbatim in the template source. '
                "This can happen when the selected text contains HTML entities. "
                "Try selecting a shorter span."
            )

# ── Right column: template editor + test ──────────────────────────────────────
with col_editor:
    st.subheader("Template Editor")

    if st.button("Test Extraction", type="primary", use_container_width=True):
        eml_plain, eml_html = extract_parts(st.session_state["_eml_raw"])
        source = eml_html if st.session_state["_is_html"] else eml_plain
        try:
            out = parse(st.session_state["template"], source)
            st.success("Extraction successful")
            st.json(out)
        except TemplateParseError as e:
            st.error(f"Template error: {e}")
        except MatchError as e:
            st.error(f"Match error: {e}")
        except CoercionError as e:
            st.error(f"Type error: {e}")

    ext = "html" if is_html else "txt"
    mime = "text/html" if is_html else "text/plain"
    _stem = st.session_state["_file"].removesuffix(".eml")
    st.download_button(
        "Download template",
        data=st.session_state["template"].encode(),
        file_name=f"{_stem}_template.{ext}",
        mime=mime,
        use_container_width=True,
    )

    st.divider()

    # Static assignment helper
    with st.expander("Add static assignment  `{% var = 'value' %}`"):
        asgn_name = st.text_input(
            "Variable name", placeholder="sender.account_name", key="asgn_name"
        )
        asgn_val = st.text_input(
            "Value", placeholder="e.g. Vietcombank", key="asgn_val"
        )
        if st.button("Insert assignment", use_container_width=True):
            if asgn_name and asgn_val:
                existing_names = {v["name"] for v in variables} | {
                    a["name"] for a in assignments
                }
                if asgn_name in existing_names:
                    st.error(f'Variable name "{asgn_name}" is already defined.')
                else:
                    tag = f"{{% {asgn_name} = '{asgn_val}' %}}\n"
                    st.session_state["template"] = tag + st.session_state["template"]
                    st.rerun()
