"""
Tests for docthu.
"""
from __future__ import annotations

from datetime import date

import pytest

from docthu import CoercionError, MatchError, Template, TemplateParseError, parse, variables


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

HSBC_MESSAGE = """\
Kính gởi Quý khách,

Chúng tôi xin thông báo thẻ tín dụng X0000 của Quý khách vừa thực hiện giao dịch với số tiền 588,000 VND tại CONG TY TNHH UNIQLO VN vào ngày 05/11/2024.

Dư nợ hiện tại là 1,000,000 VND và số dư khả dụng là 100,000,000 VND

Nếu Quý khách cần thêm thông tin, vui lòng liên hệ Trung Tâm Dịch Vụ Khách Hàng theo số:

   —  Đối với Khách hàng Cá Nhân: (84 28) 37247247 (miền Nam) hoặc (84 24) 62707707 (miền Bắc)
   —  Chủ Thẻ Tín Dụng Bạch Kim: (84 28) 37247248
   —  Khách hàng Premier: (84 28) 37247666

Trân trọng,

Ngân hàng TNHH một thành viên HSBC (Việt Nam)"""

HSBC_TEMPLATE = """\
{% sender.account_name = 'Nguyen Van A' %}
Kính gởi Quý khách,

Chúng tôi xin thông báo thẻ tín dụng {{ sender.account_number }} của Quý khách vừa thực hiện giao dịch với số tiền {{ amount }} {{ currency }} tại {{ receiver.account_name }} vào ngày {{ date }}.

Dư nợ hiện tại là 1,000,000 VND và số dư khả dụng là 100,000,000 VND

Nếu Quý khách cần thêm thông tin, vui lòng liên hệ Trung Tâm Dịch Vụ Khách Hàng theo số:

   —  Đối với Khách hàng Cá Nhân: (84 28) 37247247 (miền Nam) hoặc (84 24) 62707707 (miền Bắc)
   —  Chủ Thẻ Tín Dụng Bạch Kim: (84 28) 37247248
   —  Khách hàng Premier: (84 28) 37247666

Trân trọng,

Ngân hàng TNHH một thành viên HSBC (Việt Nam)"""


# ---------------------------------------------------------------------------
# 1. Full round-trip — HSBC example
# ---------------------------------------------------------------------------

def test_hsbc_full_roundtrip():
    result = parse(HSBC_TEMPLATE, HSBC_MESSAGE)
    assert result["sender"]["account_number"] == "X0000"
    assert result["sender"]["account_name"] == "Nguyen Van A"
    assert result["receiver"]["account_name"] == "CONG TY TNHH UNIQLO VN"
    assert result["amount"] == "588,000"
    assert result["currency"] == "VND"
    assert result["date"] == "05/11/2024"


# ---------------------------------------------------------------------------
# 2. Static assignment only (no extraction needed)
# ---------------------------------------------------------------------------

def test_static_assignment_only():
    template = "{% bank = 'HSBC' %}\nHello world"
    message = "Hello world"
    result = parse(template, message)
    assert result["bank"] == "HSBC"


# ---------------------------------------------------------------------------
# 3. Typed variables — float and date
# ---------------------------------------------------------------------------

def test_typed_float():
    template = "Amount: {{ total:float }} USD"
    message = "Amount: 1,234.56 USD"
    result = parse(template, message)
    assert result["total"] == pytest.approx(1234.56)


def test_typed_float_vn_thousands():
    template = "Số tiền: {{ amount:float }} VND"
    message = "Số tiền: 588,000 VND"
    result = parse(template, message)
    assert result["amount"] == pytest.approx(588000.0)


def test_typed_date():
    template = "Ngày: {{ txn_date:date }}"
    message = "Ngày: 05/11/2024"
    result = parse(template, message)
    assert result["txn_date"] == date(2024, 11, 5)


def test_typed_date_iso():
    template = "Date: {{ d:date }}"
    message = "Date: 2024-11-05"
    result = parse(template, message)
    assert result["d"] == date(2024, 11, 5)


def test_typed_int():
    template = "Count: {{ n:int }}"
    message = "Count: 42"
    result = parse(template, message)
    assert result["n"] == 42


# ---------------------------------------------------------------------------
# 4. Flexible whitespace matching
# ---------------------------------------------------------------------------

def test_flexible_extra_spaces():
    template = "Hello {{ name }} how are you"
    message = "Hello   World   how are you"
    result = parse(template, message, flexible=True)
    assert result["name"] == "World"


def test_flexible_extra_newlines():
    template = "A {{ x }} B"
    message = "A\n  foo\n  B"
    result = parse(template, message, flexible=True)
    assert result["x"] == "foo"


# ---------------------------------------------------------------------------
# 5. Nested dotted keys
# ---------------------------------------------------------------------------

def test_nested_three_levels():
    template = "Ref: {{ a.b.c }}"
    message = "Ref: XYZ"
    result = parse(template, message)
    assert result == {"a": {"b": {"c": "XYZ"}}}


def test_nested_mixed_assignment_and_variable():
    template = "{% org.name = 'HSBC' %}\nCode: {{ org.code }}"
    message = "Code: HK001"
    result = parse(template, message)
    assert result["org"]["name"] == "HSBC"
    assert result["org"]["code"] == "HK001"


# ---------------------------------------------------------------------------
# 6. MatchError when message doesn't fit
# ---------------------------------------------------------------------------

def test_match_error_wrong_static_text():
    template = "Hello {{ name }} goodbye"
    message = "Completely different text"
    with pytest.raises(MatchError):
        parse(template, message)


# ---------------------------------------------------------------------------
# 7. CoercionError when type conversion fails
# ---------------------------------------------------------------------------

def test_coercion_error_int():
    template = "Value: {{ n:int }}"
    message = "Value: not-a-number"
    with pytest.raises(CoercionError) as exc_info:
        parse(template, message)
    assert exc_info.value.var_name == "n"
    assert exc_info.value.target_type == "int"


def test_coercion_error_date():
    template = "Date: {{ d:date }}"
    message = "Date: not-a-date"
    with pytest.raises(CoercionError) as exc_info:
        parse(template, message)
    assert exc_info.value.target_type == "date"


# ---------------------------------------------------------------------------
# 8. Adjacent variables raise TemplateParseError
# ---------------------------------------------------------------------------

def test_adjacent_variables_error():
    template = "{{ a }}{{ b }}"
    with pytest.raises(TemplateParseError, match="Adjacent variables"):
        parse(template, "anything")


# ---------------------------------------------------------------------------
# 9. Template class reuse
# ---------------------------------------------------------------------------

def test_template_class_reuse():
    tpl = Template("Name: {{ name }}, Code: {{ code }}")
    r1 = tpl.match("Name: Alice, Code: 001")
    r2 = tpl.match("Name: Bob, Code: 002")
    assert r1 == {"name": "Alice", "code": "001"}
    assert r2 == {"name": "Bob", "code": "002"}


# ---------------------------------------------------------------------------
# 10. Unknown type raises TemplateParseError
# ---------------------------------------------------------------------------

def test_unknown_type_raises():
    with pytest.raises(TemplateParseError, match="Unknown type"):
        parse("{{ x:uuid }}", "anything")


# ---------------------------------------------------------------------------
# 11. Trailing dot+newline anchor does not overshoot when no whitespace
#     follows the dot in the actual message (issue #1)
# ---------------------------------------------------------------------------

def test_trailing_dot_newline_no_whitespace_after_dot():
    """Variable before '.\n' must not greedily consume HTML content after the dot."""
    template = "vào ngày {{ occurred_at:date }}.\n"
    # Simulates an HTML email where '.<br>' has no whitespace between dot and tag
    message = "vào ngày 22/03/2026.<br> <br> Regards, on 22/03/2026."
    result = parse(template, message, flexible=True)
    assert result["occurred_at"] == date(2026, 3, 22)


# ---------------------------------------------------------------------------
# 12. variables() — export template variable schema
# ---------------------------------------------------------------------------

def test_variables_extract_only():
    tpl = "Date: {{ date }} Amount: {{ amount:float }}"
    result = variables(tpl)
    assert result == [
        {"name": "date", "type": "str", "kind": "extract"},
        {"name": "amount", "type": "float", "kind": "extract"},
    ]


def test_variables_static_assign_only():
    tpl = "{% sender.bank_name = 'Vietcombank' %}\nHello"
    result = variables(tpl)
    assert result == [
        {"name": "sender.bank_name", "type": "str", "kind": "static_assign", "value": "Vietcombank"},
    ]


def test_variables_mixed():
    tpl = "Date: {{ date }}\n{% sender.bank_name = 'Vietcombank' %}\nAmount: {{ amount:float }}"
    result = variables(tpl)
    assert result == [
        {"name": "date", "type": "str", "kind": "extract"},
        {"name": "sender.bank_name", "type": "str", "kind": "static_assign", "value": "Vietcombank"},
        {"name": "amount", "type": "float", "kind": "extract"},
    ]


def test_variables_document_order():
    tpl = "{{ b }} {{ a }}"
    result = variables(tpl)
    assert [v["name"] for v in result] == ["b", "a"]


def test_variables_on_template_class():
    tpl = Template("Date: {{ date }}\n{% sender.bank_name = 'Vietcombank' %}")
    result = tpl.variables()
    assert result == [
        {"name": "date", "type": "str", "kind": "extract"},
        {"name": "sender.bank_name", "type": "str", "kind": "static_assign", "value": "Vietcombank"},
    ]


def test_variables_result_is_json_serialisable():
    import json
    tpl = "{{ date }} {% bank = 'VCB' %}"
    assert json.dumps(variables(tpl))  # must not raise


# ---------------------------------------------------------------------------
# 13. Assignment type annotations
# ---------------------------------------------------------------------------

def test_assignment_type_annotation_float():
    tpl = "{% amount:float = '100.50' %}\nDate: {{ date }}"
    result = variables(tpl)
    assert result[0] == {"name": "amount", "type": "float", "kind": "static_assign", "value": "100.50"}


def test_assignment_type_annotation_int():
    tpl = "{% count:int = '42' %}\nHello"
    result = variables(tpl)
    assert result[0] == {"name": "count", "type": "int", "kind": "static_assign", "value": "42"}


def test_assignment_type_annotation_coerced_in_match():
    tpl = "{% amount:float = '100.50' %}\nHello"
    result = parse(tpl, "Hello")
    assert result["amount"] == pytest.approx(100.50)


def test_assignment_unknown_type_raises():
    with pytest.raises(TemplateParseError, match="Unknown type"):
        parse("{% x:uuid = 'val' %}", "anything")


# ---------------------------------------------------------------------------
# 14. Non-string literals in assignments
# ---------------------------------------------------------------------------

def test_assignment_int_literal():
    tpl = "{% count = 42 %}\nHello"
    result = parse(tpl, "Hello")
    assert result["count"] == 42


def test_assignment_float_literal():
    tpl = "{% rate = 0.08 %}\nHello"
    result = parse(tpl, "Hello")
    assert result["rate"] == pytest.approx(0.08)


def test_assignment_bool_literal_stored_as_string():
    tpl = "{% flag = true %}\nHello"
    result = parse(tpl, "Hello")
    assert result["flag"] == "true"


def test_assignment_int_literal_type_in_variables():
    tpl = "{% count = 42 %}"
    result = variables(tpl)
    assert result[0] == {"name": "count", "type": "int", "kind": "static_assign", "value": "42"}


def test_assignment_float_literal_type_in_variables():
    tpl = "{% rate = 3.14 %}"
    result = variables(tpl)
    assert result[0] == {"name": "rate", "type": "float", "kind": "static_assign", "value": "3.14"}


# ---------------------------------------------------------------------------
# 15. Invalid assignment syntax raises TemplateParseError
# ---------------------------------------------------------------------------

def test_invalid_block_raises():
    with pytest.raises(TemplateParseError, match="Invalid assignment syntax"):
        parse("{% invalid syntax here %}\nDate: {{ date }}", "Date: 2024-01-01")


def test_block_missing_equals_raises():
    with pytest.raises(TemplateParseError, match="Invalid assignment syntax"):
        parse("{% no_equals 'value' %}\nHello", "Hello")


# ---------------------------------------------------------------------------
# 16. stop_on_filled — early-exit extraction
# ---------------------------------------------------------------------------

def test_stop_on_filled_basic():
    """Stops after capturing the declared variables; rest of template is skipped."""
    template = "A: {{ a }} B: {{ b }} C: {{ c }} D: {{ d }}"
    # Message intentionally breaks after field b — full template would fail
    message = "A: alpha B: beta C: ---GARBAGE---"
    result = parse(template, message, stop_on_filled=["a", "b"])
    assert result["a"] == "alpha"
    assert result["b"] == "beta"
    assert "c" not in result
    assert "d" not in result


def test_stop_on_filled_order_independent():
    """List order doesn't matter — engine always cuts at the rightmost by template position."""
    template = "A: {{ a }} B: {{ b }} C: {{ c }}"
    message = "A: alpha B: beta C: ---GARBAGE---"
    r1 = parse(template, message, stop_on_filled=["b", "a"])
    r2 = parse(template, message, stop_on_filled=["a", "b"])
    assert r1 == r2
    assert r1["a"] == "alpha"
    assert r1["b"] == "beta"


def test_stop_on_filled_all_variables():
    """Declaring all variables is equivalent to a full extraction."""
    template = "Name: {{ name }} Code: {{ code }}"
    message = "Name: Alice Code: 001"
    result_full = parse(template, message)
    result_sof = parse(template, message, stop_on_filled=["name", "code"])
    assert result_full == result_sof


def test_stop_on_filled_unknown_variable_raises():
    """Names not in the template raise ValueError at call time."""
    template = "A: {{ a }} B: {{ b }}"
    message = "A: x B: y"
    with pytest.raises(ValueError, match="not found in template"):
        parse(template, message, stop_on_filled=["nonexistent"])


def test_stop_on_filled_template_class():
    """Template.match() supports stop_on_filled the same way."""
    tpl = Template("A: {{ a }} B: {{ b }} C: {{ c }}")
    message = "A: alpha B: beta C: ---GARBAGE---"
    result = tpl.match(message, stop_on_filled=["a", "b"])
    assert result["a"] == "alpha"
    assert result["b"] == "beta"
    assert "c" not in result


def test_stop_on_filled_trailing_static_differs():
    """Static text after the stop point may differ from the template (issue #11)."""
    template = (
        "<table>\n"
        "<tr><td>ID</td><td>{{receipt_number}}</td></tr>\n"
        "<tr><td>Date</td><td>2026-01-01</td></tr>\n"
        "<tr><td>Amount</td><td>100 USD</td></tr>\n"
        "</table>"
    )
    message = (
        "<table>\n"
        "<tr><td>ID</td><td>ABC-999</td></tr>\n"
        "<tr><td>Date</td><td>2026-04-07</td></tr>\n"
        "<tr><td>Amount</td><td>194,579 VND</td></tr>\n"
        "</table>"
    )
    result = parse(template, message, stop_on_filled=["receipt_number"])
    assert result == {"receipt_number": "ABC-999"}
