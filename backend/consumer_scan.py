"""Consumer-facing scan wrapper (CON-01).

Wraps ProductInspection. Does not fork ExtractedFact. Does not expose bboxes,
per-engine confidence, or rule IDs. UNCERTAIN is a first-class consumer
outcome and is never flattened to pass/fail.

Public access is flag-gated (LMPC_ENABLE_CONSUMER_SCAN) and rate-limited.
No new RBAC role is introduced (ARCH-01 SCR: keep inspector/reviewer/admin).
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock
from typing import Deque, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field

from schema import FactStatus, ProductInspection


CONSUMER_VERDICT_COPY = {
    FactStatus.PASS: (
        "The photo looks consistent with the declarations we could read. "
        "This is not a legal determination."
    ),
    FactStatus.FAIL: (
        "Some required declarations could not be confirmed as compliant from "
        "this photo. A Legal Metrology officer must review before any action."
    ),
    FactStatus.UNCERTAIN: (
        "We could not confirm this from the photo. That is not a pass and not "
        "a violation — the image did not give enough reliable evidence."
    ),
    FactStatus.EXEMPT: (
        "This package appears outside the ordinary retail-package rules that "
        "this scan checks (for example a statutory exemption). Confirm with "
        "an officer before relying on that."
    ),
}


class ConsumerScanItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str
    observed: Optional[str] = None
    outcome: str  # PASS | FAIL | UNCERTAIN | EXEMPT — never collapsed
    plain_language: str


class ConsumerScanResponse(BaseModel):
    """Published contract for CON-02 / FE-02 / AUTH-01. Draft, additive."""

    model_config = ConfigDict(extra="forbid")
    scan_id: str
    overall_status: str
    headline: str
    plain_language: str
    disclaimer: str
    review_required: bool = False
    items: list[ConsumerScanItem] = Field(default_factory=list)
    captured_at: Optional[str] = None
    source: str = "consumer"
    evidentially_weaker_than_inspector: bool = True


def _item_copy(status: FactStatus, field: str) -> str:
    if status is FactStatus.UNCERTAIN:
        return f"Could not confirm '{field}' from this photo."
    if status is FactStatus.FAIL:
        return f"'{field}' did not meet the automated check on this photo."
    if status is FactStatus.EXEMPT:
        return f"'{field}' is outside the rules this scan applies."
    return f"'{field}' was readable and did not fail the automated check."


def to_consumer_response(
    inspection: ProductInspection,
    *,
    scan_id: str,
    captured_at: Optional[str] = None,
) -> ConsumerScanResponse:
    status = inspection.overall_status
    items: list[ConsumerScanItem] = []
    for fact in inspection.facts:
        if fact.field.startswith("__"):
            continue
        items.append(
            ConsumerScanItem(
                label=fact.label or fact.field,
                observed=fact.extracted_value,
                outcome=fact.status.value,
                plain_language=_item_copy(fact.status, fact.label or fact.field),
            )
        )
    return ConsumerScanResponse(
        scan_id=scan_id,
        overall_status=status.value,
        headline=status.value,
        plain_language=CONSUMER_VERDICT_COPY[status],
        disclaimer=inspection.disclaimer,
        review_required=bool(inspection.review_required or status is FactStatus.UNCERTAIN),
        items=items,
        captured_at=captured_at,
    )


class SlidingWindowRateLimiter:
    """In-process limiter. Redis is cache-only and must not be legal truth."""

    def __init__(self, max_events: int, window_seconds: float = 60.0) -> None:
        self.max_events = max(1, int(max_events))
        self.window_seconds = float(window_seconds)
        self._events: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            bucket = self._events[key]
            cutoff = now - self.window_seconds
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.max_events:
                return False
            bucket.append(now)
            return True
