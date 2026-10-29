from datetime import date, timedelta

from app.domain.categorization import guess_category, guess_type
from app.domain.dates import parse_date_text, today_ist
from app.domain.normalization import normalize_amount, normalize_type


def test_parse_date_text_supports_natural_and_day_first_dates():
    assert parse_date_text("today") == today_ist()
    assert parse_date_text("yesterday") == today_ist() - timedelta(days=1)
    assert parse_date_text("05-01-2026") == date(2026, 1, 5)


def test_normalization_handles_currency_and_transaction_aliases():
    assert normalize_amount("Rs. 1,200.50") == 1200.50
    assert normalize_amount("(500)") == -500
    assert normalize_type("credited") == "income"
    assert normalize_type("invested") == "investment"


def test_categorization_uses_description_hints_before_defaults():
    assert guess_category("Swiggy dinner") == "food"
    assert guess_type("loan", "Home loan EMI") == "loan_repaid"
