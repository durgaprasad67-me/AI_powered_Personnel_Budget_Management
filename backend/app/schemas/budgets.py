from datetime import date as Date
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.schemas.common import (
    Amount,
    Category,
    PlanDate,
)

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
    "income",
    "investment",
    "investment_return",
    "loan_taken",
    "loan_repaid",
    "loan_given",
    "loan_collected",
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
    def validate_budget_dates(self):
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date.")

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