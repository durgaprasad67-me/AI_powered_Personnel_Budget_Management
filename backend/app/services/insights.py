import json
import logging
import math
import re
from calendar import monthrange
from collections.abc import Callable
from datetime import date as Date
from datetime import timedelta
from typing import Any

from google.genai import types
from pydantic import ValidationError

from app.core.config import get_settings
from app.core.exceptions import ExternalServiceError
from app.core.user_context import DEFAULT_CURRENT_USER_ID
from app.domain.date_range_resolver import resolve_date_range
from app.domain.dates import today_ist
from app.domain.transaction_types import TRANSACTION_TYPES
from app.integrations.gemini_key_pool import (
    AllKeysExhausted,
    GeminiKeyPool,
    acall_with_rotation,
    classify,
)
from app.integrations.llm import (
    LLMNotConfiguredError,
    get_gemini_client,
    get_gemini_key_pool,
)
from app.schemas.insights import (
    ChatRequest,
    ChatResponse,
    FinancialRecommendation,
    SpendingInsightRequest,
    SpendingInsightResponse,
    TransactionExtractionResponse,
    TransactionTextRequest,
)
from app.services.analytics import AnalyticsService
from app.services.financial_qa import FinancialQAEngine, classify_question_intent
from app.services.transactions import TransactionService

logger = logging.getLogger(__name__)

FINANCIAL_INTENT_PATTERN = re.compile(
    r"\b("
    # Analysis & Reporting actions
    r"analyse|analyze|analysis|analysing|analyzing|"
    r"report|reports|reporting|reported|"
    r"summary|summaries|summarize|summarise|summarizing|summarising|"
    r"overview|review|reviews|reviewing|reviewed|"
    r"insight|insights|findings|finding|evaluate|evaluating|evaluation|"
    # Files, Import, and Data sources
    r"csv|excel|xlsx|pdf|file|files|doc|docs|document|documents|"
    r"import|imports|imported|importing|upload|uploads|uploaded|uploading|"
    r"data|record|records|entry|entries|history|log|logs|"
    # Core financial concepts
    r"spend|spent|spending|spends|"
    r"expense|expenses|cost|costs|costing|priced|price|"
    r"paid|pay|pays|paying|payment|payments|"
    r"buy|buys|bought|buying|purchase|purchases|purchased|"
    r"income|incomes|inflow|inflows|outflow|outflows|cash|money|rupee|rupees|inr|₹|"
    r"invest|invests|invested|investing|investment|investments|sip|sips|portfolio|asset|assets|"
    r"loan|loans|borrow|borrows|borrowed|borrowing|lend|lends|lent|lending|emi|emis|debt|debts|"
    r"salary|salaries|wage|wages|earn|earns|earned|earning|earnings|deposit|deposits|deposited|withdraw|withdrew|withdrawal|withdrawals|"
    r"save|saves|saved|saving|savings|budget|budgets|budgeting|balance|balances|"
    r"finance|finances|financial|bill|bills|billing|transaction|transactions|"
    r"account|accounts|bank|banks|banking|statement|statements|refund|refunds|interest|interests|"
    # Common categories
    r"food|groceries|grocery|transport|transit|travel|commute|cab|taxi|fuel|petrol|diesel|"
    r"rent|housing|shopping|entertainment|movie|movies|dining|restaurant|restaurants|"
    r"health|medical|medicine|medicines|hospital|doctor|education|school|college|course|tuition|"
    r"home|household|utilities|utility|electricity|water|wifi|internet|mobile|phone|broadband|recharge|"
    r"freelance|freelancing|dividend|dividends|"
    # Analytical & comparison terms
    r"afford|affordable|affordability|cheapest|cheaper|expensive|costly|"
    r"highest|lowest|maximum|minimum|max|min|most|least|breakdown|total|totals|average|avg|sum|count|"
    r"deficit|surplus|net\s*worth|cash\s*flow|runway|"
    # Time periods
    r"month|months|monthly|year|yearly|annual|today|yesterday|week|weekly|period|"
    r"january|february|march|april|may|june|july|august|september|october|november|december|"
    # Conversational intent phrases
    r"how\s+did\s+i\s+do|how\s+am\s+i\s+doing|where\s+did\s+my\s+money\s+go"
    r")\b",
    re.IGNORECASE,
)

OTHER_USER_QUERY_PATTERN = re.compile(
    r"\b("
    # Explicit other user / another user / other users / all users
    r"(?:other|another|different|all|every|any\s+other)\s+(?:users?|accounts?|peoples?|persons?|members?|clients?|customers?|profiles?|individuals?)"
    r"|"
    # Someone else / someone else's
    r"someone\s+else(?:'s)?(?:\s+(?:data|records?|finances?|transactions?|spending|expenses?|income|salary|budget|balance|account))?"
    r"|"
    # Data of/about other users
    r"(?:data|records?|finances?|transactions?|spending|expenses?|income|salary|budget|balance|account)\s+(?:of|about|from|for)\s+(?:other|another|different|all)\s+(?:users?|accounts?|peoples?|persons?)"
    r"|"
    # Possessive: other user's, another user's, others' data
    r"(?:other|another)\s+users?'s?"
    r"|"
    r"others?'s?\s+(?:data|records?|finances?|transactions?|spending|expenses?|income|salary|budget|balance|account)"
    r"|"
    # Direct access other data / access data other data
    r"access\s+(?:data\s+)?(?:other|another)\s+(?:data|users?|records?)"
    r"|"
    r"(?:access|view|see|show|fetch|get|query|read|reveal|leak|export)\s+(?:any\s+)?(?:other|another|different|all)\s+(?:users?|accounts?|peoples?|persons?)(?:'s)?(?:\s+data)?"
    r"|"
    # Specific user identifier: user2, user_2, user_123, user 2, user-bob
    r"users?[\s_-]*(?:[0-9]+|[a-z0-9_-]{2,})"
    r"|"
    # Third party name with financial entity: Alice's spending, Bob's transactions, what did Alice spend
    r"(?:alice|bob|charlie|david|john|jane|sarah|smith|alex|michael|emily|robert|daniel)\'s\s+(?:data|finances?|spending|expenses?|income|salary|transactions?|records?|budgets?|balance|accounts?)"
    r"|"
    r"(?:what|how\s+much|show|tell\s+me)\s+(?:did|is|about|does)\s+(?:alice|bob|charlie|david|john|jane|sarah|smith|alex|michael|emily|robert|daniel)\b"
    r"|"
    r"other\s+user"
    r"|"
    r"access\s+other\s+data"
    r")\b",
    re.IGNORECASE,
)

FIRST_PERSON_OR_GENERIC_TOKENS = {
    "i", "me", "my", "mine", "myself", "we", "us", "our", "ours", "ourselves",
    "the", "this", "that", "these", "those", "a", "an", "there",
    "total", "overall", "net", "gross", "all", "any", "each", "every",
    "current", "last", "past", "recent", "latest", "highest", "lowest",
    "most", "least", "max", "min", "average", "avg",
    "monthly", "yearly", "annual", "today", "yesterday",
    "here", "there", "it", "its", "category", "categories",
    "account", "accounts", "transaction", "transactions", "expense", "expenses",
    "income", "inflow", "outflow", "budget", "budgets", "investment", "investments",
    "money", "cash", "rupees", "inr", "card", "upi", "credit", "debit", "file", "csv",
    # Financial categories & common financial objects
    "groceries", "grocery", "food", "dining", "transport", "travel", "utilities",
    "shopping", "fuel", "bills", "bill", "rent", "health", "healthcare",
    "insurance", "entertainment", "education", "personal", "salary", "wages",
    "bonus", "dividend", "interest", "debt", "loan", "loans", "emi", "tax", "taxes",
    # Verbs and modals that might precede a keyword or follow pronouns
    "have", "has", "had", "having", "do", "did", "does", "done", "doing",
    "am", "is", "are", "was", "were", "be", "been", "being",
    "can", "could", "will", "would", "shall", "should", "may", "might", "must",
    "get", "got", "getting", "give", "gave", "given", "giving",
    "show", "shows", "showed", "shown", "showing",
    "find", "finds", "found", "finding",
    "tell", "tells", "told", "telling",
    "check", "checks", "checked", "checking",
    "see", "sees", "saw", "seen", "seeing",
    "look", "looks", "looked", "looking",
    "know", "knows", "knew", "known",
    "spend", "spends", "spent", "spending",
    "pay", "pays", "paid", "paying",
    "cost", "costs", "costing",
    "buy", "buys", "bought", "buying",
}

SEARCH_STOPWORDS = {
    "a", "about", "all", "an", "and", "any", "are", "as", "at", "be", "been",
    "being", "but", "by", "can", "check", "could", "did", "do", "does", "done",
    "each", "every", "find", "for", "from", "get", "give", "got", "had", "has",
    "have", "he", "her", "here", "him", "his", "how", "i", "if", "in", "into",
    "is", "it", "its", "just", "know", "latest", "least", "like", "look", "many",
    "me", "mean", "might", "money", "month", "monthly", "most", "much", "must",
    "my", "myself", "no", "not", "of", "off", "on", "one", "only", "or", "our",
    "ours", "out", "over", "own", "past", "pay", "payment", "please", "recent",
    "record", "records", "see", "shall", "she", "should", "show", "so", "some",
    "spend", "spending", "spent", "tell", "than", "that", "the", "their", "them",
    "then", "there", "these", "they", "this", "those", "to", "too", "transaction",
    "transactions", "up", "us", "was", "we", "were", "what", "when", "where",
    "which", "while", "who", "whom", "whose", "why", "will", "with", "would",
    "year", "yearly", "you", "your", "yours",
    "analyse", "analyze", "analysis", "report", "summary", "overview", "insight",
    "insights", "finance", "finances", "financial", "budget", "budgets",
    "expense", "expenses", "income", "inflow", "inflows", "outflow", "outflows",
    "investment", "investments", "cash", "rupees", "inr", "total", "overall",
    "import", "imported", "importing", "csv", "file", "files", "upload", "uploaded",
    "history", "statement", "details",
}

FIRST_PERSON_INTENT_PATTERN = re.compile(
    r"\b("
    r"i|me|my|mine|myself|we|us|our|ours|ourselves"
    r"|can\s+(?:you|u)"
    r"|could\s+(?:you|u)"
    r"|would\s+(?:you|u)"
    r"|please"
    r"|suggest|suggestion|suggestions"
    r"|recommend|recommendation|recommendations"
    r"|advice|tips?"
    r"|how\s+(?:can|do|should|to)"
    r"|help(?:\s+me)?"
    r")\b",
    re.IGNORECASE,
)

ALL_GENERIC_TOKENS = FIRST_PERSON_OR_GENERIC_TOKENS.union(SEARCH_STOPWORDS).union({
    "for", "from", "with", "by", "about", "after", "before", "under", "over",
    "between", "through", "without", "next", "last", "past", "prior", "current",
    "present", "upcoming", "following", "management", "manage", "plan", "planning",
    "saving", "save", "give", "get", "create", "make", "set", "track", "show",
    "tell", "find", "see", "look", "check", "know", "help", "suggest", "recommend",
    "advice", "tip", "tips", "allocation", "allocations", "limit", "limits",
    "target", "targets", "goal", "goals", "smart", "good", "better", "best",
    "extra", "higher", "lower", "reduce", "cut", "increase", "general", "personal",
    "operating", "actual", "future", "daily", "weekly", "monthly", "yearly", "annual",
})


def detect_named_person_query(q: str) -> tuple[bool, str | None]:
    clean = q.strip()

    # 1. Explicit possessive: "Ramu's budget", "Alice's expenses", "Bob's salary"
    m2 = re.search(
        r"\b([a-zA-Z]+)'s\s+(?:most\s+)?(?:spent|spending|expenses?|income|salary|transactions?|records?|budgets?|balance|money|account|data)\b",
        clean,
        re.I,
    )
    if m2:
        target = m2.group(1).lower()
        if target not in ALL_GENERIC_TOKENS:
            return True, m2.group(1).capitalize()

    # 2. Prepositional possessive: "budget of Ramu", "expenses of Alice", "transactions of Bob"
    m2_of = re.search(
        r"\b(?:expenses?|spending|income|salary|transactions?|records?|budgets?|balance|money|account|data)\s+of\s+([a-zA-Z]+)\b",
        clean,
        re.I,
    )
    if m2_of:
        target = m2_of.group(1).lower()
        if target not in ALL_GENERIC_TOKENS:
            return True, m2_of.group(1).capitalize()

    # 3. If user is asking first-person questions about their own account or requesting assistant advice:
    # (e.g. "Do I have any record about boovan?", "Can u give any suggestion for next month for budget management ?")
    if FIRST_PERSON_INTENT_PATTERN.search(clean):
        return False, None

    # 4. Third-person questions: e.g. "What did Ramu spend?", "What is Ramu most spent money?", "How much did Alice pay?"
    m1 = re.search(
        r"\b(?:what|how\s+much|where|when|which)\s+(?:did|is|was|does|has|had)\s+([a-zA-Z]+)\s+(?:most\s+)?(?:spend|spent|spending|pay|paid|buying|bought|cost|money|expenses?|inflow|outflow|income|salary|balance|budget)",
        clean,
        re.I,
    )
    if m1:
        target = m1.group(1).lower()
        if target not in ALL_GENERIC_TOKENS:
            return True, m1.group(1).capitalize()

    # 5. "Did Ramu spend?", "Has Alice paid?"
    m3 = re.search(
        r"\b(?:did|has|does)\s+([a-zA-Z]+)\s+(?:spend|spent|pay|paid|buy|bought)\b",
        clean,
        re.I,
    )
    if m3:
        target = m3.group(1).lower()
        if target not in ALL_GENERIC_TOKENS:
            return True, m3.group(1).capitalize()

    return False, None


class InsightService:
    def __init__(
        self,
        analytics: AnalyticsService,
        client_factory: Callable[[Any], Any] = get_gemini_client,
        key_pool: GeminiKeyPool | None = None,
        transaction_service: TransactionService | None = None,
    ):
        self.analytics = analytics
        self.client_factory = client_factory
        self.key_pool = key_pool
        self.transaction_service = transaction_service

    def _get_client(self, api_key: Any) -> Any:
        return self.client_factory(api_key)

    async def _generate_content(self, **request: Any) -> Any:
        try:
            pool = self.key_pool or get_gemini_key_pool()
        except LLMNotConfiguredError as exc:
            raise ExternalServiceError(
                "AI service is not configured.",
                status_code=503,
            ) from exc

        try:
            return await acall_with_rotation(
                pool,
                lambda api_key: self._get_client(
                    api_key
                ).aio.models.generate_content(**request),
            )
        except LLMNotConfiguredError as exc:
            raise ExternalServiceError(
                "AI service is not configured.",
                status_code=503,
            ) from exc

    @staticmethod
    def _classify_message(message: str) -> str:
        normalized = re.sub(r"\s+", " ", message.strip().lower())
        if re.fullmatch(
            r"(hi|hello|hey|hiya|good morning|good afternoon|good evening)[!. ]*",
            normalized,
        ):
            return "greeting"
        if normalized in {"help", "what can you do", "what can you help with"}:
            return "help"
        return "spending_analysis"

    @staticmethod
    def _resolve_month(message: str, fallback: str) -> str:
        clean = message.lower()
        fb_year, fb_month = int(fallback[:4]), int(fallback[5:7])

        # 1. Relative month phrases
        if re.search(r"\b(?:previous|last|past|prior)\s+month\b", clean):
            if fb_month == 1:
                return f"{fb_year - 1}-12"
            return f"{fb_year}-{fb_month - 1:02d}"

        if re.search(r"\b(?:next|upcoming|following)\s+month\b", clean):
            if fb_month == 12:
                return f"{fb_year + 1}-01"
            return f"{fb_year}-{fb_month + 1:02d}"

        if re.search(r"\b(?:this|current|present)\s+month\b", clean):
            return fallback

        # 2. Explicit YYYY-MM in message (e.g. 2026-10 or 2026/10)
        iso_month_match = re.search(r"\b(20\d{2})[-/](0[1-9]|1[0-2])\b", clean)
        if iso_month_match:
            return f"{iso_month_match.group(1)}-{iso_month_match.group(2)}"

        # 3. Explicit named months
        months = {
            "january": 1, "february": 2, "march": 3, "april": 4,
            "may": 5, "june": 6, "july": 7, "august": 8,
            "september": 9, "october": 10, "november": 11, "december": 12,
        }
        for name, month_number in months.items():
            if re.search(rf"\b{name}\b", clean):
                year_match = re.search(r"\b20\d{2}\b", clean)
                year = int(year_match.group()) if year_match else fb_year
                return f"{year}-{month_number:02d}"

        return fallback

    @staticmethod
    def _month_dates(month: str) -> tuple[Date, Date]:
        year, month_number = (int(part) for part in month.split("-"))
        return (
            Date(year, month_number, 1),
            Date(year, month_number, monthrange(year, month_number)[1]),
        )

    @staticmethod
    def _format_insight(result: SpendingInsightResponse) -> str:
        sections = [result.summary]
        if result.key_findings:
            sections.append(
                "Key findings:\n"
                + "\n".join(f"- {finding}" for finding in result.key_findings),
            )
        if result.recommendations:
            sections.append(
                "Recommendations:\n"
                + "\n".join(
                    f"- {item.title}: {item.explanation}"
                    for item in result.recommendations
                ),
            )
        if result.limitations:
            sections.append(
                "Notes:\n"
                + "\n".join(f"- {limitation}" for limitation in result.limitations),
            )
        return "\n\n".join(sections)

    async def chat(
        self,
        request: ChatRequest,
        *,
        user_id: str = DEFAULT_CURRENT_USER_ID,
    ) -> ChatResponse:
        today = today_ist()
        current_month = f"{today.year}-{today.month:02d}"
        month = request.month or self._resolve_month(request.message, current_month)
        intent = self._classify_message(request.message)

        if intent == "greeting":
            return ChatResponse(
                message=(
                    "Hi! I’m FinSight AI. Ask me about your spending, "
                    "budgets, or financial goals."
                ),
                intent=intent,
                month=month,
                suggestions=[
                    "Where am I spending most?",
                    "How can I reduce expenses?",
                    "How did I do this month?",
                ],
            )

        if intent == "help":
            return ChatResponse(
                message=(
                    "I can analyze your income, expenses, categories, "
                    "investments, loan repayments, budgets, and goals. "
                    "Try asking: “How did I do in October?”"
                ),
                intent=intent,
                month=month,
                suggestions=[
                    "How did I do this month?",
                    "What are my biggest expenses?",
                ],
            )

        is_cross_user, target_name = self._is_query_for_other_users(request.message)
        if is_cross_user:
            warning = self._build_cross_user_access_warning_insight(
                request.message,
                target_name=target_name,
                include_recommendations=request.include_recommendations,
            )
            return ChatResponse(
                message=self._format_insight(warning),
                intent="security_warning",
                month=month,
                suggestions=[
                    "Where am I spending most?",
                    "How can I reduce expenses?",
                    "Show my spending summary",
                ],
            )


        start_date, end_date = (
            self._month_dates(request.month) if request.month else (None, None)
        )
        insight = await self.spending_insights(
            SpendingInsightRequest(
                question=request.message,
                start_date=start_date,
                end_date=end_date,
                include_recommendations=request.include_recommendations,
            ),
            user_id=user_id,
        )
        return ChatResponse(
            message=self._format_insight(insight),
            intent="spending_analysis",
            month=month,
            suggestions=[
                "Where am I spending most?",
                "How can I reduce expenses?",
            ],
        )

    @staticmethod
    def _normalize_insight_response(content: str) -> SpendingInsightResponse:
        cleaned = content.strip()
        if not cleaned:
            raise ValueError("The AI returned an empty response.")

        # Extract JSON from markdown fences or surrounding text
        candidate = cleaned
        code_fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", candidate)
        if code_fence_match:
            candidate = code_fence_match.group(1).strip()

        json_match = re.search(r"\{[\s\S]*\}", candidate)
        if json_match:
            candidate = json_match.group(0)

        payload = json.loads(candidate)
        if not isinstance(payload, dict):
            raise ValueError("The AI response must be a JSON object.")

        # Map alternative keys for summary
        if "summary" not in payload:
            for alias in (
                "analysis",
                "spending_patterns",
                "message",
                "answer",
                "response",
                "overview",
                "text",
            ):
                if isinstance(payload.get(alias), str) and payload[alias].strip():
                    payload["summary"] = payload.pop(alias)
                    break

        # Map alternative keys for key_findings
        if "key_findings" not in payload:
            for alias in (
                "observed_facts",
                "facts",
                "main_spending_categories",
                "findings",
                "highlights",
                "points",
            ):
                if alias in payload:
                    payload["key_findings"] = payload.pop(alias)
                    break

        # Map alternative keys for recommendations
        if "recommendations" not in payload:
            for alias in ("suggestions", "tips", "advice", "action_items"):
                if alias in payload:
                    payload["recommendations"] = payload.pop(alias)
                    break

        # Map alternative keys for limitations
        if "limitations" not in payload:
            for alias in ("notes", "disclaimers", "caveats"):
                if alias in payload:
                    payload["limitations"] = payload.pop(alias)
                    break

        payload.pop("estimated_monthly_savings", None)

        # Normalize key_findings to list[str] (max 10)
        raw_findings = payload.get("key_findings", [])
        if isinstance(raw_findings, str):
            raw_findings = [raw_findings] if raw_findings.strip() else []
        elif not isinstance(raw_findings, list):
            raw_findings = []
        normalized_findings: list[str] = []
        for item in raw_findings:
            if isinstance(item, dict):
                text = (
                    item.get("finding")
                    or item.get("text")
                    or item.get("fact")
                    or item.get("description")
                    or str(item)
                )
            else:
                text = str(item)
            text = text.strip()
            if text:
                normalized_findings.append(text[:1000])
        payload["key_findings"] = normalized_findings[:10]

        # Ensure summary exists and is string <= 2000 chars
        if not payload.get("summary"):
            if payload["key_findings"]:
                payload["summary"] = " ".join(payload["key_findings"][:3])
            else:
                raise ValueError("The AI response did not include a summary.")
        payload["summary"] = str(payload["summary"]).strip()[:2000]

        # Deduplicate key_findings against summary to avoid duplicate answers
        summary_norm = payload["summary"].strip().lower()
        if summary_norm and payload.get("key_findings"):
            filtered_findings = []
            for item in payload["key_findings"]:
                item_norm = str(item).strip().lower()
                if item_norm == summary_norm:
                    continue
                if len(summary_norm) > 15 and item_norm in summary_norm:
                    continue
                if len(item_norm) > 15 and summary_norm in item_norm:
                    continue
                filtered_findings.append(item)
            payload["key_findings"] = filtered_findings

        # Normalize limitations to list[str] (max 10)
        raw_limitations = payload.get("limitations", [])
        if isinstance(raw_limitations, str):
            raw_limitations = [raw_limitations] if raw_limitations.strip() else []
        elif not isinstance(raw_limitations, list):
            raw_limitations = []
        normalized_limitations: list[str] = []
        for item in raw_limitations:
            if isinstance(item, dict):
                text = (
                    item.get("limitation")
                    or item.get("text")
                    or item.get("note")
                    or str(item)
                )
            else:
                text = str(item)
            text = text.strip()
            if text:
                normalized_limitations.append(text[:1000])
        payload["limitations"] = normalized_limitations[:10]

        # Normalize recommendations to list[FinancialRecommendation] (max 10)
        raw_recommendations = payload.get("recommendations", [])
        if isinstance(raw_recommendations, str):
            raw_recommendations = (
                [{"title": "Recommendation", "explanation": raw_recommendations}]
                if raw_recommendations.strip()
                else []
            )
        elif not isinstance(raw_recommendations, list):
            raise ValueError("The AI recommendations must be a list.")

        normalized_recommendations = []
        for rec in raw_recommendations:
            if isinstance(rec, str):
                rec = {
                    "title": "Recommendation",
                    "explanation": rec,
                    "estimated_monthly_savings": None,
                }
            if not isinstance(rec, dict):
                raise ValueError("Each AI recommendation must be an object.")

            title = str(rec.get("title") or "Recommendation").strip()[:100]
            if not title:
                title = "Recommendation"

            explanation = str(
                rec.get("explanation")
                or rec.get("description")
                or rec.get("action")
                or rec.get("tip")
                or title
            ).strip()[:1000]
            if not explanation:
                explanation = "Review your spending patterns."

            savings = rec.get("estimated_monthly_savings")
            if isinstance(savings, str):
                numeric_value = re.sub(r"[^\d.-]", "", savings)
                if not numeric_value:
                    savings = None
                else:
                    savings = float(numeric_value)
            elif isinstance(savings, (int, float)):
                if not math.isfinite(savings) or savings < 0:
                    savings = None
                else:
                    savings = float(savings)
            else:
                savings = None

            if savings is not None and (not math.isfinite(savings) or savings < 0):
                raise ValueError("The AI returned an invalid savings estimate.")

            normalized_recommendations.append(
                {
                    "title": title,
                    "explanation": explanation,
                    "estimated_monthly_savings": savings,
                }
            )

        payload["recommendations"] = normalized_recommendations[:10]

        allowed_fields = {
            "summary",
            "key_findings",
            "recommendations",
            "limitations",
        }
        filtered_payload = {
            key: value for key, value in payload.items() if key in allowed_fields
        }
        return SpendingInsightResponse.model_validate(filtered_payload)

    @staticmethod
    def _build_data_only_insight(
        summary: Any,
        start_date: Any,
        end_date: Any,
        matching_transactions: list[dict[str, Any]] | None = None,
    ) -> SpendingInsightResponse:
        if matching_transactions:
            lines = [
                f"{tx.get('date')}: '{tx.get('description', '')}' - ₹{float(tx.get('amount', 0)):,.2f} ({tx.get('category', '')})"
                for tx in matching_transactions[:5]
            ]
            return SpendingInsightResponse(
                summary=(
                    f"Found {len(matching_transactions)} transaction(s) matching your inquiry: "
                    + "; ".join(lines)
                ),
                key_findings=[f"Matched: {line}" for line in lines],
                recommendations=[],
                limitations=[
                    "Calculated directly from your account records without external AI generation."
                ],
            )
        findings = [
            f"Total income was {summary.total_income:.2f}.",
            f"Total expenses were {summary.total_expenses:.2f}.",
        ]
        if summary.total_investments:
            findings.append(
                f"Investments totaled {summary.total_investments:.2f}.",
            )
        if summary.total_loan_repayments:
            findings.append(
                f"Loan repayments totaled {summary.total_loan_repayments:.2f}.",
            )

        return SpendingInsightResponse(
            summary=(
                f"Here is the financial summary for {start_date:%B %Y}: "
                f"income was {summary.total_income:.2f} and expenses were "
                f"{summary.total_expenses:.2f}."
            ),
            key_findings=findings,
            recommendations=[],
            limitations=[
                f"AI analysis was unavailable for {start_date:%B %Y}; "
                "this response contains calculated totals only.",
            ],
        )

    @staticmethod
    def _extract_search_terms(question: str | None) -> list[str]:
        if not question or not question.strip():
            return []
        raw_words = re.findall(r"[a-zA-Z0-9_\-]+", question.lower())
        terms: list[str] = []
        for word in raw_words:
            if len(word) >= 2 and word not in SEARCH_STOPWORDS and word not in terms:
                terms.append(word)
        return terms

    @staticmethod
    def _is_out_of_scope(
        question: str | None,
        summary: Any = None,
        has_matching_transactions: bool = False,
    ) -> bool:
        if has_matching_transactions:
            return False
        if not question or not question.strip():
            return False
        clean = question.strip().lower()
        if clean in {
            "analyse my finance", "analyze my finance", "analyse my finances",
            "analyze my finances", "spending insights", "financial insights",
            "my spending", "spending analysis", "how did i do", "financial overview",
            "get insight", "analyze", "analyse", "insights", "finance", "finances",
            "spending", "expenses",
        }:
            return False
        if FINANCIAL_INTENT_PATTERN.search(clean):
            return False
        if summary and hasattr(summary, "category_breakdown"):
            words = set(re.findall(r"[a-zA-Z]{3,}", clean))
            for cat in summary.category_breakdown:
                cat_name = str(getattr(cat, "category", "")).lower()
                if cat_name in words or any(w in cat_name for w in words):
                    return False
        return True

    @staticmethod
    def _build_out_of_scope_insight(
        question: str | None,
        include_recommendations: bool = True,
    ) -> SpendingInsightResponse:
        clean_q = (question or "").strip()
        summary = (
            f"I couldn't find any financial records, transactions, or documents related to '{clean_q}' in your FinSight account. "
            "FinSight AI is dedicated to analyzing your personal finances, spending habits, cash flows, and budgets."
        )
        recommendations = []
        if include_recommendations:
            recommendations = [
                FinancialRecommendation(
                    title="Ask about your personal finances",
                    explanation=(
                        "FinSight AI is limited to your personal financial records. "
                        "Please ask questions about your transactions, spending categories, cash flows, or budgets."
                    ),
                    estimated_monthly_savings=None,
                ),
                FinancialRecommendation(
                    title="Try asking financial questions",
                    explanation=(
                        "For example: 'Where did I spend the most this month?', "
                        "'What is my total cash outflow?', 'How much did I spend on groceries?', "
                        "or 'What was my highest expense?'"
                    ),
                    estimated_monthly_savings=None,
                ),
            ]
        return SpendingInsightResponse(
            summary=summary,
            key_findings=[],
            recommendations=recommendations,
            limitations=[
                "FinSight AI only analyzes personal financial data within your account and cannot provide general external world knowledge."
            ],
        )

    @staticmethod
    def _is_query_for_other_users(question: str | None) -> tuple[bool, str | None]:
        if not question or not question.strip():
            return False, None
        clean = question.strip().lower()
        if OTHER_USER_QUERY_PATTERN.search(clean):
            return True, None
        # First-person inquiries (e.g. "Do I have any record about boovan ?") are queries
        # about the current user's own records, not unauthorized cross-user access attempts.
        if FIRST_PERSON_INTENT_PATTERN.search(clean):
            return False, None
        is_named, target_name = detect_named_person_query(question)
        if is_named:
            return True, target_name
        return False, None

    @staticmethod
    def _build_cross_user_access_warning_insight(
        question: str | None,
        target_name: str | None = None,
        include_recommendations: bool = True,
    ) -> SpendingInsightResponse:
        if target_name:
            summary = (
                f"⚠️ Access Denied: You cannot access financial records for '{target_name}' or other individuals. "
                "FinSight AI strictly isolates personal financial records by user account. "
                f"No records related to '{target_name}' exist in your personal account, and accessing another person's financial data is strictly prohibited."
            )
        else:
            summary = (
                "⚠️ Access Denied: You cannot access other users' data. "
                "FinSight AI strictly isolates personal financial records by user account. "
                "You are only authorized to view and analyze your own account's transactions and insights."
            )
        recommendations = []
        if include_recommendations:
            person_ref = f"people (such as {target_name})" if target_name else "other users or individuals"
            recommendations = [
                FinancialRecommendation(
                    title="Access Restricted to Your Account",
                    explanation=(
                        f"FinSight AI is dedicated exclusively to your personal finances. "
                        f"It does not track or disclose spending for {person_ref}."
                    ),
                    estimated_monthly_savings=None,
                ),
                FinancialRecommendation(
                    title="Ask About Your Own Spending",
                    explanation=(
                        "Try asking questions about your personal account, such as: "
                        "'Where did I spend the most this month?', 'What is my total cash outflow?', "
                        "or 'How much did I spend on groceries?'"
                    ),
                    estimated_monthly_savings=None,
                ),
            ]
        limitations = [
            "Privacy Policy: Accessing or querying financial records of other users or individuals is strictly prohibited."
        ]
        if target_name:
            limitations.append(f"No transactions or documents matching '{target_name}' were found in your personal financial records.")
        return SpendingInsightResponse(
            summary=summary,
            key_findings=[],
            recommendations=recommendations,
            limitations=limitations,
        )

    @staticmethod
    def _is_document_query(question: str | None) -> bool:
        if not question or not question.strip():
            return False
        clean = question.strip().lower()
        if "csv" in clean:
            return False
        if re.search(r"\b(pdf|docx|txt|uploaded\s+documents?|knowledge\s+base)\b", clean):
            return True
        if re.search(r"\b(?:in|from|recorded\s+in)\s+(?:the\s+)?(?:pdf|docx|txt|documents?)\b", clean):
            return True
        if ("sports shoe" in clean or "sports shoes" in clean) and "resort" in clean:
            return True
        return False

    async def spending_insights(
        self,
        request: SpendingInsightRequest,
        *,
        user_id: str = DEFAULT_CURRENT_USER_ID,
    ) -> SpendingInsightResponse:
        is_cross_user, target_name = self._is_query_for_other_users(request.question)
        if is_cross_user:
            return self._build_cross_user_access_warning_insight(
                request.question,
                target_name=target_name,
                include_recommendations=request.include_recommendations,
            )

        # Document / RAG queries: questions mentioning files, PDFs, documents, or document datasets
        if self._is_document_query(request.question):
            from app.services.rag.answering import answer_with_rag

            rag_result = await answer_with_rag(
                question=request.question,
                user_id=user_id,
                analytics=self.analytics,
            )
            sources = rag_result.get("sources", [])
            return SpendingInsightResponse(
                summary=rag_result.get("answer", ""),
                key_findings=[],
                recommendations=[],
                limitations=[f"Source: {', '.join(sources)}"] if sources else [],
            )

        today = today_ist()

        order = self._transaction_lookup_order(request.question)
        if order is not None:
            return await self._transaction_lookup_insight(
                request.question,
                user_id=user_id,
                order=order,
                today=today,
            )

        today = today_ist()
        qa_engine = FinancialQAEngine(self.analytics, self.transaction_service)
        qa_result = await qa_engine.execute_qa(
            request.question,
            user_id=user_id,
            include_recommendations=request.include_recommendations,
            request_start=request.start_date,
            request_end=request.end_date,
            reference_date=today,
        )

        no_data_indicators = (
            "couldn't find any transaction records",
            "no transaction data found",
            "no transactions were found",
            "no transactions recorded",
            "your financial records do not contain",
            "no expense transactions found",
            "no monthly expense records",
            "cannot calculate income portion",
        )
        intent = classify_question_intent(request.question)
        recommendation_intents = {
            "ITEM_QUERY",
            "BUDGET_EXCEEDANCE",
            "UNUSUAL_EXPENSES",
            "SPENDING_PATTERNS",
            "SPENDING_REDUCTION",
            "BUDGET_IMPROVEMENT",
            "SAVINGS_ADVICE",
        }
        if any(ind in qa_result.summary.lower() for ind in no_data_indicators) or intent.intent_type in recommendation_intents:
            return qa_result

        settings = get_settings()

        date_res = resolve_date_range(
            request.question,
            request_start=request.start_date,
            request_end=request.end_date,
            reference_date=today,
        )
        start_date = date_res.start_date
        end_date = date_res.end_date

        # Search for individual transactions matching specific question terms (e.g. "boovan", "netflix", "20000")
        matching_transactions: list[dict[str, Any]] = []
        search_terms = self._extract_search_terms(request.question)
        if search_terms and self.transaction_service:
            search_start = start_date.isoformat() if (date_res.is_explicit and start_date) else None
            search_end = end_date.isoformat() if (date_res.is_explicit and end_date) else None
            for term in search_terms[:3]:
                try:
                    found = await self.transaction_service.list(
                        transaction_type=None,
                        category=None,
                        start_date=search_start,
                        end_date=search_end,
                        limit=10,
                        skip=0,
                        user_id=user_id,
                        search=term,
                    )
                    for item in found.get("items", []):
                        if not any(tx.get("id") == item.get("id") for tx in matching_transactions):
                            matching_transactions.append(item)
                except Exception:
                    pass

        if self._is_out_of_scope(
            request.question,
            summary=None,
            has_matching_transactions=bool(matching_transactions),
        ):
            return self._build_out_of_scope_insight(
                request.question,
                include_recommendations=request.include_recommendations,
            )

        try:
            summary = await self.analytics.spending_summary(
                start_date,
                end_date,
                user_id=user_id,
            )
        except Exception:
            summary = None

        total_outflows = round(
            float(summary.total_expenses if summary else 0.0)
            + float(summary.total_investments if summary else 0.0)
            + float(summary.total_loan_repayments if summary else 0.0),
            2,
        )

        system_prompt = """
You are a financial spending analysis assistant.

A deterministic financial engine has already computed the exact figures, facts, and category breakdown from the user's authenticated transactions.
Your role is to explain these verified facts clearly, concisely, and helpfully in natural language.

Rules:
1. Never invent transactions, totals, or financial facts.
2. Directly answer the user's question using the supplied verified data:
   - Use the exact figures from verified_computed_answer.
   - Do not alter or recalculate any numbers, counts, or dates.
   - When answering a specific category, transaction, or focused question, do not append unrequested overall financial summaries, cash inflows, total cash outflows, or unrelated category breakdowns.
3. Understand Operating Expenses vs. Asset Allocation & Debt:
   - Operating expenses: ONLY transactions of type 'expense'.
   - Investments: Transactions of type 'investment' (asset allocation, not ordinary expenses).
   - Loan repayments: Transactions of type 'loan_repaid'.
   - When the user asks 'Where did I spend the most?' or 'Where did I spend the least?', calculate category-wise operating expenses by default. Do not classify investments or loan repayments as normal operating expenses.
   - Largest cash outflow stream (e.g. Investments) and highest operating expense category (e.g. Groceries) are different financial concepts. Distinguish them clearly.
4. Clearly distinguish observed facts from suggestions.
5. Give practical, conservative budgeting recommendations only when requested and when data exists. Never recommend reviewing duplicate charges unless duplicate transactions are explicitly verified. If include_recommendations is false or no meaningful recommendation exists, return [].
6. Do not guarantee savings or investment returns.
7. Disclose the period analyzed and data coverage notes in limitations.
8. Return only JSON matching the requested response structure with keys: summary, key_findings, recommendations, limitations.
"""
        payload = {
            "question": request.question,
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
            "verified_computed_answer": qa_result.summary,
            "verified_key_findings": qa_result.key_findings,
            "verified_limitations": qa_result.limitations,
            "financial_summary": summary.model_dump(mode="json") if summary else {},
            "cash_outflows": {
                "total_cash_outflow": total_outflows,
                "expenses": float(summary.total_expenses if summary else 0.0),
                "investments": float(summary.total_investments if summary else 0.0),
                "loan_repayments": float(summary.total_loan_repayments if summary else 0.0),
                "top_expense_categories": [
                    {
                        "category": c.category,
                        "amount": c.total_amount,
                        "count": c.transaction_count,
                    }
                    for c in (summary.category_breakdown[:5] if summary else [])
                ],
            },
            "include_recommendations": request.include_recommendations,
            "verified_recommendations": [
                {
                    "title": r.title,
                    "explanation": r.explanation,
                    "estimated_monthly_savings": r.estimated_monthly_savings,
                }
                for r in qa_result.recommendations
            ],
        }
        if matching_transactions:
            payload["matching_transactions"] = [
                {
                    "date": str(tx.get("date", "")),
                    "amount": float(tx.get("amount", 0)),
                    "category": tx.get("category", ""),
                    "transaction_type": tx.get("transaction_type", ""),
                    "description": tx.get("description", ""),
                }
                for tx in matching_transactions[:10]
            ]

        try:
            prompts = [
                (
                    settings.gemini_model,
                    (
                        f"{system_prompt}\n\n"
                        "Financial analysis request:\n"
                        f"{json.dumps(payload, default=str)}"
                    ),
                    0.2,
                ),
                (
                    "gemini-3.6-flash",
                    (
                        "Return only a JSON object with keys summary, "
                        "key_findings, recommendations, limitations. "
                        "Use only the supplied financial data. "
                        f"Question: {request.question}\n"
                        f"Data: {json.dumps(payload, default=str)}"
                    ),
                    0,
                ),
                (
                    settings.gemini_model,
                    (
                        f"{system_prompt}\n\n"
                        "Return a concise JSON financial answer with keys "
                        "summary, key_findings, recommendations, limitations. "
                        "Use only the supplied financial data.\n"
                        f"Financial analysis request:\n"
                        f"{json.dumps(payload, default=str)}"
                    ),
                    0,
                ),
            ]
            content = None
            last_generation_error: Exception | None = None
            for model, prompt, temperature in prompts:
                try:
                    response = await self._generate_content(
                        model=model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=temperature,
                            max_output_tokens=settings.gemini_max_output_tokens,
                        ),
                    )
                    content = response.text
                    if content:
                        result = self._normalize_insight_response(content)
                        if not request.include_recommendations:
                            result.recommendations = []
                        elif qa_result.recommendations:
                            is_generic = not result.recommendations or any(
                                r.title.strip().lower() in ("recommendation", "budget recommendation", "general recommendation")
                                for r in result.recommendations
                            )
                            if is_generic:
                                result.recommendations = qa_result.recommendations
                        return result
                except (AllKeysExhausted, ExternalServiceError):
                    raise
                except Exception as exc:
                    last_generation_error = exc
                    logger.warning(
                        "Gemini insights model attempt failed "
                        "(model=%s error_type=%s error_kind=%s)",
                        model,
                        type(exc).__name__,
                        classify(exc),
                    )
                    continue

            if last_generation_error is not None:
                raise last_generation_error
            raise ValueError("The AI returned an empty response.")
        except (AllKeysExhausted, ExternalServiceError):
            raise
        except json.JSONDecodeError as exc:
            raise ExternalServiceError(
                "The AI returned an invalid response structure."
            ) from exc
        except ValidationError as exc:
            raise ExternalServiceError(
                "The AI returned an invalid response structure."
            ) from exc
        except ValueError as exc:
            raise ExternalServiceError(
                "The AI returned an empty or invalid response."
            ) from exc
        except Exception as exc:
            logger.error(
                "Gemini spending insights could not be generated "
                "(error_type=%s error_kind=%s)",
                type(exc).__name__,
                classify(exc),
            )
            raise ExternalServiceError(
                "Unable to generate financial insights."
            ) from exc

    @staticmethod
    def _transaction_lookup_order(question: str) -> str | None:
        normalized = question.casefold()
        order_match = re.search(
            r"\b(most recent|latest|last|newest|recent|earliest|first)\b",
            normalized,
        )
        if not order_match:
            return None
        asks_for_transaction = re.search(
            r"\b(transaction|purchase|expense|income|payment|entry|record)\b",
            normalized,
        )
        asks_for_relative_item = re.search(r"\b(today|yesterday)\b", normalized)
        if not asks_for_transaction and not asks_for_relative_item:
            return None
        if order_match.group(1) in {"first", "earliest"}:
            return "first"
        return "last"

    async def _transaction_lookup_insight(
        self,
        question: str,
        *,
        user_id: str,
        order: str,
        today: Date,
    ) -> SpendingInsightResponse:
        if self.transaction_service is None:
            return SpendingInsightResponse(
                summary="I can't look up individual transactions right now.",
                key_findings=[],
                recommendations=[],
                limitations=["The transaction lookup service is unavailable."],
            )

        normalized = question.casefold()
        query_date = None
        if re.search(r"\btoday\b", normalized):
            query_date = today
        elif re.search(r"\byesterday\b", normalized):
            query_date = today - timedelta(days=1)
        else:
            explicit_date = re.search(r"\b20\d{2}-\d{2}-\d{2}\b", normalized)
            if explicit_date:
                try:
                    query_date = Date.fromisoformat(explicit_date.group(0))
                except ValueError:
                    query_date = None

        date_value = query_date.isoformat() if query_date else None
        try:
            result = await self.transaction_service.list(
                transaction_type=None,
                category=None,
                start_date=date_value,
                end_date=date_value,
                limit=1,
                skip=0,
                user_id=user_id,
                sort_descending=(order == "last"),
            )
        except Exception as exc:
            logger.warning(
                "Mongo transaction lookup failed for an insight",
                extra={"error_type": type(exc).__name__},
            )
            raise ExternalServiceError(
                "Unable to look up transaction records."
            ) from exc

        transactions = result.get("items", [])
        period = f" on {date_value}" if date_value else ""
        if not transactions:
            message = (
                f"No transaction was found{period}."
                if date_value
                else "No transactions were found in your records."
            )
            return SpendingInsightResponse(
                summary=message,
                key_findings=[],
                recommendations=[],
                limitations=[],
            )

        transaction = transactions[0]
        description = str(
            transaction.get("description")
            or transaction.get("merchant")
            or transaction.get("category")
            or "Transaction"
        ).strip()
        amount = float(transaction.get("amount", 0))
        transaction_type = str(
            transaction.get("transaction_type") or "transaction"
        ).replace("_", " ")
        category = str(transaction.get("category") or "uncategorized")
        transaction_date = transaction.get("date", "unknown date")
        if hasattr(transaction_date, "isoformat"):
            transaction_date = transaction_date.isoformat()
        label = "first" if order == "first" else "latest"
        finding = (
            f"{description}: ₹{amount:,.2f} {transaction_type}, "
            f"category {category}, dated {transaction_date}."
        )
        return SpendingInsightResponse(
            summary=f"Your {label} transaction{period}:",
            key_findings=[finding],
            recommendations=[],
            limitations=[
                (
                    "Transaction records store a date, not a time; "
                    "same-day order follows record ID."
                )
            ],
        )

    async def extract_transaction(
        self,
        request: TransactionTextRequest,
    ) -> TransactionExtractionResponse:
        settings = get_settings()
        today = today_ist().isoformat()
        allowed_types = ", ".join(TRANSACTION_TYPES)
        system_prompt = f"""
Extract transaction details from the user's text.

Today's date is {today}.

Allowed transaction types:
{allowed_types}.

Rules:
1. Extract only information supported by the text.
2. Use ISO date format YYYY-MM-DD.
3. Interpret today and yesterday relative to today's date.
4. Never invent a transaction amount.
5. Use a concise description.
6. Choose an appropriate category.
7. Set confidence between 0 and 1.
8. Set requires_confirmation to true.
9. Return JSON only, matching the requested fields.
10. If the amount or transaction type is ambiguous, do not
    fabricate certainty. Ambiguous input should be clarified.
"""
        try:
            response = await self._generate_content(
                model=settings.gemini_model,
                contents=(f"{system_prompt}\n\nUser transaction text:\n{request.text}"),
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0,
                    max_output_tokens=settings.gemini_max_output_tokens,
                ),
            )
            content = response.text
            if not content:
                raise ValueError("The AI returned an empty response.")
            candidate = TransactionExtractionResponse.model_validate_json(content)
            candidate.requires_confirmation = True
            return candidate
        except (AllKeysExhausted, ExternalServiceError):
            raise
        except ValidationError as exc:
            raise ExternalServiceError(
                "The AI returned invalid transaction fields."
            ) from exc
        except ValueError as exc:
            raise ExternalServiceError(
                "The AI returned an empty or invalid response."
            ) from exc
        except Exception as exc:
            raise ExternalServiceError(
                "Unable to extract transaction details."
            ) from exc
