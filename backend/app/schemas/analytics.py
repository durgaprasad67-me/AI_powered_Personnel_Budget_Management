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


class TypeDetail(BaseModel):
    type: str
    stream: str
    total: float
    count: int = 0
    categories: dict[str, float] = Field(default_factory=dict)


class MonthlyAnalyticsSummary(BaseModel):
    month: str
    total_income: float
    total_expenses: float
    balance: float
    investments: InvestmentSummary
    loans: LoanSummary
    net_cash_flow: float
    category_breakdown: dict[str, float] = Field(default_factory=dict)
    total_cash_inflow: float = 0.0
    total_cash_outflow: float = 0.0
    type_breakdown: dict[str, float] = Field(default_factory=dict)
    outflow_categories: dict[str, float] = Field(default_factory=dict)
    inflow_categories: dict[str, float] = Field(default_factory=dict)
    type_details: list[TypeDetail] = Field(default_factory=list)


class DashboardResponse(MonthlyAnalyticsSummary):
    allocated_budget: float = Field(ge=0)
    available_allocated_budget: float = Field(ge=0)
    transactions: list[TransactionResponse] = Field(default_factory=list)
    budgets: list[BudgetResponse] = Field(default_factory=list)
    goals: list[FinancialGoalResponse] = Field(default_factory=list)
