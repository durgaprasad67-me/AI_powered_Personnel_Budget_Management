from datetime import date as Date
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.domain.transaction_types import CASH_IN_TYPES
from app.schemas.types import (
    Amount,
    Category,
    PlanDate,
)

INFLOW_CATEGORIES = {"salary", "freelance", "interest", "refund"}

BudgetPeriod = Literal[
    "weekly",
    "monthly",
    "quarterly",
    "yearly",
    "custom",
]
BudgetTransactionType = Literal[
    "all",
    "expense",
    "investment",
    "loan_repaid",
    "loan_given",
]


# CREATE BUDGET
class BudgetCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(default="Budget", min_length=1, max_length=100)

    # None means the budget covers all eligible categories.
    category: Category | None = None
    transaction_type: BudgetTransactionType = "expense"

    amount: Amount

    start_date: PlanDate
    end_date: PlanDate | None = None

    @model_validator(mode="after")
    def validate_budget_rules(self):
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date.")
        if self.transaction_type in CASH_IN_TYPES:
            raise ValueError(
                f"Budgets cannot be created for cash inflow types ('{self.transaction_type}'). "
                "Budgets only apply to cash outflow types (expense, investment, loan_repaid, loan_given, all)."
            )
        if self.category and self.category.lower() in INFLOW_CATEGORIES:
            raise ValueError(
                f"'{self.category}' is a cash inflow category. Budgets can only be set for cash outflow categories."
            )
        return self


# UPDATE BUDGET
class BudgetUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    category: Category | None = None
    transaction_type: BudgetTransactionType | None = None
    amount: Amount | None = None
    start_date: PlanDate | None = None
    end_date: PlanDate | None = None

    @model_validator(mode="after")
    def validate_budget_rules(self):
        if self.end_date is not None and self.start_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date.")
        if self.transaction_type is not None and self.transaction_type in CASH_IN_TYPES:
            raise ValueError(
                f"Budgets cannot be created for cash inflow types ('{self.transaction_type}'). "
                "Budgets only apply to cash outflow types (expense, investment, loan_repaid, loan_given, all)."
            )
        if self.category is not None and self.category.lower() in INFLOW_CATEGORIES:
            raise ValueError(
                f"'{self.category}' is a cash inflow category. Budgets can only be set for cash outflow categories."
            )
        return self


# BUDGET RESPONSE
class BudgetResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1)

    name: str = "Budget"
    category: Category | None = None
    transaction_type: BudgetTransactionType = "expense"

    amount: Amount

    start_date: Date
    end_date: Date | None = None


class BudgetListResponse(BaseModel):
    items: list[BudgetResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    skip: int = Field(ge=0)


# BUDGET PROGRESS
class BudgetProgress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    budget_id: str
    budget_amount: Amount

    spent_amount: float = Field(
        ge=0,
        le=100_000_000,
        allow_inf_nan=False,
    )

    remaining_amount: float = Field(
        allow_inf_nan=False,
    )

    percentage_used: float = Field(
        ge=0,
        allow_inf_nan=False,
    )

    is_over_budget: bool
