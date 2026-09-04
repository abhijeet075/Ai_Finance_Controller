"""Deterministic reusable normalization for cross-source finance records."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Final

SUPPORTED_CURRENCIES: Final[frozenset[str]] = frozenset(
    {"AED", "AUD", "CAD", "EUR", "GBP", "INR", "JPY", "SGD", "USD"}
)
NORMALIZATION_VERSION: Final = "1.1.0"

_NAME_ABBREVIATIONS: Final = {
    "TECHNOLOGIES": "TECH", "TECHNOLOGY": "TECH", "TECH": "TECH",
    "PVT": "PRIVATE", "LTD": "LIMITED", "INC": "INCORPORATED",
    "CORP": "CORPORATION", "CO": "COMPANY",
}
_LEGAL_SUFFIXES: Final = frozenset(
    {"COMPANY", "CORPORATION", "INCORPORATED", "LIMITED", "LLC", "LLP", "PLC", "PRIVATE"}
)
_DESCRIPTION_ABBREVIATIONS: Final = {
    "PMT": "PAYMENT", "PYMT": "PAYMENT", "PAYMT": "PAYMENT",
    "TRF": "TRANSFER", "XFER": "TRANSFER", "TXN": "TRANSACTION",
    "DESC": "DESCRIPTION", "INV": "INVOICE", "REF": "REFERENCE",
}
_CURRENCY_ALIASES: Final = {
    "INR": "INR", "RS": "INR", "RUPEE": "INR", "RUPEES": "INR",
    "USD": "USD", "US DOLLAR": "USD", "US DOLLARS": "USD",
    "DOLLAR": "USD", "DOLLARS": "USD",
    "EUR": "EUR", "EURO": "EUR", "EUROS": "EUR",
    "GBP": "GBP", "POUND": "GBP", "POUNDS": "GBP",
    "JPY": "JPY", "YEN": "JPY", "AED": "AED", "DIRHAM": "AED",
    "DIRHAMS": "AED", "AUD": "AUD", "CAD": "CAD", "SGD": "SGD",
}
_CURRENCY_SYMBOLS: Final = {
    "\u20b9": "INR", "\u20ac": "EUR", "\u00a3": "GBP", "\u00a5": "JPY"
}
_DOLLAR_SYMBOLS: Final = {
    "US$": "USD", "A$": "AUD", "AU$": "AUD", "C$": "CAD", "CA$": "CAD",
    "S$": "SGD", "SG$": "SGD",
}
_DOLLAR_CURRENCIES: Final = frozenset({"AUD", "CAD", "SGD", "USD"})


class NormalizationError(ValueError):
    """Raised when normalization would require an unsafe guess."""


def _text(value: object, field: str) -> str:
    if value is None or isinstance(value, bool):
        raise NormalizationError(f"{field} is required")
    result = unicodedata.normalize("NFKC", str(value)).strip()
    if not result:
        raise NormalizationError(f"{field} is required")
    return result


def _words(value: object, field: str) -> list[str]:
    result = unicodedata.normalize("NFKD", _text(value, field))
    result = "".join(char for char in result if not unicodedata.combining(char))
    result = result.replace("&", " AND ").upper()
    result = "".join(char if char.isalnum() else " " for char in result)
    words = result.split()
    if not words:
        raise NormalizationError(f"{field} contains no letters or numbers")
    return words


def normalize_name(value: object) -> str:
    """Canonicalize a party name for deterministic matching."""
    tokens = [_NAME_ABBREVIATIONS.get(token, token) for token in _words(value, "name")]
    if len(tokens) > 2 and tokens[-2:] == ["AND", "COMPANY"]:
        del tokens[-2:]
    while len(tokens) > 1 and tokens[-1] in _LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def normalize_description(value: object) -> str:
    """Canonicalize transaction text and expand common finance abbreviations."""
    return " ".join(
        _DESCRIPTION_ABBREVIATIONS.get(token, token)
        for token in _words(value, "description")
    )


def normalize_currency(value: object, *, default: str | None = None) -> str:
    """Convert supported symbols, names, and codes to ISO currency codes."""
    result = _text(value, "currency").upper()
    if result in _DOLLAR_SYMBOLS:
        return _DOLLAR_SYMBOLS[result]
    if result == "$":
        if default is None:
            raise NormalizationError("currency symbol $ is ambiguous; provide a default code")
        default_alias = re.sub(r"[^A-Z]+", " ", default.upper()).strip()
        currency = _CURRENCY_ALIASES.get(default_alias)
        if currency not in _DOLLAR_CURRENCIES:
            raise NormalizationError("$ default must be AUD, CAD, SGD, or USD")
        return currency
    if result in _CURRENCY_SYMBOLS:
        return _CURRENCY_SYMBOLS[result]
    alias = re.sub(r"[^A-Z]+", " ", result).strip()
    currency = _CURRENCY_ALIASES.get(alias)
    if currency is None or currency not in SUPPORTED_CURRENCIES:
        allowed = ", ".join(sorted(SUPPORTED_CURRENCIES))
        raise NormalizationError(f"currency must resolve to one of {allowed}")
    return currency


def _canonical_number(result: str) -> str:
    if not re.fullmatch(r"[0-9.,]+", result):
        raise NormalizationError("amount must contain only digits and separators")
    comma, point = result.rfind(","), result.rfind(".")
    if comma >= 0 and point >= 0:
        decimal_separator = "," if comma > point else "."
        whole, fraction = result.rsplit(decimal_separator, 1)
        whole = whole.replace(",", "").replace(".", "")
        if not whole or not fraction:
            raise NormalizationError("amount has invalid separators")
        return f"{whole}.{fraction}"
    separator = "," if comma >= 0 else "." if point >= 0 else None
    if separator is None:
        return result
    parts = result.split(separator)
    if any(not part for part in parts):
        raise NormalizationError("amount has invalid separators")
    if len(parts) > 2:
        if all(len(part) == 3 for part in parts[1:]):
            return "".join(parts)
        indian_grouping = (
            1 <= len(parts[0]) <= 3
            and len(parts[-1]) == 3
            and all(len(part) == 2 for part in parts[1:-1])
        )
        if indian_grouping:
            return "".join(parts)
        if len(parts[-1]) in {1, 2} and all(len(part) == 3 for part in parts[1:-1]):
            return f"{''.join(parts[:-1])}.{parts[-1]}"
        raise NormalizationError("amount has ambiguous separators")
    whole, fraction = parts
    if len(fraction) == 3 and whole != "0":
        return whole + fraction
    return f"{whole}.{fraction}"


def normalize_amount(value: object, *, allow_negative: bool = True) -> Decimal:
    """Convert localized monetary values to a two-decimal Decimal."""
    if value is None or isinstance(value, bool):
        raise NormalizationError("amount must be numeric")
    if isinstance(value, Decimal):
        amount = value
    elif isinstance(value, (int, float)):
        try:
            amount = Decimal(str(value))
        except InvalidOperation as exc:
            raise NormalizationError("amount must be numeric") from exc
    else:
        result = unicodedata.normalize("NFKC", str(value)).strip().upper()
        parentheses = result.startswith("(") and result.endswith(")")
        if parentheses:
            result = result[1:-1].strip()
        amount_symbols = {*_CURRENCY_SYMBOLS, *_DOLLAR_SYMBOLS, "$"}
        for symbol in sorted(amount_symbols, key=len, reverse=True):
            result = result.replace(symbol, "")
        for alias in sorted(_CURRENCY_ALIASES, key=len, reverse=True):
            result = re.sub(rf"\b{re.escape(alias)}\b", "", result)
        result = re.sub(r"[\s'_]", "", result)
        sign = -1 if parentheses else 1
        if result.startswith(("+", "-")):
            if parentheses:
                raise NormalizationError("amount uses conflicting sign notation")
            sign *= -1 if result[0] == "-" else 1
            result = result[1:]
        try:
            amount = Decimal(_canonical_number(result)) * sign
        except InvalidOperation as exc:
            raise NormalizationError("amount must be a valid number") from exc
    if not amount.is_finite():
        raise NormalizationError("amount must be finite")
    if not allow_negative and amount < 0:
        raise NormalizationError("amount must not be negative")
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def normalize_date(value: object, *, day_first: bool | None = None) -> date:
    """Normalize common dates and reject ambiguous numeric dates by default."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    result = _text(value, "date")
    if "T" in result or re.search(r"\s\d{1,2}:\d{2}", result):
        try:
            return datetime.fromisoformat(result.replace("Z", "+00:00")).date()
        except ValueError as exc:
            raise NormalizationError("date-time must use ISO-8601") from exc
    compact = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", result)
    if compact:
        try:
            return date(*(int(part) for part in compact.groups()))
        except ValueError as exc:
            raise NormalizationError("date is not a real calendar date") from exc
    year_first = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", result)
    if year_first:
        try:
            return date(*(int(part) for part in year_first.groups()))
        except ValueError as exc:
            raise NormalizationError("date is not a real calendar date") from exc
    numeric = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", result)
    if numeric:
        first, second, year = (int(part) for part in numeric.groups())
        if first > 12:
            day, month = first, second
        elif second > 12:
            month, day = first, second
        elif day_first is None:
            raise NormalizationError("date is ambiguous; set day_first explicitly")
        elif day_first:
            day, month = first, second
        else:
            month, day = first, second
        try:
            return date(year, month, day)
        except ValueError as exc:
            raise NormalizationError("date is not a real calendar date") from exc
    for format_string in ("%d %b %Y", "%d %B %Y", "%b %d %Y", "%B %d %Y"):
        try:
            return datetime.strptime(result, format_string).date()
        except ValueError:
            continue
    raise NormalizationError("date format is unsupported")
