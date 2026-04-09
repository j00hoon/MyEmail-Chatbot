from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import logging
from pathlib import Path

from config import settings
from retrieval.execution_plans import QueryExecutionPlan
from schemas import EmailSearchFilters, EmailSearchIntent, DateRange


def _utc_today():
    return datetime.now(timezone.utc).date()


DEBUG_LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "query_debug.log"
DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

_debug_logger = logging.getLogger("query_debug")
if not _debug_logger.handlers:
    handler = logging.FileHandler(DEBUG_LOG_PATH, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    _debug_logger.addHandler(handler)
    _debug_logger.setLevel(logging.INFO)
    _debug_logger.propagate = False


def _build_default_intent(question: str):
    cleaned_question = " ".join(question.strip().split())
    fallback_keyword = cleaned_question[:120] if cleaned_question else "email search"
    return EmailSearchIntent(
        intent="SEARCH_EMAILS",
        search_filters=EmailSearchFilters(
            keywords=[fallback_keyword],
            semantic_expansions=[],
            sender=None,
            subject=None,
            is_important=False,
        ),
        date_range=DateRange(),
        result_scope="top_n",
        aggregation_mode="emails",
        retrieval_mode_hint="hybrid",
        requested_count=None,
        output_mode="bullet_points",
    )


class QueryAnalyzer:
    def __init__(self):
        self._chain = self._build_chain()

    def analyze(self, question: str, *, reference_date: date | None = None):
        reference_date = reference_date or _utc_today()

        if self._chain is None:
            self._log_debug(
                event="query_analyzer_fallback",
                reason="chain_unavailable",
                question=question,
                reference_date=reference_date.isoformat(),
            )
            return _build_default_intent(question)

        try:
            result = self._chain.invoke(
                {
                    "question": question.strip(),
                    "reference_date": reference_date.isoformat(),
                }
            )
            self._log_debug(
                event="query_analyzer_success",
                question=question,
                reference_date=reference_date.isoformat(),
                parsed_intent=result.model_dump(mode="json"),
            )
            return result
        except Exception as exc:
            self._log_debug(
                event="query_analyzer_fallback",
                reason="invoke_exception",
                question=question,
                reference_date=reference_date.isoformat(),
                exception_type=type(exc).__name__,
                exception_message=str(exc),
                exception_repr=repr(exc),
            )
            return _build_default_intent(question)

    def _build_chain(self):
        if not settings.openai_api_key:
            return None

        try:
            from langchain_core.prompts import ChatPromptTemplate
            from langchain_openai import ChatOpenAI
        except ImportError:
            return None

        llm = ChatOpenAI(
            api_key=settings.openai_api_key,
            model=settings.openai_chat_model,
            temperature=0,
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "\n".join(
                        [
                            "You are a query understanding engine for a Gmail search assistant.",
                            "Convert the user's request into a strictly structured EmailSearchIntent object.",
                            "Use the provided reference date to resolve all relative time expressions into absolute ISO dates.",
                            "Return start_date and end_date in YYYY-MM-DD format when the user implies a range.",
                            "Interpret semantic intent, not just literal words.",
                            "For topic searches, populate keywords with the user's core topics in priority order.",
                            "Populate semantic_expansions with a flat list of synonyms or neighboring concepts that improve retrieval.",
                            "If the user asks about billing, likely semantic expansions include terms such as payment, invoice, receipt, premium, charge, transaction, statement, or refund when context supports them.",
                            "Set sender only when the user is clearly asking about a specific sender or contact.",
                            "Use intent=SUMMARIZE_THREADS when the user wants a synthesized summary over multiple related emails.",
                            "Use intent=FIND_CONTACT when the user mainly wants a sender/contact identity.",
                            "Use intent=UNSUBSCRIBE_ASSIST only for unsubscribe or mailing-list management requests.",
                            "Set result_scope=all when the user asks for all matching emails.",
                            "Set result_scope=best_match when the user clearly wants the single most relevant email.",
                            "Set result_scope=top_n when the user asks for a subset, recent highlights, or a bounded summary.",
                            "Set requested_count only when the user explicitly or implicitly asks for a number of results.",
                            "Use aggregation_mode=threads when the user asks for thread-level summaries.",
                            "Use aggregation_mode=senders when the user wants a contact or sender list.",
                            "Use retrieval_mode_hint=exact for filter-heavy requests driven by sender, date, subject, or explicit mailbox constraints.",
                            "Use retrieval_mode_hint=hybrid for mixed topic-and-filter searches.",
                            "Use retrieval_mode_hint=semantic for broad exploratory meaning-based searches without tight filters.",
                            "Use output_mode=bullet_points for list-like or summary-over-multiple-email requests.",
                            "Use output_mode=table only when the user explicitly asks for a table.",
                            "Use output_mode=raw_list when the user explicitly asks for a raw list.",
                            "Use output_mode=concise_summary otherwise.",
                            "Only set is_important=true when the user explicitly asks for important or urgent emails.",
                        ]
                    ),
                ),
                (
                    "human",
                    "\n".join(
                        [
                            "Reference date: {reference_date}",
                            "User question: {question}",
                        ]
                    ),
                ),
            ]
        )

        try:
            return prompt | llm.with_structured_output(
                EmailSearchIntent,
                method="function_calling",
            )
        except AttributeError:
            self._log_debug(
                event="query_analyzer_chain_init_failed",
                reason="with_structured_output_missing",
            )
            return None

    def _log_debug(self, **payload):
        try:
            _debug_logger.info(payload)
        except Exception:
            return


class GmailQueryBuilder:
    def build(self, structured_intent: EmailSearchIntent, *, category_filters: list[str] | None = None):
        clauses: list[str] = []

        sender = (structured_intent.search_filters.sender or "").strip()
        if sender:
            clauses.append(f"from:{self._escape_token(sender)}")

        subject = (structured_intent.search_filters.subject or "").strip()
        if subject:
            clauses.append(f"subject:{self._escape_token(subject)}")

        for group in structured_intent.search_filters.grouped_terms():
            group_clause = " OR ".join(self._escape_token(term) for term in group)
            if group_clause:
                clauses.append(f"({group_clause})")

        if structured_intent.search_filters.is_important:
            clauses.append("is:important")

        if category_filters:
            label_clauses = [f"category:{self._escape_token(category)}" for category in category_filters]
            clauses.append("(" + " OR ".join(label_clauses) + ")")

        start_date = structured_intent.date_range.start_date
        end_date = structured_intent.date_range.end_date
        if start_date is not None:
            clauses.append(f"after:{start_date.strftime('%Y/%m/%d')}")
        if end_date is not None:
            day_after = end_date + timedelta(days=1)
            clauses.append(f"before:{day_after.strftime('%Y/%m/%d')}")

        return " ".join(clause for clause in clauses if clause).strip()

    def _escape_token(self, value: str):
        cleaned = " ".join(value.strip().split())
        if not cleaned:
            return '""'
        if " " in cleaned or ":" in cleaned:
            escaped = cleaned.replace('"', '\\"')
            return f'"{escaped}"'
        return cleaned


class QueryExecutionPlanner:
    def __init__(self, gmail_query_builder: GmailQueryBuilder | None = None):
        self.gmail_query_builder = gmail_query_builder or GmailQueryBuilder()

    def build(
        self,
        *,
        account_id: str,
        question: str,
        structured_intent: EmailSearchIntent,
        reference_date: date | None = None,
        category_filters: list[str] | None = None,
        search_filters: dict | None = None,
    ):
        merged_sender = (search_filters or {}).get("sender") or structured_intent.search_filters.sender
        merged_subject = (search_filters or {}).get("subject") or structured_intent.search_filters.subject
        date_from = (search_filters or {}).get("date_from") or self._date_to_string(structured_intent.date_range.start_date)
        date_to = (search_filters or {}).get("date_to") or self._date_to_string(structured_intent.date_range.end_date)
        keyword_terms = structured_intent.search_filters.ordered_terms()
        semantic_query_text = self._build_semantic_query_text(question=question, structured_intent=structured_intent)
        strategy = self._resolve_strategy(
            structured_intent=structured_intent,
            merged_sender=merged_sender,
            merged_subject=merged_subject,
            date_from=date_from,
            date_to=date_to,
            category_filters=category_filters or [],
        )
        result_limit = self._resolve_result_limit(structured_intent=structured_intent)
        candidate_limit = self._resolve_candidate_limit(
            structured_intent=structured_intent,
            strategy=strategy,
            result_limit=result_limit,
        )

        return QueryExecutionPlan(
            account_id=account_id,
            question=question,
            reference_date=reference_date or _utc_today(),
            structured_intent=structured_intent,
            strategy=strategy,
            selection_policy=structured_intent.result_scope,
            candidate_limit=candidate_limit,
            result_limit=result_limit,
            gmail_query=self.gmail_query_builder.build(structured_intent, category_filters=category_filters),
            semantic_query_text=semantic_query_text,
            metadata_filters={
                "sender": merged_sender,
                "subject": merged_subject,
                "date_from": date_from,
                "date_to": date_to,
            },
            category_filters=list(category_filters or []),
            keyword_terms=keyword_terms,
            must_apply_filters=True,
        )

    def _build_semantic_query_text(self, *, question: str, structured_intent: EmailSearchIntent):
        parts = [question.strip()]

        ordered_terms = structured_intent.search_filters.ordered_terms()
        if ordered_terms:
            parts.append("Priority search concepts: " + ", ".join(ordered_terms))

        sender = (structured_intent.search_filters.sender or "").strip()
        if sender:
            parts.append(f"Sender focus: {sender}")

        subject = (structured_intent.search_filters.subject or "").strip()
        if subject:
            parts.append(f"Subject focus: {subject}")

        if structured_intent.search_filters.is_important:
            parts.append("Importance focus: important or urgent messages")

        if structured_intent.date_range.start_date or structured_intent.date_range.end_date:
            start_date = self._date_to_string(structured_intent.date_range.start_date) or "open"
            end_date = self._date_to_string(structured_intent.date_range.end_date) or "open"
            parts.append(f"Date range: {start_date} to {end_date}")

        return "\n".join(part for part in parts if part).strip()

    def _date_to_string(self, value: date | None):
        return value.isoformat() if value is not None else None

    def _resolve_strategy(
        self,
        *,
        structured_intent: EmailSearchIntent,
        merged_sender: str | None,
        merged_subject: str | None,
        date_from: str | None,
        date_to: str | None,
        category_filters: list[str],
    ):
        hint = structured_intent.retrieval_mode_hint
        ordered_terms = structured_intent.search_filters.ordered_terms()
        filter_strength = sum(
            1
            for value in (
                merged_sender,
                merged_subject,
                date_from,
                date_to,
            )
            if value
        ) + (1 if category_filters else 0)

        if hint == "exact":
            return "exact"
        if hint == "semantic" and filter_strength == 0:
            return "semantic"
        if structured_intent.result_scope == "all" and filter_strength >= 1 and not ordered_terms:
            return "exact"
        if filter_strength >= 2 and structured_intent.result_scope in {"all", "best_match"}:
            return "exact" if not ordered_terms else "hybrid"
        if ordered_terms and filter_strength >= 1:
            return "hybrid"
        if ordered_terms:
            return "hybrid"
        return "semantic"

    def _resolve_result_limit(self, *, structured_intent: EmailSearchIntent):
        if structured_intent.result_scope == "best_match":
            return 1
        if structured_intent.result_scope == "all":
            return structured_intent.requested_count or 25
        return structured_intent.requested_count or 6

    def _resolve_candidate_limit(self, *, structured_intent: EmailSearchIntent, strategy: str, result_limit: int):
        if strategy == "exact":
            return max(result_limit * 4, 50)
        if strategy == "hybrid":
            return max(result_limit * 6, 24)
        return max(result_limit * 8, 24)
