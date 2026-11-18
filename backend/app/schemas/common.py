from pydantic import BaseModel


class MessageResponse(BaseModel):
    message: str


class HomeResponse(BaseModel):
    message: str
    status: str
    version: str


class HealthResponse(BaseModel):
    status: str
    database: str


class ImportResult(BaseModel):
    message: str
    filename: str
    total_records: int
    imported_records: int
    transactions: list[str]
