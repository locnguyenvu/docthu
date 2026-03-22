# docthu

**docthu** is a template-based structured data extraction library for Python. It lets you describe the format of a message once — using a plain-text or HTML template with embedded variable placeholders — and then automatically extract structured data from any message that follows the same format. No regex maintenance, no hardcoded field selectors, no code changes when templates evolve.

## Demo

[![Watch the demo](https://img.youtube.com/vi/TS8todTxwOk/maxresdefault.jpg)](https://youtu.be/TS8todTxwOk)

Load a real `.eml` file into the app, select spans of text in the rendered email and name them as template variables, then run Test Extraction to see the parsed JSON output live.

**[Try the live demo](https://docthu-deixxjekexnpdbnypqc9jr.streamlit.app/)** — no installation needed.

## Problem

Banks and financial institutions send transactional notification emails in a consistent, recurring format. These emails contain critical structured data — transaction amounts, account numbers, dates, beneficiary names, reference codes — but buried inside prose text or HTML layouts. Automating the extraction of this data today typically requires:

- Writing one-off regex patterns per bank per email type
- Manually mapping HTML XPath/CSS selectors to fields
- Re-writing extractors every time the bank changes their email template

Any of these approaches breaks silently when the source format shifts even slightly, and they don't compose well when you need to handle dozens of banks and email types.

**docthu** solves this with a declarative template approach: annotate a real sample email with variable placeholders, save it as a template file, and the engine handles extraction for all future emails matching that format. When the bank changes their template, you update your template file — not your code.

## How it works

docthu parses a template string into tokens (literals and variable placeholders), compiles them into a regex pattern, and applies the pattern to a target message. Captured values are type-coerced and assembled into a nested Python dict.

```
Template string  →  Tokenizer  →  Token list  →  Regex compiler  →  Pattern
                                                                         ↓
Nested dict  ←  Type coercion  ←  Captured groups  ←  Regex match  ←  Message
```

## Installation

```bash
uv add git+https://github.com/locnguyenvu/docthu.git
```

Or run without installing:

```bash
uvx --from git+https://github.com/locnguyenvu/docthu.git docthu
```

Or for development:

```bash
git clone https://github.com/locnguyenvu/docthu.git
cd docthu
uv sync --dev
```

## Python API

```python
from docthu import parse, Template

# One-shot
result = parse(template_str, message_str)

# Reusable (template compiled once, matched many times)
tpl = Template(template_str)
result = tpl.match(message_str)
```

### Template syntax

| Syntax | Meaning |
|---|---|
| `{{ var }}` | Extract value as string |
| `{{ var:int }}` | Extract and coerce to `int` |
| `{{ var:float }}` | Extract and coerce to `float` |
| `{{ var:date }}` | Extract and coerce to `datetime.date` |
| `{{ var:datetime }}` | Extract and coerce to `datetime.datetime` |
| `{{ a.b.c }}` | Nested output: `{"a": {"b": {"c": value}}}` |
| `{% var = 'literal' %}` | Static assignment — no extraction, direct output |

### Example

Template:

```
Transaction successful.
Date: {{ date:date }}
From: {{ sender.account_number }} ({{ sender.bank }})
To: {{ receiver.account_number }} - {{ receiver.name }}
Amount: {{ amount:float }} {{ currency }}
Note: {{ narration }}
{% type = 'transfer' %}
```

Message:

```
Transaction successful.
Date: 17/03/2026
From: 1234567890 (Vietcombank)
To: 9876543210 - NGUYEN VAN A
Amount: 5,000,000 VND
Note: school fees
```

Result:

```json
{
  "date": "2026-03-17",
  "sender": { "account_number": "1234567890", "bank": "Vietcombank" },
  "receiver": { "account_number": "9876543210", "name": "NGUYEN VAN A" },
  "amount": 5000000.0,
  "currency": "VND",
  "narration": "school fees",
  "type": "transfer"
}
```

### Type coercion

| Type | Behaviour |
|---|---|
| `str` | Identity — returned as-is |
| `int` | Strips thousand separators (`,` and `.`), converts to int |
| `float` | Auto-detects locale: `1.327,45` → `1327.45`, `1,327.45` → `1327.45` |
| `date` | Tries common formats: `dd/mm/yyyy`, `yyyy-mm-dd`, `dd-mm-yyyy`, `dd.mm.yyyy`, etc. |
| `datetime` | Same date formats plus time component |

### Exceptions

```python
from docthu import TemplateParseError, MatchError, CoercionError

try:
    result = parse(template, message)
except TemplateParseError as e:
    # Bad template syntax (unknown type, adjacent variables, etc.)
    ...
except MatchError as e:
    # Message doesn't match the template structure
    ...
except CoercionError as e:
    # Extracted value couldn't be coerced to the declared type
    print(e.var_name, e.raw_value, e.target_type)
```

## Use cases

### Banking transaction notifications

Every bank sends transfer confirmation emails in a fixed format per notification type. A single template file per bank per notification type is all you need:

- Incoming transfer alerts
- Outgoing transfer confirmations
- Card transaction notifications
- Low-balance or overdraft alerts
- Interest credit/debit notices

Supported banks in Vietnam (tested): Vietcombank, VIB, VietinBank, etc., and any bank with consistently formatted notification emails.

### Finance and accounting automation

- Auto-import transactions into accounting software from email receipts
- Extract invoice amounts, due dates, and reference numbers from supplier emails
- Parse e-commerce order confirmation and shipping notification emails
- Feed structured transaction data into cash-flow dashboards

### Structured email pipelines

docthu works best for **structured, recurring** emails where the layout is stable between messages of the same type. It is not designed for general free-form text or emails with highly variable structure.

## Template Builder (Streamlit app)

docthu ships with an interactive template builder UI. Upload a `.eml` file, select text in the rendered email to define variables, then download the resulting template file.

```bash
uv run docthu
```

### Generating a template from an `.eml` file

1. **Upload** the `.eml` file in the sidebar.
2. The email renders in the left panel (HTML or plain text, depending on the email).
3. **Select** any span of text in the preview — an *Add Variable* dialog appears.
4. Enter a **variable name** (e.g. `sender.account_number`) and optionally a **type** (`int`, `float`, `date`, `datetime`).
5. Confirm — the selected text is replaced by the `{{ variable }}` token, highlighted in the preview.
6. Repeat for each field you want to extract.
7. Use **Add static assignment** (right panel) to hard-code fields that don't vary (e.g. `{% bank = 'Vietcombank' %}`).
8. Click **Test Extraction** to verify the extracted JSON matches your expectation.
9. Click **Download template** to save the `.html` or `.txt` template file.

The downloaded template is a self-contained file you can check into version control and pass directly to `docthu.parse()` or `docthu.Template`.

### Tips for clean templates

- **Select the minimal span** — include only the value itself, not surrounding labels. The labels become the literal anchors in the pattern.
- **Avoid HTML entity issues** — if a selection isn't found verbatim, try a shorter span. HTML emails may encode certain characters as entities (`&amp;`, `&nbsp;`) that differ from the rendered text.
- **Use dotted names for nested output** — `sender.account_number` produces `{"sender": {"account_number": ...}}` in the result dict.
- **Test before downloading** — the Test Extraction button runs the template against the original email, confirming the regex compiles and all fields are captured correctly.

## Running tests

```bash
uv run pytest tests/ -v
```

## License

MIT

