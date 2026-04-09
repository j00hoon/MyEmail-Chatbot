from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from retrieval.execution_plans import QueryExecutionPlan
from retrieval.retrievers import CandidateEmail


@dataclass
class CandidateReranker:
    def rerank(self, *, execution_plan: QueryExecutionPlan, candidates: list[CandidateEmail]):
        merged = self._merge_candidates(candidates)
        ranked = []
        for candidate in merged.values():
            filter_score = self._filter_score(candidate=candidate, execution_plan=execution_plan)
            recency_score = self._recency_score(candidate.sent_at)
            strategy_weights = self._weights_for_strategy(execution_plan.strategy)
            candidate.final_score = (
                candidate.metadata_score * strategy_weights["metadata"]
                + candidate.lexical_score * strategy_weights["lexical"]
                + candidate.semantic_score * strategy_weights["semantic"]
                + filter_score * strategy_weights["filter"]
                + recency_score * strategy_weights["recency"]
            )
            ranked.append(candidate)

        ranked.sort(
            key=lambda candidate: (
                candidate.final_score,
                self._filter_score(candidate=candidate, execution_plan=execution_plan),
                self._parse_sent_at(candidate.sent_at),
            ),
            reverse=True,
        )
        return ranked

    def select(self, *, execution_plan: QueryExecutionPlan, candidates: list[CandidateEmail]):
        if execution_plan.selection_policy == "best_match":
            return candidates[:1]
        if execution_plan.selection_policy == "all":
            return candidates[: execution_plan.result_limit]
        return candidates[: execution_plan.result_limit]

    def _merge_candidates(self, candidates: list[CandidateEmail]):
        merged: dict[str, CandidateEmail] = {}
        for candidate in candidates:
            key = candidate.gmail_message_id
            existing = merged.get(key)
            if existing is None:
                merged[key] = candidate
                continue

            existing.metadata_score = max(existing.metadata_score, candidate.metadata_score)
            existing.lexical_score = max(existing.lexical_score, candidate.lexical_score)
            existing.semantic_score = max(existing.semantic_score, candidate.semantic_score)
            existing.provenance |= set(candidate.provenance)
            existing.matched_terms = sorted(set(existing.matched_terms) | set(candidate.matched_terms))
            if len(candidate.document or "") > len(existing.document or ""):
                existing.document = candidate.document
            if not existing.snippet and candidate.snippet:
                existing.snippet = candidate.snippet
        return merged

    def _filter_score(self, *, candidate: CandidateEmail, execution_plan: QueryExecutionPlan):
        checks: list[float] = []
        sender_filter = (execution_plan.metadata_filters.get("sender") or "").strip().lower()
        subject_filter = (execution_plan.metadata_filters.get("subject") or "").strip().lower()
        if sender_filter:
            checks.append(1.0 if sender_filter in (candidate.sender or "").lower() else 0.0)
        if subject_filter:
            checks.append(1.0 if subject_filter in (candidate.subject or "").lower() else 0.0)

        if execution_plan.metadata_filters.get("date_from") or execution_plan.metadata_filters.get("date_to"):
            checks.append(1.0 if self._within_date_range(candidate.sent_at, execution_plan.metadata_filters) else 0.0)

        if execution_plan.category_filters:
            checks.append(1.0 if (candidate.gmail_category or "uncategorized") in set(execution_plan.category_filters) else 0.0)

        if not checks:
            return 0.5
        return sum(checks) / len(checks)

    def _within_date_range(self, raw_sent_at: str | None, metadata_filters: dict[str, str | None]):
        sent_at = self._parse_sent_at(raw_sent_at)
        date_from = self._parse_filter_date(metadata_filters.get("date_from"))
        date_to = self._parse_filter_date(metadata_filters.get("date_to"), end_of_day=True)
        if date_from is not None and sent_at < date_from:
            return False
        if date_to is not None and sent_at > date_to:
            return False
        return True

    def _weights_for_strategy(self, strategy: str):
        if strategy == "exact":
            return {
                "metadata": 0.35,
                "lexical": 0.15,
                "semantic": 0.10,
                "filter": 0.30,
                "recency": 0.10,
            }
        if strategy == "hybrid":
            return {
                "metadata": 0.20,
                "lexical": 0.25,
                "semantic": 0.25,
                "filter": 0.20,
                "recency": 0.10,
            }
        return {
            "metadata": 0.10,
            "lexical": 0.15,
            "semantic": 0.45,
            "filter": 0.15,
            "recency": 0.15,
        }

    def _recency_score(self, raw_sent_at: str | None):
        sent_at = self._parse_sent_at(raw_sent_at)
        if sent_at == datetime.min.replace(tzinfo=timezone.utc):
            return 0.0
        age = max((datetime.now(timezone.utc) - sent_at).days, 0)
        if age <= 7:
            return 1.0
        if age <= 30:
            return 0.75
        if age <= 90:
            return 0.45
        return 0.15

    def _parse_filter_date(self, raw_value: str | None, *, end_of_day: bool = False):
        if not raw_value:
            return None
        try:
            parsed = datetime.fromisoformat(raw_value)
        except ValueError:
            return None
        if end_of_day:
            parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    def _parse_sent_at(self, sent_at: str | None):
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

