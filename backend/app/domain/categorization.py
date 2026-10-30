import re

from app.domain.normalization import clean_lower, clean_spaces, normalize_type

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
    for word in words_in(description):
        if word in TYPE_HINTS:
            return TYPE_HINTS[word]

    normalized_category = clean_lower(category)
    if normalized_category in CATEGORY_DEFAULT_TYPE:
        return CATEGORY_DEFAULT_TYPE[normalized_category]

    for word in words_in(category):
        group = KEYWORD_TO_CATEGORY.get(word, word)
        if group in CATEGORY_DEFAULT_TYPE:
            return CATEGORY_DEFAULT_TYPE[group]

    return "expense"


def fill_missing_fields(data: dict) -> dict:
    """Fill missing transaction fields without mutating the input."""
    data = dict(data)
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

    if description is None or (
        isinstance(description, str) and not description.strip()
    ):
        description = category
        filled.append("description")

    if data.get("date") is None or (
        isinstance(data.get("date"), str) and not data["date"].strip()
    ):
        filled.append("date")

    data.update(
        category=category,
        transaction_type=kind,
        description=description,
        auto_filled=filled,
    )
    return data
