from datetime import date as Date
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import (
    Amount,
    Category,
    CreateDate,
    Description,
    TransactionType,
    UpdateDate,
    fill_missing_fields,
    today_ist,
)



# CREATE TRANSACTION
class TransactionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: Amount
    transaction_type: TransactionType | None = None
    category: Category | None = None
    description: Description | None = None
    date: CreateDate = Field(default_factory=today_ist)
    auto_filled: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def fill_in_missing_fields(cls, data):
        if isinstance(data, dict):
            return fill_missing_fields(data)
        return data



# UPDATE TRANSACTION
class TransactionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: Amount | None = None
    transaction_type: TransactionType | None = None
    category: Category | None = None
    description: Description | None = None
    date: UpdateDate | None = None



# TRANSACTION RESPONSE
class TransactionResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(min_length=1)
    amount: Amount
    transaction_type: TransactionType
    category: Category
    description: Description
    date: Date
    auto_filled: list[str] = Field(default_factory=list)



# PAGINATED TRANSACTION RESPONSE
class TransactionListResponse(BaseModel):
    items: list[TransactionResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    skip: int = Field(ge=0)



# TRANSACTION FILTERS
class TransactionFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transaction_type: TransactionType | None = None
    category: Category | None = None
    start_date: UpdateDate | None = None
    end_date: UpdateDate | None = None
    min_amount: float | None = Field(
        default=None,
        ge=0,
        le=100_000_000,
        allow_inf_nan=False,
    )
    max_amount: float | None = Field(
        default=None,
        ge=0,
        le=100_000_000,
        allow_inf_nan=False,
    )

    @model_validator(mode="after")
    def validate_filter_range(self):
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.start_date > self.end_date
        ):
            raise ValueError("start_date must not be after end_date.")

        if (
            self.min_amount is not None
            and self.max_amount is not None
            and self.min_amount > self.max_amount
        ):
            raise ValueError("min_amount must not exceed max_amount.")

        return self