from datetime import date as Date
from typing import Annotated

from pydantic import AfterValidator, BeforeValidator, Field

from app.domain.dates import (
    check_date_range,
    check_plan_date,
    date_or_today,
    parse_date_text,
)
from app.domain.normalization import (
    clean_description,
    normalize_category,
    normalize_type,
    parse_amount,
    round_amount,
)
from app.domain.transaction_types import TransactionTypeName

Amount = Annotated[
    float,
    BeforeValidator(parse_amount),
    Field(gt=0, allow_inf_nan=False),
    AfterValidator(round_amount),
]
TransactionType = Annotated[
    TransactionTypeName,
    BeforeValidator(normalize_type),
]
Category = Annotated[
    str,
    BeforeValidator(normalize_category),
]
Description = Annotated[
    str,
    BeforeValidator(clean_description),
]
CreateDate = Annotated[
    Date,
    BeforeValidator(date_or_today),
    AfterValidator(check_date_range),
]
UpdateDate = Annotated[
    Date,
    BeforeValidator(parse_date_text),
    AfterValidator(check_date_range),
]
PlanDate = Annotated[
    Date,
    BeforeValidator(parse_date_text),
    AfterValidator(check_plan_date),
]
