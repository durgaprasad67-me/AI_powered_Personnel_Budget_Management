import os
from dotenv import load_dotenv
from google.genai import Client

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise RuntimeError("GEMINI_API_KEY is missing from the environment.")

client = Client(api_key=api_key)


async def generate_financial_insights(financial_data: dict) -> str:
    prompt = f"""
    You are FinSight AI, a personal finance assistant.

    Analyze the following financial summary:
    {financial_data}

    Provide:
    1. A summary of the user's financial situation.
    2. Important spending patterns.
    3. Potential areas to reduce expenses.
    4. Practical budgeting suggestions.

    Do not invent financial figures that are not provided.
    Clearly distinguish observations from suggestions.
    """

    response = await client.aio.models.generate_content(
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        contents=prompt,
    )

    return response.text or "No insights were generated."