from pydantic import BaseModel, ConfigDict, Field


class RAGQuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=3, max_length=1000)
    k: int = Field(default=4, ge=1, le=10)


class RAGSourceChunk(BaseModel):
    source: str
    page: int | None = None
    chunk_index: int
    snippet: str
    score: float


class RAGDocumentSummary(BaseModel):
    doc_id: str
    source: str
    chunk_count: int = Field(ge=0)


class RAGAnswerResponse(BaseModel):
    question: str
    answer: str
    sources: list[str] = Field(default_factory=list)
    source_chunks: list[RAGSourceChunk] = Field(default_factory=list)


class DocumentIndexResponse(BaseModel):
    filename: str
    chunks_created: int = Field(ge=0)
    message: str
