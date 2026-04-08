# docthu API Reference

## Public symbols

```python
from docthu import parse, Template, variables
from docthu import TemplateParseError, MatchError, CoercionError
```

---

## `parse(template, message, *, flexible=True, stop_on_filled=None)`

One-shot extraction. Tokenises `template` and matches it against `message`.

| Parameter | Type | Description |
|---|---|---|
| `template` | `str` | Template string |
| `message` | `str` | Message to extract from |
| `flexible` | `bool` | When `True` (default), whitespace differences between template and message are ignored |
| `stop_on_filled` | `list[str] \| None` | List of variable names the caller requires. The engine stops matching as soon as all of them can be captured. See [Early exit](#early-exit-stop_on_filled) |

**Returns** `dict` — a (possibly nested) dict of extracted values.

**Raises** `TemplateParseError` if the template syntax is invalid.  
**Raises** `MatchError` if the message doesn't match the template structure.  
**Raises** `CoercionError` if a typed variable can't be converted.

For repeated extraction against the same template, prefer `Template` to avoid re-parsing on every call.

---

## `Template(template, *, flexible=True)`

Compiled extraction template. Parse once, match many times.

### Constructor

| Parameter | Type | Description |
|---|---|---|
| `template` | `str` | Template string |
| `flexible` | `bool` | See `parse()` |

**Raises** `TemplateParseError` on invalid template syntax.

### `Template.match(message, *, stop_on_filled=None)`

Extract variables from `message`.

| Parameter | Type | Description |
|---|---|---|
| `message` | `str` | Message to extract from |
| `stop_on_filled` | `list[str] \| None` | See [Early exit](#early-exit-stop_on_filled) |

**Returns** `dict`.  
**Raises** `MatchError`, `CoercionError`.

### `Template.variables()`

Return the variable schema of this template as a list of dicts. Same output as the standalone `variables()` function.

---

## `variables(template)`

Return the variables declared in `template` as a list of JSON-serialisable dicts, without running an extraction. Useful for generating UI schemas or validating template coverage.

**Returns** `list[dict]`, in document order. Each dict contains:

| Field | Values | Description |
|---|---|---|
| `name` | dotted path string | Variable name as declared in the template |
| `type` | `str`, `int`, `float`, `date`, `datetime` | Coercion type |
| `kind` | `extract` \| `static_assign` | `extract` for `{{ var }}` tokens; `static_assign` for `{% var = 'value' %}` tokens |
| `value` | string | Present only when `kind == "static_assign"` — the literal value |

```python
from docthu import variables

template = """\
Date: {{ date }}
Amount: {{ amount:float }}
{% sender.bank_name = 'Vietcombank' %}
"""

variables(template)
# [
#   {"name": "date",             "type": "str",   "kind": "extract"},
#   {"name": "amount",           "type": "float", "kind": "extract"},
#   {"name": "sender.bank_name", "type": "str",   "kind": "static_assign", "value": "Vietcombank"},
# ]
```

---

## Template syntax

### Variable placeholders

| Syntax | Meaning |
|---|---|
| `{{ var }}` | Extract value as string |
| `{{ var:int }}` | Extract and coerce to `int` |
| `{{ var:float }}` | Extract and coerce to `float` |
| `{{ var:date }}` | Extract and coerce to `datetime.date` |
| `{{ var:datetime }}` | Extract and coerce to `datetime.datetime` |
| `{{ a.b.c }}` | Nested output: `{"a": {"b": {"c": value}}}` |

### Static assignments

```
{% var = 'literal' %}
{% var:int = 42 %}
{% var:float = 3.14 %}
```

Hard-code a field without extracting it. Supports single-quoted strings, int literals, float literals, and `true`/`false`. The field appears in the result dict at the declared name (dotted paths work here too).

### Constraints

Two variable placeholders cannot be adjacent — there must be at least one literal character between them. Violating this raises `TemplateParseError`.

---

## Type coercion

| Type | Behaviour |
|---|---|
| `str` | Identity — returned as-is |
| `int` | Strips thousand separators (`,` and `.`), converts to `int` |
| `float` | Auto-detects locale: `1.327,45` → `1327.45`, `1,327.45` → `1327.45` |
| `date` | Tries `dd/mm/yyyy`, `yyyy-mm-dd`, `dd-mm-yyyy`, `dd.mm.yyyy`, `mm/dd/yyyy`, `yyyy/mm/dd` |
| `datetime` | Same date formats plus an optional `HH:MM:SS` or `HH:MM` time component |

Dates and datetimes are returned as `datetime.date` / `datetime.datetime` objects (JSON-serialisable via `str()`).

---

## Exceptions

```python
from docthu import TemplateParseError, MatchError, CoercionError
```

| Exception | Raised when |
|---|---|
| `TemplateParseError` | Template syntax is invalid: unknown type annotation, adjacent variables, malformed `{% %}` block |
| `MatchError` | The message doesn't match the template's static structure |
| `CoercionError` | An extracted value can't be converted to its declared type |

`CoercionError` exposes three attributes:

| Attribute | Description |
|---|---|
| `var_name` | Name of the variable that failed coercion |
| `raw_value` | The extracted string that couldn't be converted |
| `target_type` | The declared type string (e.g. `"int"`) |

```python
try:
    result = parse(template, message)
except TemplateParseError as e:
    # Bad template syntax
    print(e)
except MatchError as e:
    # Message doesn't match template
    print(e)
except CoercionError as e:
    print(e.var_name, e.raw_value, e.target_type)
```

---

## Early exit (`stop_on_filled`)

Pass a list of variable names to `stop_on_filled` when you only need a subset of the template's variables. The engine finds the rightmost listed variable in template order, truncates the token list there, and compiles a shorter regex — skipping the rest of the template entirely.

**Semantics:**
- List order is irrelevant; only template position matters.
- All names in the list must exist as variables in the template — raises `ValueError` otherwise.
- All names must be captured after matching — raises `MatchError` otherwise.
- Variables between the start and the cutoff that are not in the list are also captured (they anchor the regex) and appear in the result.
- Static text **after** the stop point is ignored — the engine does not require it to match the message. This means the template can be created from a sample message even when subsequent messages have different values in uncaptured fields (different dates, amounts, bank names, etc.).

**Typical use case — bilingual emails:**

Many bank emails repeat the same data in two languages. The full template would cover both sections, but you only need the first:

```python
from docthu import Template

# Template covers both English and Vietnamese sections
tpl = Template(open("bank_bilingual.txt").read())

# Stop as soon as amount and date are captured — skip the Vietnamese duplicate
result = tpl.match(email_body, stop_on_filled=["amount", "date"])
```

---

## End-to-end example

**Template** (`bank_transfer.txt`):

```
Transaction successful.
Date: {{ date:date }}
From: {{ sender.account_number }} ({{ sender.bank }})
To: {{ receiver.account_number }} - {{ receiver.name }}
Amount: {{ amount:float }} {{ currency }}
Note: {{ narration }}
{% type = 'transfer' %}
```

**Message:**

```
Transaction successful.
Date: 17/03/2026
From: 1234567890 (Vietcombank)
To: 9876543210 - NGUYEN VAN A
Amount: 5,000,000 VND
Note: school fees
```

**Code:**

```python
from docthu import Template

tpl = Template(open("bank_transfer.txt").read())
result = tpl.match(open("email_body.txt").read())
```

**Result:**

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
