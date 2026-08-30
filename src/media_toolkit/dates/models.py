"""Domain models for capture-date evidence and resolution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class DateCandidate:
    """One parsed date value and its provenance."""

    source: str
    value: str
    local_datetime: datetime
    utc_datetime: datetime | None
    timezone_name: str | None
    timezone_source: str
    priority: int
    confidence: str
    evidence_kind: str
    precision: str = "SECOND"
    timezone_ambiguous: bool = False
    timezone_nonexistent: bool = False


@dataclass(frozen=True)
class DateResolution:
    """Deterministic effective date plus review state and complete evidence."""

    status: str
    selected: DateCandidate | None
    candidates: tuple[DateCandidate, ...]
    reasons: tuple[str, ...]
