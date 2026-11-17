from pydantic import BaseModel, Field

from app.schemas.budgets import BudgetResponse
from app.schemas.goals import FinancialGoalResponse
from app.schemas.transactions import TransactionResponse


class InvestmentSummary(BaseModel):
    invested: float
    returned: float
    net_invested: float


class LoanSummary(BaseModel):
    borrowed: float
    repaid: float
    lent: float
    collected: float


class MonthlyAnalyticsSummary(BaseModel):
    month: str
    total_income: float
    total_expenses: float
    balance: float
    investments: InvestmentSummary
    loans: LoanSummary
    net_cash_flow: float
    category_breakdown: dict[str, float] = Field(default_factory=dict)


class DashboardResponse(MonthlyAnalyticsSummary):
    allocated_budget: float = Field(ge=0)
    available_allocated_budget: float = Field(ge=0)
    transactions: list[TransactionResponse] = Field(default_factory=list)
    budgets: list[BudgetResponse] = Field(default_factory=list)
    goals: list[FinancialGoalResponse] = Field(default_factory=list)
