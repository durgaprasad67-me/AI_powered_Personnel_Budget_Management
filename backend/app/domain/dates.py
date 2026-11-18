from datetime import date as Date
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings

IST = timezone(timedelta(hours=5, minutes=30))


def today_ist() -> Date:
    """Return today's date in Indian Standard Time."""
    return datetime.now(IST).date()


def get_date_floor() -> Date:
    """Dynamic past date floor based on configured number of years."""
    current = today_ist()
    years = get_settings().transaction_date_floor_years
    try:
        return current.replace(year=current.year - years)
    except ValueError:
        # Handle Feb 29 leap day fallback
        return current.replace(year=current.year - years, day=28)


def parse_date_text(value):
    """Parse supported natural-language and Indian date formats."""
    if not isinstance(value, str):
        return value

    text = value.strip().lower()

    if text == "today":
        return today_ist()

    if text == "yesterday":
        return today_ist() - timedelta(days=1)

    for pattern in ("%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue

    return text


def date_or_today(value):
    """Use today's date for a missing or blank date."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return today_ist()
    return parse_date_text(value)


def check_date_range(value: Date) -> Date:
    """Validate that date is not in the future and not older than dynamic floor."""
    current_today = today_ist()
    if value > current_today:
        raise ValueError("Transaction date cannot be in the future.")

    floor_date = get_date_floor()
    if value < floor_date:
        years = get_settings().transaction_date_floor_years
        raise ValueError(
            f"Transaction date cannot be older than {years} years ({floor_date.isoformat()})."
        )
    return value


def check_plan_date(value: Date) -> Date:
    """Validate that budget or goal date is not older than dynamic floor (future dates are allowed)."""
    floor_date = get_date_floor()
    if value < floor_date:
        years = get_settings().transaction_date_floor_years
        raise ValueError(
            f"Date cannot be older than {years} years ({floor_date.isoformat()})."
        )
    return value
