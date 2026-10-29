from pydantic import BaseModel, Field, ConfigDict


class RAGQuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=3, max_length=1000)
    k: int = Field(default=4, ge=1, le=10)


class RAGAnswerResponse(BaseModel):
    question: str
    answer: str
    sources: list[str] = Field(default_factory=list)


class DocumentIndexResponse(BaseModel):
    filename: str
    chunks_created: int = Field(ge=0)
    message: str
