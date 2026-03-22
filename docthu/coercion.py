"""
Type coercion for extracted string values.
"""

from __future__ import annotations

import re
from datetime import date, datetime


class CoercionError(Exception):
    def __init__(self, var_name: str, raw_value: str, target_type: str) -> None:
        self.var_name = var_name
        self.raw_value = raw_value
        self.target_type = target_type
        super().__init__(
            f"Cannot coerce '{raw_value}' to {target_type} for variable '{var_name}'"
        )


# Common date/datetime formats to try in order
_DATE_FORMATS = [
    "%d/%m/%Y",
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%m/%d/%Y",
    "%Y/%m/%d",
]

_DATETIME_FORMATS = (
    [fmt + " %H:%M:%S" for fmt in _DATE_FORMATS]
    + [fmt + " %H:%M" for fmt in _DATE_FORMATS]
    + _DATE_FORMATS
)  # fallback: date-only parsed as datetime at midnight


def coerce(var_name: str, raw: str, type_: str) -> object:
    """Coerce *raw* string to the requested *type_*. Raises CoercionError on failure."""
    raw = raw.strip()
    if type_ == "str":
        return raw
    if type_ == "int":
        return _to_int(var_name, raw)
    if type_ == "float":
        return _to_float(var_name, raw)
    if type_ == "date":
        return _to_date(var_name, raw)
    if type_ == "datetime":
        return _to_datetime(var_name, raw)
    raise CoercionError(var_name, raw, type_)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalize_number(raw: str) -> str:
    """
    Normalise a localised number string to plain decimal.

    Handles:
      "588,000"   → "588000"   (comma as thousands separator)
      "1.327.455" → "1327455"  (dot as thousands separator)
      "1,327.45"  → "1327.45"  (comma thousands, dot decimal)
      "1.327,45"  → "1327.45"  (dot thousands, comma decimal)
    """
    # Detect decimal marker: if both comma and dot present, the last one is decimal
    has_comma = "," in raw
    has_dot = "." in raw

    if has_comma and has_dot:
        last_comma = raw.rfind(",")
        last_dot = raw.rfind(".")
        if last_comma > last_dot:
            # comma is decimal separator (European style): 1.327,45
            raw = raw.replace(".", "").replace(",", ".")
        else:
            # dot is decimal separator (US style): 1,327.45
            raw = raw.replace(",", "")
    elif has_comma:
        # Could be thousands (588,000 or 30,000,000) or decimal (3,14)
        # If every group after the first is exactly 3 digits → thousands separator
        parts = raw.split(",")
        if len(parts) >= 2 and all(re.fullmatch(r"\d{3}", p) for p in parts[1:]):
            raw = raw.replace(",", "")
        else:
            raw = raw.replace(",", ".")
    elif has_dot:
        parts = raw.split(".")
        if len(parts) >= 2 and all(re.fullmatch(r"\d{3}", p) for p in parts[1:]):
            raw = raw.replace(".", "")
        # else: normal decimal dot — leave as-is

    return raw


def _to_int(var_name: str, raw: str) -> int:
    try:
        return int(_normalize_number(raw))
    except (ValueError, TypeError):
        raise CoercionError(var_name, raw, "int")


def _to_float(var_name: str, raw: str) -> float:
    try:
        return float(_normalize_number(raw))
    except (ValueError, TypeError):
        raise CoercionError(var_name, raw, "float")


def _to_date(var_name: str, raw: str) -> date:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise CoercionError(var_name, raw, "date")


def _to_datetime(var_name: str, raw: str) -> datetime:
    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    raise CoercionError(var_name, raw, "datetime")
