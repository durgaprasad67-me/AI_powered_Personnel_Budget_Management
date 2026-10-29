from datetime import date as Date
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
MIN_DATE = Date(2000, 1, 1)
MAX_DAYS_AHEAD = 365


def today_ist() -> Date:
    """Return today's date in Indian Standard Time."""
    return datetime.now(IST).date()


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
    """Validate the supported transaction date range."""
    if value < MIN_DATE or value > today_ist() + timedelta(days=MAX_DAYS_AHEAD):
        raise ValueError(
            "Date must be on or after 2000-01-01 "
            "and no more than one year ahead."
        )
    return value
