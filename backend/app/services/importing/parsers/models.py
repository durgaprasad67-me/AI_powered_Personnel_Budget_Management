"""
Data models for unified file parsing across all supported formats.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParsedRow:
    row_number: int  # 1-based spreadsheet row number (header = 1, data starts at 2)
    raw_data: dict[str, Any]


@dataclass
class ParsedTable:
    filename: str
    file_type: str
    headers: list[str]
    rows: list[ParsedRow]
    sheet_name: str | None = None
    notes: list[str] = field(default_factory=list)
