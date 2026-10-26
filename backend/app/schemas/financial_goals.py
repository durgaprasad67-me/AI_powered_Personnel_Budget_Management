from datetime import date as Date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.common import Amount, UpdateDate

GoalStatus = Literal["active","completed","paused","cancelled",]


# CREATE FINANCIAL GOAL
class FinancialGoalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None,max_length=300,)
    target_amount: Amount
    current_amount: float = Field(
        default=0,
        ge=0,
        le=100_000_000,
        allow_inf_nan=False,
    )
    target_date: UpdateDate | None = None



# UPDATE FINANCIAL GOAL
class FinancialGoalUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None,min_length=1,max_length=100,)
    description: str | None = Field(default=None,max_length=300,)
    target_amount: Amount | None = None
    current_amount: float | None = Field(
        default=None,
        ge=0,
        le=100_000_000,
        allow_inf_nan=False,
    )
    target_date: UpdateDate | None = None
    status: GoalStatus | None = None



# FINANCIAL GOAL RESPONSE
class FinancialGoalResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(min_length=1)
    name: str
    description: str | None = None
    target_amount: Amount
    current_amount: float = Field(ge=0,le=100_000_000,allow_inf_nan=False,)
    target_date: Date | None = None
    status: GoalStatus = "active"



# FINANCIAL GOAL PROGRESS
class FinancialGoalProgress(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goal_id: str
    target_amount: Amount
    current_amount: float = Field(ge=0, allow_inf_nan=False,)
    remaining_amount: float = Field( allow_inf_nan=False,)
    percentage_completed: float = Field(ge=0,allow_inf_nan=False,)
    is_completed: bool