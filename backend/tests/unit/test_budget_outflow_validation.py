import pytest
from pydantic import ValidationError
from app.schemas.budgets import BudgetCreate, BudgetUpdate
from app.api.v1.endpoints.dashboard import _transaction_matches_budget
from app.repositories.budgets import budget_category_values


def test_budget_create_accepts_cash_outflows():
    for tx_type in ("expense", "investment", "loan_repaid", "loan_given", "all"):
        budget = BudgetCreate(
            name=f"{tx_type} budget",
            category="food" if tx_type == "expense" else None,
            transaction_type=tx_type,
            amount=5000.0,
            start_date="2026-11-01",
        )
        assert budget.transaction_type == tx_type


def test_budget_create_rejects_cash_inflows():
    for tx_type in ("income", "investment_return", "loan_taken", "loan_collected"):
        with pytest.raises(ValidationError) as exc_info:
            BudgetCreate(
                name=f"{tx_type} budget",
                transaction_type=tx_type,
                amount=5000.0,
                start_date="2026-11-01",
            )
        assert "transaction_type" in str(exc_info.value)


def test_budget_create_rejects_inflow_categories():
    for cat in ("salary", "freelance", "interest", "refund"):
        with pytest.raises(ValueError, match="is a cash inflow category"):
            BudgetCreate(
                name="Inflow budget",
                category=cat,
                transaction_type="expense",
                amount=5000.0,
                start_date="2026-11-01",
            )


def test_budget_update_rejects_inflow_types_and_categories():
    with pytest.raises(ValidationError):
        BudgetUpdate(transaction_type="income")

    with pytest.raises(ValueError, match="is a cash inflow category"):
        BudgetUpdate(category="salary")


def test_dashboard_transaction_matches_budget_cash_outflow_only():
    all_budget = {"transaction_type": "all", "category": None}
    food_budget = {"transaction_type": "expense", "category": "food"}
    invest_budget = {"transaction_type": "investment", "category": "investment"}

    # Cash outflows should match corresponding budgets
    assert _transaction_matches_budget({"transaction_type": "expense", "category": "food"}, all_budget) is True
    assert _transaction_matches_budget({"transaction_type": "investment", "category": "investment"}, all_budget) is True
    assert _transaction_matches_budget({"transaction_type": "loan_repaid", "category": "loan"}, all_budget) is True
    assert _transaction_matches_budget({"transaction_type": "loan_given", "category": "loan"}, all_budget) is True
    assert _transaction_matches_budget({"transaction_type": "expense", "category": "food"}, food_budget) is True
    assert _transaction_matches_budget({"transaction_type": "investment", "category": "investment"}, invest_budget) is True

    # Cash inflows should NEVER match any budget, even 'all'
    assert _transaction_matches_budget({"transaction_type": "income", "category": "salary"}, all_budget) is False
    assert _transaction_matches_budget({"transaction_type": "investment_return", "category": "investment"}, all_budget) is False
    assert _transaction_matches_budget({"transaction_type": "loan_taken", "category": "loan"}, all_budget) is False
    assert _transaction_matches_budget({"transaction_type": "loan_collected", "category": "loan"}, all_budget) is False
    assert _transaction_matches_budget({"transaction_type": "income", "category": "salary"}, food_budget) is False


def test_budget_category_values_outflow():
    assert budget_category_values("food") == ["food"]
    assert budget_category_values("  GROCERIES  ") == ["groceries"]
    assert budget_category_values(None) is None
    assert budget_category_values("") is None
    assert budget_category_values("all") is None
    assert budget_category_values("All categories") is None


def test_custom_category_budget_creation_and_case_insensitivity():
    # User can create a budget with any custom category (e.g. Gaming, Gym, boovan)
    budget = BudgetCreate(
        name="Gaming Budget",
        category="Gaming",
        transaction_type="expense",
        amount=2000.0,
        start_date="2026-11-01",
    )
    # Stored category is lowercased automatically by Category normalizer
    assert budget.category == "gaming"


def test_custom_category_transaction_triggers_budget_case_insensitively():
    import asyncio
    from app.core.exceptions import InvalidInputError
    from app.schemas.transactions import TransactionCreate
    from app.services.transactions import TransactionService
    from tests.fakes import FakeBudgetRepository, FakeTransactionRepository

    # Budget set for custom category "gaming"
    budget_repo = FakeBudgetRepository([
        {
            "id": "b1",
            "name": "Gaming Budget",
            "category": "gaming",
            "transaction_type": "expense",
            "amount": 2000.0,
            "start_date": "2026-11-01",
            "end_date": "2026-11-30",
        }
    ])
    tx_repo = FakeTransactionRepository()
    budget_repo.transaction_repository = tx_repo
    tx_service = TransactionService(tx_repo, budget_repository=budget_repo)

    # 1. First transaction: Inflow to have available cash
    asyncio.run(
        tx_service.create(
            TransactionCreate(
                date="2026-11-02",
                amount=10000.0,
                category="salary",
                transaction_type="income",
                description="Salary",
            )
        )
    )

    # 2. Add custom category transaction with mixed case "Gaming" within budget
    tx1 = asyncio.run(
        tx_service.create(
            TransactionCreate(
                date="2026-11-10",
                amount=1500.0,
                category="Gaming",
                transaction_type="expense",
                description="New Steam game",
            )
        )
    )
    assert tx1["category"] == "gaming"

    # 3. Add second transaction exceeding the remaining budget (2000 - 1500 = 500 remaining, trying 800)
    with pytest.raises(InvalidInputError, match="Remaining budget"):
        asyncio.run(
            tx_service.create(
                TransactionCreate(
                    date="2026-11-15",
                    amount=800.0,
                    category="GAMING",
                    transaction_type="expense",
                    description="Another game",
                )
            )
        )


def test_all_categories_and_types_budget_triggers_on_custom_category_outflow():
    import asyncio
    from app.core.exceptions import InvalidInputError
    from app.schemas.transactions import TransactionCreate
    from app.services.transactions import TransactionService
    from tests.fakes import FakeBudgetRepository, FakeTransactionRepository

    # Global budget: applies to "all" cash outflows and all categories (category=None)
    budget_repo = FakeBudgetRepository([
        {
            "id": "b_global",
            "name": "Overall Outflow Budget",
            "category": None,
            "transaction_type": "all",
            "amount": 5000.0,
            "start_date": "2026-11-01",
            "end_date": "2026-11-30",
        }
    ])
    tx_repo = FakeTransactionRepository()
    budget_repo.transaction_repository = tx_repo
    tx_service = TransactionService(tx_repo, budget_repository=budget_repo)

    # Inflow to provide cash
    asyncio.run(
        tx_service.create(
            TransactionCreate(
                date="2026-11-02",
                amount=20000.0,
                category="salary",
                transaction_type="income",
                description="Monthly Salary",
            )
        )
    )

    # Outflow transaction with custom category "Gym"
    tx1 = asyncio.run(
        tx_service.create(
            TransactionCreate(
                date="2026-11-05",
                amount=3500.0,
                category="Gym",
                transaction_type="expense",
                description="Gym Annual Fee",
            )
        )
    )
    assert tx1["category"] == "gym"

    # Second outflow with another custom category "Boovan" that pushes total over 5000 (3500 + 2000 = 5500 > 5000)
    with pytest.raises(InvalidInputError, match="Remaining budget"):
        asyncio.run(
            tx_service.create(
                TransactionCreate(
                    date="2026-11-06",
                    amount=2000.0,
                    category="boovan",
                    transaction_type="expense",
                    description="boovan expense",
                )
            )
        )


def test_dashboard_transaction_matches_custom_category():
    gaming_budget = {"transaction_type": "expense", "category": "gaming"}
    all_budget = {"transaction_type": "all", "category": None}

    # Custom category matches case-insensitively
    assert _transaction_matches_budget({"transaction_type": "expense", "category": "Gaming"}, gaming_budget) is True
    assert _transaction_matches_budget({"transaction_type": "expense", "category": "gaming"}, gaming_budget) is True
    assert _transaction_matches_budget({"transaction_type": "expense", "category": "GAMING"}, gaming_budget) is True

    # Custom category matches "all" budget for any cash outflow type
    assert _transaction_matches_budget({"transaction_type": "expense", "category": "Gaming"}, all_budget) is True
    assert _transaction_matches_budget({"transaction_type": "investment", "category": "Crypto"}, all_budget) is True
    assert _transaction_matches_budget({"transaction_type": "loan_repaid", "category": "PersonalLoan"}, all_budget) is True

    # Inflow with custom category never matches budget
    assert _transaction_matches_budget({"transaction_type": "income", "category": "GamingPrize"}, all_budget) is False

