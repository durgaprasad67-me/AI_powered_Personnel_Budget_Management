from pydantic import BaseModel, Field


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
