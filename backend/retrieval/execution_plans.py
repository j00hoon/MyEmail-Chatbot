from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from schemas import EmailSearchIntent


RetrievalStrategy = Literal["exact", "hybrid", "semantic"]
SelectionPolicy = Literal["all", "top_n", "best_match"]


@dataclass
class QueryExecutionPlan:
    account_id: str
    question: str
    reference_date: date
    structured_intent: EmailSearchIntent
    strategy: RetrievalStrategy
    selection_policy: SelectionPolicy
    candidate_limit: int
    result_limit: int
    gmail_query: str
    semantic_query_text: str
    metadata_filters: dict[str, str | None]
    category_filters: list[str] = field(default_factory=list)
    keyword_terms: list[str] = field(default_factory=list)
    must_apply_filters: bool = True
