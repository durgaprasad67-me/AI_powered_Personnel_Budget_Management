from datetime import date as Date, datetime, timedelta, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

IST = timezone(timedelta(hours=5, minutes=30))


def today_ist() -> Date:
    return datetime.now(IST).date()

def clean_spaces(value):
    # "  Lunch   at  home " -> "Lunch at home"
    return " ".join(value.split()) if isinstance(value, str) else value


def clean_lower(value):
    # "  FOOD " -> "food"
    return clean_spaces(value).lower() if isinstance(value, str) else value

def date_or_today(value):
    return today_ist() if value in (None, "") else value


TransactionType = Annotated[Literal["income", "expense"], BeforeValidator(clean_lower)]
Category = Annotated[str, BeforeValidator(clean_lower), Field(min_length=1, max_length=50)]
Description = Annotated[str, BeforeValidator(clean_spaces), Field(min_length=1, max_length=200)]
TransactionDate = Annotated[Date, BeforeValidator(date_or_today)]


class TransactionCreate(BaseModel):
    amount: float = Field(gt=0)
    transaction_type: TransactionType
    category: Category
    description: Description
    date: TransactionDate = Field(default_factory=today_ist)


class TransactionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: float | None = Field(default=None, gt=0)
    transaction_type: TransactionType | None = None
    category: Category | None = None
    description: Description | None = None
    date: Date | None = None