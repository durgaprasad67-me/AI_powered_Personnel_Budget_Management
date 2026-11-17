<<<<<<< HEAD
import os
from dotenv import load_dotenv

# Loads backend/.env when running from the backend directory.
load_dotenv()

MONGO_USER = os.getenv("MONGO_USER")
MONGO_PASSWORD = os.getenv("MONGO_PASSWORD")
MONGO_CLUSTER = os.getenv("MONGO_CLUSTER")
DATABASE_NAME = os.getenv("DATABASE_NAME", "finsight_db")
=======
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    mongo_user: str | None = None
    mongo_password: str | None = None
    mongo_cluster: str | None = None
    database_name: str = "finsight_db"
    gemini_api_keys: Annotated[list[SecretStr], NoDecode] = Field(
        default_factory=list,
        repr=False,
    )
    gemini_api_key: SecretStr | None = Field(default=None, repr=False)
    # Numbered aliases are kept for existing deployments that already use
    # GEMINI_API_KEY_1, GEMINI_API_KEY_2, and GEMINI_API_KEY_3.
    gemini_api_key_1: SecretStr | None = Field(default=None, repr=False)
    gemini_api_key_2: SecretStr | None = Field(default=None, repr=False)
    gemini_api_key_3: SecretStr | None = Field(default=None, repr=False)
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_embedding_dim: int = Field(default=768, ge=128, le=3072)
    gemini_embedding_batch_size: int = Field(default=100, ge=1, le=100)
    gemini_request_timeout_seconds: float = Field(default=30.0, gt=0)
    gemini_max_output_tokens: int = Field(default=1024, ge=1, le=65536)
    chroma_persist_directory: str = "./chroma_db"
    chroma_collection_name: str = "finsight_knowledge"
    rag_max_chunks: int = 2000
    rag_top_k: int = 4
    rag_min_score: float = Field(default=0.60, ge=0.0, le=1.0)
    rag_chunk_size: int = 1000
    rag_chunk_overlap: int = 150
    rag_context_max_chars: int = Field(default=12000, ge=1000, le=100000)
    rag_debug_context: bool = False

    # Transaction validation limits & thresholds (authoritative central config)
    max_inflow_amount: float = Field(default=100_000_000.0, gt=0)
    max_outflow_amount_without_budget: float = Field(default=100_000_000.0, gt=0)
    transaction_date_floor_years: int = Field(default=10, ge=1, le=100)
    category_min_length: int = Field(default=2, ge=1)
    category_max_length: int = Field(default=30, ge=2)
    description_max_length: int = Field(default=200, ge=1)
    duplicate_window_seconds: float = Field(default=5.0, ge=0.5)

    @field_validator("gemini_api_keys", mode="before")
    @classmethod
    def parse_gemini_api_keys(cls, value):
        if value is None:
            return []
        candidates = value.split(",") if isinstance(value, str) else value
        if not isinstance(candidates, (list, tuple, set)):
            raise ValueError("GEMINI_API_KEYS must be a comma-separated string.")

        unique: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            if isinstance(candidate, SecretStr):
                candidate = candidate.get_secret_value()
            key = str(candidate).strip()
            if key and key not in seen:
                seen.add(key)
                unique.append(key)
        return unique

    @field_validator("gemini_api_key", mode="before")
    @classmethod
    def strip_legacy_gemini_key(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    def configured_gemini_keys(self) -> list[SecretStr]:
        numbered = [
            key
            for key in (
                self.gemini_api_key_1,
                self.gemini_api_key_2,
                self.gemini_api_key_3,
            )
            if key is not None
        ]
        candidates = numbered or list(self.gemini_api_keys)
        if not candidates and self.gemini_api_key:
            candidates = [self.gemini_api_key]

        unique: list[SecretStr] = []
        seen: set[str] = set()
        for candidate in candidates:
            value = candidate.get_secret_value().strip()
            if value and value not in seen:
                seen.add(value)
                unique.append(SecretStr(value))
        return unique

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
>>>>>>> 3d11468 (updated the some backend and frontend files)
