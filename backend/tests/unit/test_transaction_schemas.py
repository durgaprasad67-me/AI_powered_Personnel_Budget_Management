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
    [0, -5, 0.001, True, float("inf"), float("nan"), 10**12, "abc"],
)
def test_bad_amounts_are_rejected(bad_amount):
    with pytest.raises(ValidationError):
        make(amount=bad_amount)


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


def test_amount_only_input_is_filled_in():
    transaction = TransactionCreate.model_validate({"amount": 250})

    assert transaction.transaction_type == "expense"
    assert transaction.category == "other"
    assert transaction.description == "other"
    assert transaction.date == today_ist()
    assert transaction.auto_filled == [
        "category",
        "transaction_type",
        "description",
        "date",
    ]


def test_category_is_guessed_from_description():
    transaction = TransactionCreate.model_validate(
        {"amount": 250, "description": "Swiggy dinner", "date": "2026-10-23"}
    )

    assert transaction.category == "food"
    assert transaction.transaction_type == "expense"
    assert transaction.description == "Swiggy dinner"
    assert transaction.auto_filled == ["category", "transaction_type"]


def test_income_is_guessed_from_description():
    transaction = TransactionCreate.model_validate(
        {"amount": "₹50,000", "description": "October salary", "date": "2026-10-23"}
    )

    assert transaction.amount == 50000.0
    assert transaction.category == "salary"
    assert transaction.transaction_type == "income"


def test_update_schema_cleans_values_but_guesses_nothing():
    updates = TransactionUpdate.model_validate({"category": "  FOOD ", "amount": "₹99"})

    assert updates.model_dump(exclude_unset=True) == {"category": "food", "amount": 99.0}


def guess(**fields):
    return TransactionCreate.model_validate({"amount": 1000, "date": "2026-10-23", **fields})


def test_sip_is_an_investment_not_an_expense():
    transaction = guess(description="Monthly SIP")

    assert (transaction.category, transaction.transaction_type) == ("investment", "investment")


def test_redeemed_investment_is_money_coming_back():
    transaction = guess(description="Mutual fund redeemed")

    assert transaction.category == "investment"
    assert transaction.transaction_type == "investment_return"


def test_emi_is_a_loan_repayment():
    transaction = guess(description="Home loan EMI")

    assert (transaction.category, transaction.transaction_type) == ("loan", "loan_repaid")


def test_borrowing_and_lending_are_understood():
    assert guess(description="Personal loan disbursed").transaction_type == "loan_taken"
    assert guess(description="Lent to Ravi").transaction_type == "loan_given"


def test_type_without_category_gets_a_sensible_category():
    transaction = guess(transaction_type="Borrowed")

    assert (transaction.category, transaction.transaction_type) == ("loan", "loan_taken")
    assert transaction.auto_filled == ["category", "description"]


def test_loan_and_investment_type_words_are_understood():
    assert make(transaction_type="Invested").transaction_type == "investment"
    assert make(transaction_type="EMI").transaction_type == "loan_repaid"


def test_bare_loan_type_is_rejected_because_it_is_ambiguous():
    with pytest.raises(ValidationError):
        make(transaction_type="loan")
