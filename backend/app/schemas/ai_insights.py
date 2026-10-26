from datetime import date as Date
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.schemas.common import ( Amount, Category, Description, TransactionType, UpdateDate,)


# CATEGORY SPENDING
class CategorySpending(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Category
    total_amount: float = Field(ge=0,le=100_000_000,allow_inf_nan=False, )
    transaction_count: int = Field(ge=0)


# FINANCIAL SPENDING SUMMARY
class SpendingSummary(BaseModel):
    """
    Financial metrics calculated by Python, not invented by the LLM.
    """
    model_config = ConfigDict(extra="forbid")
    start_date: Date
    end_date: Date
    total_income: float = Field(ge=0,allow_inf_nan=False,)
    total_expenses: float = Field( ge=0,allow_inf_nan=False,)
    total_investments: float = Field(ge=0,allow_inf_nan=False,)
    total_loan_repayments: float = Field(ge=0,allow_inf_nan=False,)
    category_breakdown: list[CategorySpending] = Field(default_factory=list,max_length=100,)

    @model_validator(mode="after")
    def validate_summary_dates(self):
        if self.start_date > self.end_date:
            raise ValueError("start_date must not be after end_date.")
        return self



# REQUEST FINANCIAL INSIGHTS
class SpendingInsightRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field( min_length=3, max_length=1000,)
    start_date: UpdateDate | None = None
    end_date: UpdateDate | None = None
    include_recommendations: bool = True

    @model_validator(mode="after")
    def validate_analysis_dates(self):
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.start_date > self.end_date
        ):
            raise ValueError("start_date must not be after end_date.")
        return self


# FINANCIAL RECOMMENDATION
class FinancialRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1,max_length=100,)
    explanation: str = Field(min_length=1, max_length=1000,)
    estimated_monthly_savings: float | None = Field(default=None,ge=0,le=100_000_000,allow_inf_nan=False,)


# LLM INSIGHT RESPONSE
class SpendingInsightResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=1,max_length=2000,)
    key_findings: list[str] = Field(default_factory=list,max_length=10,)
    recommendations: list[FinancialRecommendation] = Field(default_factory=list,max_length=10,)
    limitations: list[str] = Field(default_factory=list,max_length=10,)

# NATURAL-LANGUAGE TRANSACTION REQUEST
class TransactionTextRequest(BaseModel):
    """
    Accept a natural-language transaction description.
    Example:
        I spent ₹450 on dinner yesterday.
    """
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=3,max_length=1000,)


# LLM-EXTRACTED TRANSACTION
class TransactionExtractionResponse(BaseModel):
    """
    Represents a candidate transaction extracted by an LLM.
    This is not a saved or verified transaction.
    """

    model_config = ConfigDict(extra="forbid")
    amount: Amount
    transaction_type: TransactionType
    category: Category
    description: Description
    date: UpdateDate
    confidence: float = Field(ge=0,le=1,allow_inf_nan=False,)
    requires_confirmation: bool = True