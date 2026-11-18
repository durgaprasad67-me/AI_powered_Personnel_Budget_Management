from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.domain.dates import today_ist
from app.schemas.transactions import TransactionCreate, TransactionUpdate

BASE = {
    "amount": 10,
    "transaction_type": "expense",
    "category": "Food",
    "description": "Lunch",
}


def make(**changes):
    return TransactionCreate.model_validate({**BASE, **changes})


def test_transaction_schema_accepts_valid_transaction():
    transaction = make(amount=125.5, date="2026-10-23")

    assert transaction.amount == 125.5
    assert transaction.transaction_type == "expense"
    assert transaction.category == "food"
    assert transaction.auto_filled == []


def test_type_and_category_ignore_case_and_extra_spaces():
    transaction = make(
        transaction_type=" EXPENSE ",
        category="  Food  ",
        date="2026-10-23",
    )

    assert transaction.transaction_type == "expense"
    assert transaction.category == "food"


def test_credit_and_debit_are_understood():
    assert make(transaction_type="Credit").transaction_type == "income"
    assert make(transaction_type="DEBIT").transaction_type == "expense"


def test_given_category_is_never_replaced():
    transaction = make(category="Petrol", description="Bike", date="2026-10-23")

    assert transaction.category == "petrol"
    assert "category" not in transaction.auto_filled


def test_unknown_field_is_rejected():
    with pytest.raises(ValidationError):
        make(catagory="food")


def test_messy_amounts_are_cleaned():
    assert make(amount="₹1,200.50").amount == 1200.5
    assert make(amount="Rs. 500").amount == 500.0
    assert make(amount=10.456).amount == 10.46


@pytest.mark.parametrize(
    "bad_amount",
    [0, -5, -0.01, True, float("inf"), float("nan"), "abc", "1e5", "2.5e3"],
)
def test_bad_amounts_are_rejected(bad_amount):
    with pytest.raises(ValidationError):
        make(amount=bad_amount)


def test_missing_required_fields_are_rejected():
    # Missing amount
    with pytest.raises(ValidationError):
        TransactionCreate.model_validate({
            "transaction_type": "expense",
            "category": "food",
        })
    # Missing transaction_type
    with pytest.raises(ValidationError):
        TransactionCreate.model_validate({
            "amount": 100,
            "category": "food",
        })
    # Missing category
    with pytest.raises(ValidationError):
        TransactionCreate.model_validate({
            "amount": 100,
            "transaction_type": "expense",
        })


def test_category_length_and_formatting():
    # Category < 2 chars is rejected
    with pytest.raises(ValidationError):
        make(category="a")
    # Category > 30 chars is rejected
    with pytest.raises(ValidationError):
        make(category="a" * 31)
    # Category 2 chars is accepted
    assert make(category="ab").category == "ab"
    # Category 30 chars is accepted
    assert len(make(category="a" * 30).category) == 30
    # Category collapses internal spaces and lowercases
    assert make(category="  Food   Dining  ").category == "food dining"


def test_description_optional_sanitized_and_html_stripped():
    # Description is optional and defaults to empty string
    tx_no_desc = make()
    assert tx_no_desc.description == "Lunch"

    tx_empty = TransactionCreate.model_validate({
        "amount": 50,
        "transaction_type": "expense",
        "category": "food",
    })
    assert tx_empty.description == ""

    # HTML tags and control chars are stripped
    tx_html = make(description="<script>alert(1)</script>Lunch at <b>Cafe</b>")
    assert tx_html.description == "alert(1)Lunch at Cafe"

    # Description > 200 chars is rejected
    with pytest.raises(ValidationError):
        make(description="x" * 201)


def test_missing_date_defaults_to_today():
    transaction = TransactionCreate.model_validate(BASE)

    assert transaction.date == today_ist()
    assert "date" in transaction.auto_filled


def test_blank_date_defaults_to_today():
    assert make(date="").date == today_ist()


def test_given_date_is_kept():
    assert str(make(date="2026-01-05").date) == "2026-01-05"


def test_date_words_and_day_first_formats_work():
    assert make(date="today").date == today_ist()
    assert make(date="Yesterday").date == today_ist() - timedelta(days=1)
    assert make(date="05-01-2026").date == date(2026, 1, 5)
    assert make(date="05/01/2026").date == date(2026, 1, 5)


@pytest.mark.parametrize("bad_date", ["1990-01-01", "2099-01-01", "not a date"])
def test_unreasonable_dates_are_rejected(bad_date):
    with pytest.raises(ValidationError):
        make(date=bad_date)


def test_future_date_is_rejected():
    tomorrow = today_ist() + timedelta(days=1)
    with pytest.raises(ValidationError):
        make(date=str(tomorrow))


def test_update_schema_cleans_values():
    updates = TransactionUpdate.model_validate({"category": "  FOOD ", "amount": "₹99"})

    assert updates.model_dump(exclude_unset=True) == {
        "category": "food",
        "amount": 99.0,
    }


def test_loan_and_investment_type_words_are_understood():
    assert make(transaction_type="Invested").transaction_type == "investment"
    assert make(transaction_type="EMI").transaction_type == "loan_repaid"


def test_bare_loan_type_is_rejected_because_it_is_ambiguous():
    with pytest.raises(ValidationError):
        make(transaction_type="loan")
