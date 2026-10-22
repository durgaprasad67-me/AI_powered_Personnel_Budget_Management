from datetime import date as  Date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class TransactionCreate(BaseModel):
    amount: float = Field(gt=0)
    transaction_type: Literal["income", "expense"]
    category: str = Field(min_length=1, max_length=50)
    description: str = Field(min_length=1, max_length=200)
    date: Date


class TransactionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: float | None = Field(default=None, gt=0)
    transaction_type: Literal["income", "expense"] | None = None
    category: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = Field(default=None, min_length=1, max_length=200)
    date: Date | None = None