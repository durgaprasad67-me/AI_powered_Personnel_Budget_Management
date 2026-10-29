from datetime import date as Date
from typing import Annotated

from pydantic import AfterValidator, BeforeValidator, Field

from app.domain.dates import check_date_range, date_or_today, parse_date_text
from app.domain.normalization import (
    MAX_AMOUNT,
    clean_lower,
    clean_spaces,
    normalize_type,
    parse_amount,
    round_amount,
)
from app.domain.transaction_types import TransactionTypeName


MAX_DESCRIPTION_LENGTH = 200
MAX_CATEGORY_LENGTH = 50

Amount = Annotated[
    float,
    BeforeValidator(parse_amount),
    Field(gt=0, le=MAX_AMOUNT, allow_inf_nan=False),
    AfterValidator(round_amount),
]
TransactionType = Annotated[
    TransactionTypeName,
    BeforeValidator(normalize_type),
]
Category = Annotated[
    str,
    BeforeValidator(clean_lower),
    Field(min_length=1, max_length=MAX_CATEGORY_LENGTH),
]
Description = Annotated[
    str,
    BeforeValidator(clean_spaces),
    Field(min_length=1, max_length=MAX_DESCRIPTION_LENGTH),
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
