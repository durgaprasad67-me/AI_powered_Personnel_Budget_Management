import re
from datetime import date as Date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Literal, get_args

from pydantic import AfterValidator, BeforeValidator, Field


# APPLICATION SETTINGS
IST = timezone(timedelta(hours=5, minutes=30))

MAX_AMOUNT = 100_000_000
MIN_DATE = Date(2000, 1, 1)
MAX_DAYS_AHEAD = 365

MAX_DESCRIPTION_LENGTH = 200
MAX_CATEGORY_LENGTH = 50


# TRANSACTION TYPES
TransactionTypeName = Literal["income","expense","investment","investment_return","loan_taken","loan_repaid","loan_given","loan_collected",]
TRANSACTION_TYPES = get_args(TransactionTypeName)
CASH_IN_TYPES = ("income","investment_return","loan_taken","loan_collected",)
CASH_OUT_TYPES = ("expense","investment","loan_repaid","loan_given",)


# CATEGORY KEYWORDS
CATEGORY_KEYWORDS = {
    "food": "swiggy zomato restaurant cafe lunch dinner breakfast snack snacks biryani pizza burger tea coffee chai meal",
    "groceries": "grocery groceries vegetables fruits milk supermarket bigbasket blinkit zepto dmart",
    "transport": "uber ola rapido petrol diesel fuel metro bus auto cab taxi train irctc flight parking toll",
    "bills": "electricity water wifi broadband recharge jio airtel postpaid dth bill",
    "rent": "rent",
    "shopping": "amazon flipkart myntra clothes shoes shopping mall",
    "entertainment": "movie netflix spotify hotstar concert game",
    "health": "doctor medicine pharmacy hospital medical clinic gym",
    "education": "course books tuition fees exam udemy",
    "salary": "salary stipend payroll wages",
    "freelance": "freelance client invoice",
    "interest": "interest dividend",
    "refund": "refund cashback reimbursement",
    "investment": "sip mutual fund funds stocks stock shares zerodha groww ppf nps gold crypto bitcoin invested investment fd",
    "loan": "loan emi instalment installment repayment repaid borrowed lent disbursed",
}

CATEGORY_DEFAULT_TYPE = {
    "salary": "income",
    "freelance": "income",
    "interest": "income",
    "refund": "income",
    "investment": "investment",
    "loan": "loan_repaid",
}

TYPE_HINT_WORDS = {
    "investment_return": "redeemed redemption matured maturity",
    "loan_taken": "borrowed disbursed",
    "loan_repaid": "emi installment instalment repayment repaid",
    "loan_given": "lent",
    "loan_collected": "collected recovered",
}

TYPE_DEFAULT_CATEGORY = {
    "investment": "investment",
    "investment_return": "investment",
    "loan_taken": "loan",
    "loan_repaid": "loan",
    "loan_given": "loan",
    "loan_collected": "loan",
}

TYPE_ALIASES = {
    "income": "income",
    "credit": "income",
    "credited": "income",
    "cr": "income",
    "received": "income",
    "expense": "expense",
    "debit": "expense",
    "debited": "expense",
    "dr": "expense",
    "spent": "expense",
    "paid": "expense",
    "withdrawal": "expense",
    "invest": "investment",
    "invested": "investment",
    "sip": "investment",
    "redeemed": "investment_return",
    "redemption": "investment_return",
    "maturity": "investment_return",
    "matured": "investment_return",
    "borrowed": "loan_taken",
    "disbursed": "loan_taken",
    "emi": "loan_repaid",
    "repaid": "loan_repaid",
    "lent": "loan_given",
    "collected": "loan_collected",
    "recovered": "loan_collected",
}


# PRECOMPUTED LOOKUP TABLES
KEYWORD_TO_CATEGORY = {
    word: category
    for category, words in CATEGORY_KEYWORDS.items()
    for word in words.split()
}

TYPE_HINTS = {
    word: transaction_type
    for transaction_type, words in TYPE_HINT_WORDS.items()
    for word in words.split()
}

WORDS = re.compile(r"[a-z]+", re.IGNORECASE)

CURRENCY_JUNK = re.compile(
    r"₹|[$€£,]|\b(?:rs\.?|inr)\b|\s+",
    re.IGNORECASE,
)


# DATE HELPERS
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


# AMOUNT AND TEXT HELPERS

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

# AUTOMATIC CATEGORIZATION

def words_in(*texts) -> list[str]:
    """Extract words from text inputs."""
    result = []
    for text in texts:
        if isinstance(text, str):
            result.extend(WORDS.findall(text.lower()))
    return result


def guess_category(description) -> str:
    """Guess a category using known description keywords."""
    for word in words_in(description):
        category = KEYWORD_TO_CATEGORY.get(word)
        if category:
            return category
    return "other"


def guess_type(category, description) -> str:
    """Guess a transaction type using hints and category defaults."""
    # Explicit description hints take priority.
    for word in words_in(description):
        if word in TYPE_HINTS:
            return TYPE_HINTS[word]

    normalized_category = clean_lower(category)

    # Check the complete category before tokenizing it.
    if normalized_category in CATEGORY_DEFAULT_TYPE:
        return CATEGORY_DEFAULT_TYPE[normalized_category]

    for word in words_in(category):
        group = KEYWORD_TO_CATEGORY.get(word, word)
        if group in CATEGORY_DEFAULT_TYPE:
            return CATEGORY_DEFAULT_TYPE[group]

    return "expense"


def fill_missing_fields(data: dict) -> dict:
    """
    Fill missing transaction fields without mutating the input.

    The backend owns the auto_filled metadata.
    """
    data = dict(data)

    # Never trust client-supplied inference metadata.
    data.pop("auto_filled", None)
    filled = []

    category = clean_lower(data.get("category"))
    description = clean_spaces(data.get("description"))
    kind = normalize_type(data.get("transaction_type"))

    if category is None or (isinstance(category, str) and not category.strip()):
        category = guess_category(description)
        filled.append("category")

    if kind is None or (isinstance(kind, str) and not kind.strip()):
        kind = guess_type(category, description)
        filled.append("transaction_type")

    if "category" in filled and category == "other" and isinstance(kind, str):
        category = TYPE_DEFAULT_CATEGORY.get(kind, category)

    if description is None or (isinstance(description, str) and not description.strip()):
        description = category
        filled.append("description")

    if data.get("date") is None or (isinstance(data.get("date"), str) and not data["date"].strip()):
        filled.append("date")

    data.update(
        category=category,
        transaction_type=kind,
        description=description,
        auto_filled=filled,
    )

    return data


# REUSABLE PYDANTIC FIELD TYPES

Amount = Annotated[
    float,
    BeforeValidator(parse_amount),
    Field(gt=0, le=MAX_AMOUNT, allow_inf_nan=False),
    AfterValidator(round_amount),
]

TransactionType = Annotated[TransactionTypeName,BeforeValidator(normalize_type),]

Category = Annotated[
    str,
    BeforeValidator(clean_lower),
    Field(min_length=1, max_length=MAX_CATEGORY_LENGTH),
]

Description = Annotated[
    str,
    BeforeValidator(clean_spaces),
    Field(min_length=1, max_length=MAX_DESCRIPTION_LENGTH),
]

CreateDate = Annotated[
                    Date,
                    BeforeValidator(date_or_today),
                    AfterValidator(check_date_range),
                ]
UpdateDate = Annotated[
                    Date,
                    BeforeValidator(parse_date_text),
                    AfterValidator(check_date_range),
                ]