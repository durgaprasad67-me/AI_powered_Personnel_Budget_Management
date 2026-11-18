from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RAGHistoryMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class RAGQuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=3, max_length=1000)
    k: int = Field(default=4, ge=1, le=10)
    history: list[RAGHistoryMessage] = Field(default_factory=list, max_length=8)
    source_type: Literal["document", "transaction"] | None = None
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def validate_date_range(self):
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.start_date > self.end_date
        ):
            raise ValueError("start_date must not be after end_date.")
        return self


class RAGSourceChunk(BaseModel):
    id: str
    source: str
    page: int | None = None
    chunk_index: int
    snippet: str
    score: float
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)


class RAGDocumentSummary(BaseModel):
    doc_id: str
    source: str
    chunk_count: int = Field(ge=0)
    vector_index_status: str = "pending"


class RAGAnswerResponse(BaseModel):
    question: str
    answer: str
    sources: list[str] = Field(default_factory=list)
    source_chunks: list[RAGSourceChunk] = Field(default_factory=list)


class DocumentIndexResponse(BaseModel):
    doc_id: str
    filename: str
    chunks_created: int = Field(ge=0)
    message: str
