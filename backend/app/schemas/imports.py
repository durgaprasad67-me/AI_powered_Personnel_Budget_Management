"""
Pydantic schemas for FinSight AI import validation, duplicate confirmation, and commit contracts.
"""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class ImportErrorItem(BaseModel):
    row: int | None = None
    column: str | None = None
    code: str
    message: str
    severity: str = "BLOCKING"
    sample_value: str | None = None


class GroupedErrorItem(BaseModel):
    code: str
    column: str = ""
    count: int
    rows: list[int] = Field(default_factory=list)
    total_rows_affected: int = 0
    message: str


class ImportSummary(BaseModel):
    total_rows: int = 0
    valid: int = 0
    invalid: int = 0
    duplicates: int = 0
    new: int = 0


class DuplicateSummary(BaseModel):
    count: int = 0
    ratio: float = 0.0
    sample: list[dict[str, Any]] = Field(default_factory=list)


class ImportResponse(BaseModel):
    status: Literal["rejected", "needs_confirmation", "ready", "imported"]
    code: str
    title: str
    message: str
    summary: ImportSummary
    errors: list[ImportErrorItem] = Field(default_factory=list)
    grouped_errors: list[GroupedErrorItem] = Field(default_factory=list)
    duplicates: DuplicateSummary = Field(default_factory=DuplicateSummary)
    actions: list[str] = Field(default_factory=list)
    import_token: str | None = None
    records: list[dict[str, Any]] = Field(default_factory=list)


class ImportCommitRequest(BaseModel):
    import_token: str
    duplicate_strategy: Literal["import_new_only", "import_all"] = "import_new_only"
    partial_ok: bool = False
