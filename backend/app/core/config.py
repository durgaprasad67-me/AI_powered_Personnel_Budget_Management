from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    mongo_user: str | None = None
    mongo_password: str | None = None
    mongo_cluster: str | None = None
    database_name: str = "finsight_db"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_embedding_model: str = "gemini-embedding-001"
    chroma_persist_directory: str = "./chroma_db"
    chroma_collection_name: str = "finsight_knowledge"
    rag_max_chunks: int = 2000
    rag_top_k: int = 4
    rag_min_score: float = 0.60
    rag_chunk_size: int = 1000
    rag_chunk_overlap: int = 150

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
