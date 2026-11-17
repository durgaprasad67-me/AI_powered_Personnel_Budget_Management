import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.domain.transaction_types import TYPE_ALIASES

import math
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.core.config import get_settings
from app.domain.transaction_types import TYPE_ALIASES

CURRENCY_JUNK = re.compile(
    r"₹|[$€£,]|\b(?:rs\.?|inr)(?=\s|\d|$)|\s+",
    re.IGNORECASE,
)
HTML_TAGS = re.compile(r"<[^>]*>")
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_spaces(value):
    """Collapse repeated whitespace."""
    if isinstance(value, str):
        return " ".join(value.split())
    return value


def clean_lower(value):
    """Normalize text to lowercase."""
    if isinstance(value, str):
        return clean_spaces(value).lower()
    return value


def normalize_category(value) -> str:
    """Normalize category: required, trimmed, collapsed spaces, lowercase, 2-30 chars."""
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError("Category is required.")
    if not isinstance(value, str):
        raise ValueError("Category must be text.")
    normalized = clean_lower(value)
    settings = get_settings()
    if len(normalized) < settings.category_min_length or len(normalized) > settings.category_max_length:
        raise ValueError(
            f"Category must be between {settings.category_min_length} and "
            f"{settings.category_max_length} characters."
        )
    return normalized


def clean_description(value) -> str:
    """Sanitize description: optional, max 200 chars, strip control characters & HTML."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    # Strip HTML tags and control characters to prevent injection
    text = HTML_TAGS.sub("", value)
    text = CONTROL_CHARS.sub("", text)
    cleaned = clean_spaces(text)
    settings = get_settings()
    if len(cleaned) > settings.description_max_length:
        raise ValueError(
            f"Description must not exceed {settings.description_max_length} characters."
        )
    return cleaned


def normalize_type(value):
    """Normalize aliases to canonical transaction types."""
    if isinstance(value, str):
        normalized = clean_lower(value)
        return TYPE_ALIASES.get(normalized, normalized)
    return value


def parse_amount(value):
    """Accept numbers and currency strings such as ₹1,200.50, rejecting scientific notation."""
    if isinstance(value, bool):
        raise ValueError("Amount must be a number.")

    if isinstance(value, (int, float)):
        # Check for NaN / Infinity
        if math.isnan(value) or math.isinf(value):
            raise ValueError("Amount must be a finite number.")

    if isinstance(value, str):
        # Reject scientific notation
        if re.search(r"[eE]", value):
            raise ValueError("Scientific notation is not permitted for amounts.")
        cleaned = CURRENCY_JUNK.sub("", value.strip())
        if not cleaned:
            raise ValueError("Amount is required.")
        return cleaned

    return value


def round_amount(value: float) -> float:
    """Validate amount using Decimal-safe handling and round to 2 decimal places."""
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Invalid transaction amount.") from exc

    if not dec.is_finite():
        raise ValueError("Transaction amount must be finite.")

    rounded_dec = dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if rounded_dec <= Decimal("0"):
        raise ValueError("Amount must be greater than 0.")

    return float(rounded_dec)


def _unwrap_negative_amount(text: str) -> tuple[str, bool]:
    """Remove accounting-style parentheses and report whether they were used."""
    is_negative = text.startswith("(") and text.endswith(")")
    if is_negative:
        return text[1:-1].strip(), True
    return text, False


def _parse_decimal_text(text: str, original_value) -> Decimal:
    """Validate and convert normalized amount text."""
    if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", text):
        raise ValueError(f"Invalid transaction amount: {original_value!r}")

    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid transaction amount: {original_value!r}") from exc


def _parse_amount_text(value) -> Decimal:
    """Parse an amount represented as text."""
    text, is_negative = _unwrap_negative_amount(str(value).strip())
    text = re.sub(r"[₹$€£,\s]|(?:rs\.?|inr)", "", text, flags=re.IGNORECASE)
    amount = _parse_decimal_text(text, value)
    return -abs(amount) if is_negative else amount


def normalize_amount(value) -> Decimal | None:
    """Convert common financial amount strings to Decimal."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None

    if isinstance(value, bool):
        raise ValueError("Boolean values are not valid transaction amounts.")

    if isinstance(value, Decimal):
        amount = value
    else:
        amount = _parse_amount_text(value)

    if not amount.is_finite():
        raise ValueError("Transaction amount must be finite.")

    return amount


def normalize_transaction_type(value) -> str | None:
    """Standardize common transaction type labels from imported data."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None

    text = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    return TYPE_ALIASES.get(text, text)
