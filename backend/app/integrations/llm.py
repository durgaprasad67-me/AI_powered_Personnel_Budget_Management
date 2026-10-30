from google import genai
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import SecretStr

from app.core.config import get_settings


class LLMNotConfiguredError(RuntimeError):
    """Raised when the Gemini API key is not configured."""


def get_gemini_client() -> genai.Client:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise LLMNotConfiguredError("GEMINI_API_KEY is missing from the environment.")
    return genai.Client(api_key=settings.gemini_api_key)


def get_chat_model() -> ChatGoogleGenerativeAI:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is missing from the environment.")
    return ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        google_api_key=SecretStr(settings.gemini_api_key),
        temperature=0.2,
    )


def get_embedding_model():
    settings = get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is missing from the environment.")
    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    return GoogleGenerativeAIEmbeddings(
        model=settings.gemini_embedding_model,
        api_key=SecretStr(settings.gemini_api_key),
    )
