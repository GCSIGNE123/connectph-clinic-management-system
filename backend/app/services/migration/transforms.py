"""Real implementations of the transform types declared on
`migration_field_mappings.transform_type`: DateFormat, PhoneFormat, Trim.
`Rename`/`Custom` are architecture-only (Rename is implicit in the
mapping itself; Custom is a placeholder for a future scripting hook)."""

import re
from datetime import date, datetime
from typing import Any

PHONE_DIGITS_RE = re.compile(r"[^0-9+]")


def apply_transform(value: Any, transform_type: str, transform_config: dict | None) -> Any:
    if value is None:
        return None
    if transform_type == "Trim":
        return str(value).strip()
    if transform_type == "PhoneFormat":
        return format_phone(str(value))
    if transform_type == "DateFormat":
        fmt = (transform_config or {}).get("source_format", "%Y-%m-%d")
        return parse_date(str(value), fmt)
    return value


def format_phone(raw: str) -> str:
    """Normalize a legacy phone number into the `+?[0-9]{7,15}` shape the
    Patient/Doctor schemas require (strips spaces/dashes/parens; converts
    a leading Philippine trunk '0' to '+63' when the result would
    otherwise be too short to be a mobile number)."""
    digits = PHONE_DIGITS_RE.sub("", raw.strip())
    if digits.startswith("09") and len(digits) == 11:
        digits = "+63" + digits[1:]
    return digits


def parse_date(raw: str, source_format: str) -> date | None:
    raw = raw.strip()
    if not raw:
        return None
    candidates = [source_format, "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%m-%d-%Y"]
    for fmt in candidates:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None
