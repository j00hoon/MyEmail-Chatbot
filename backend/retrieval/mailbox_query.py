import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime


SENDER_DELIMITER_PATTERN = re.compile(
    r"\b(?:regarding|about|re\b|subject\b|with\b|within\b|whose\b|that\b|which\b|during\b|over\b|for\b|and\s+(?:give|show|tell|summarize|read)\b)\b"
)


@dataclass
class QueryAnalysis:
    normalized_question: str
    sender_query: str = ""
    requested_count: int = 1
    window_days: int | None = None
    references_emails: bool = False
    wants_latest: bool = False
    wants_summary: bool = False
    wants_list: bool = False
    wants_important: bool = False
    asks_for_date: bool = False


@dataclass
class RetrievalPlan:
    kind: str
    normalized_question: str
    sender_query: str = ""
    requested_count: int = 1
    window_days: int | None = None
    answer_mode: str = "single_email"


class QueryAnalyzer:
    def analyze(self, question: str, default_count: int = 4):
        lowered = question.lower().strip()
        references_emails = any(term in lowered for term in ("email", "emails", "mail", "inbox", "message", "messages"))
        wants_latest = any(term in lowered for term in ("latest", "recent", "newest", "most recent", "last"))
        wants_summary = any(term in lowered for term in ("summarize", "summary", "summaries"))
        wants_list = any(term in lowered for term in ("list", "show", "give me", "select")) or wants_summary
        wants_important = "important" in lowered
        asks_for_date = any(phrase in lowered for phrase in ("when did", "what date", "on what date", "when was"))

        analysis = QueryAnalysis(
            normalized_question=self._normalize_text(question),
            sender_query=self._extract_sender_query(question),
            requested_count=self._extract_requested_count(question) or default_count,
            window_days=self._extract_window_days(question),
            references_emails=references_emails,
            wants_latest=wants_latest,
            wants_summary=wants_summary,
            wants_list=wants_list,
            wants_important=wants_important,
            asks_for_date=asks_for_date,
        )
        return analysis

    def _extract_requested_count(self, question: str):
        lowered = question.lower()
        patterns = (
            r"\b(?:top|select|latest|recent|newest|last)\s+(\d+)\b",
            r"\b(\d+)\s+(?:latest|recent|newest)\b",
            r"\b(\d+)\s+(?:emails|messages)\b",
        )
        for pattern in patterns:
            match = re.search(pattern, lowered)
            if match:
                return max(1, min(int(match.group(1)), 10))
        return None

    def _extract_window_days(self, question: str):
        lowered = question.lower()
        if any(
            term in lowered
            for term in (
                "last one week",
                "last week",
                "past week",
                "within a week",
                "within one week",
                "within the week",
                "7 day",
                "7-day",
            )
        ):
            return 7
        return None

    def _extract_sender_query(self, question: str):
        lowered = question.lower().strip()
        match = re.search(r"\bfrom\s+(.+?)(?:\?|$)", lowered)
        if not match:
            return ""

        candidate = match.group(1)
        candidate = SENDER_DELIMITER_PATTERN.split(candidate, maxsplit=1)[0]
        candidate = re.sub(r"[^a-z0-9@\.\s_-]", " ", candidate)
        tokens = [
            token
            for token in candidate.split()
            if token not in {"the", "a", "an", "latest", "recent", "newest", "last", "email", "emails"}
        ]
        sender_query = " ".join(tokens).strip()
        if not sender_query:
            return ""
        if not re.search(r"[a-z@]", sender_query):
            return ""
        return sender_query

    def _normalize_text(self, text: str):
        return " ".join(re.findall(r"[a-zA-Z0-9_]+", text.lower()))


class RetrievalPlanner:
    def build(self, analysis: QueryAnalysis):
        if (
            analysis.wants_important
            and analysis.window_days == 7
            and analysis.requested_count > 1
        ):
            return RetrievalPlan(
                kind="top_recent_important",
                normalized_question=analysis.normalized_question,
                requested_count=analysis.requested_count,
                window_days=analysis.window_days,
                answer_mode="multi_email",
            )

        if analysis.references_emails and analysis.wants_latest and analysis.requested_count > 1:
            return RetrievalPlan(
                kind="recent_email_list",
                normalized_question=analysis.normalized_question,
                requested_count=analysis.requested_count,
                window_days=analysis.window_days,
                answer_mode="multi_email",
            )

        if analysis.sender_query and analysis.wants_latest:
            return RetrievalPlan(
                kind="latest_from",
                normalized_question=analysis.normalized_question,
                sender_query=analysis.sender_query,
                requested_count=analysis.requested_count,
                window_days=analysis.window_days,
            )

        if analysis.sender_query:
            return RetrievalPlan(
                kind="sender_lookup",
                normalized_question=analysis.normalized_question,
                sender_query=analysis.sender_query,
                requested_count=analysis.requested_count,
                window_days=analysis.window_days,
                answer_mode=("multi_email" if analysis.references_emails and (analysis.wants_list or analysis.wants_summary or analysis.window_days is not None or analysis.requested_count > 1) else "single_email"),
            )

        if analysis.asks_for_date:
            return RetrievalPlan(
                kind="date_lookup",
                normalized_question=analysis.normalized_question,
            )

        return RetrievalPlan(
            kind="general",
            normalized_question=analysis.normalized_question,
            requested_count=analysis.requested_count,
        )


class CandidateSelector:
    def select_recent_emails(self, records, requested_count: int, window_days: int | None = None):
        ranked = []
        cutoff = None
        if window_days is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

        for record in records:
            sent_at = self.parse_sent_at(record.sent_at)
            if cutoff is not None and sent_at < cutoff:
                continue
            ranked.append((sent_at, record))

        ranked.sort(key=lambda item: item[0], reverse=True)
        return [record for _, record in ranked[:requested_count]]

    def parse_sent_at(self, sent_at: str | None):
        if not sent_at:
            return datetime.min.replace(tzinfo=timezone.utc)
        normalized = sent_at.strip()
        if " (" in normalized:
            normalized = normalized.split(" (", 1)[0]
        try:
            parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(sent_at)
            except (TypeError, ValueError, IndexError):
                return datetime.min.replace(tzinfo=timezone.utc)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
