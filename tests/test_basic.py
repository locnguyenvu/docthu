"""
Tests for docthu.
"""
from __future__ import annotations

from datetime import date

import pytest

from docthu import CoercionError, MatchError, Template, TemplateParseError, parse


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
