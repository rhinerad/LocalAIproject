#!/usr/bin/env python3
"""The ordered, bounded context-preparation seam for one agent turn.

This module deliberately owns policy and ordering, not tool permissions or
model routing.  The concrete stages remain in their specialist modules so
their existing safeguards and observable messages stay unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ContextBudgetPolicy:
    """Named, stable limits for every pre-model context source."""

    tool_result_chars: int = 2400
    url_evidence_chars: int = 3500
    continuity_turn_chars: int = 360
    exemplar_chars: int = 3200
    deep_research_result_chars: int = 6000


BUDGETS = ContextBudgetPolicy()


class ContextPrefetcher:
    """Run the five historical stages without changing their event order.

    URL evidence intentionally has its own early method because the Sonic Pi
    deterministic guard sits between that stage and the other four in the
    legacy request path. Keeping the seam explicit prevents a future cleanup
    from silently reordering those visible tool events.
    """

    def __init__(self, *, url_evidence: Callable[[], None],
                 project_docs: Callable[[], None],
                 prior_chats: Callable[[], None],
                 difficulty_plan: Callable[[], None],
                 exemplars: Callable[[], list[str]]) -> None:
        self._url_evidence = url_evidence
        self._project_docs = project_docs
        self._prior_chats = prior_chats
        self._difficulty_plan = difficulty_plan
        self._exemplars = exemplars

    def inject_early_url_evidence(self) -> None:
        self._url_evidence()

    def inject_remaining(self) -> list[str]:
        self._project_docs()
        self._prior_chats()
        self._difficulty_plan()
        return self._exemplars()
