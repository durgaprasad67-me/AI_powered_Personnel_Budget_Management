import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.domain.transaction_types import TYPE_ALIASES

MAX_AMOUNT = 100_000_000
CURRENCY_JUNK = re.compile(
    r"₹|[$€£,]|\b(?:rs\.?|inr)(?=\s|\d|$)|\s+",
    re.IGNORECASE,
)


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


def normalize_type(value):
    """Normalize aliases to canonical transaction types."""
    if isinstance(value, str):
        normalized = clean_lower(value)
        return TYPE_ALIASES.get(normalized, normalized)
    return value


def parse_amount(value):
    """Accept numbers and currency strings such as ₹1,200.50."""
    if isinstance(value, bool):
        raise ValueError("Amount must be a number.")

    if isinstance(value, str):
        return CURRENCY_JUNK.sub("", value.strip())

    return value


def round_amount(value: float) -> float:
    """Round an amount to two decimal places."""
    rounded = float(
        Decimal(str(value)).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
    )

    if rounded <= 0:
        raise ValueError("Amount must be at least 0.01.")
    if rounded > MAX_AMOUNT:
        raise ValueError("Amount exceeds the permitted maximum.")

    return rounded


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
