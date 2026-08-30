"""Pure capture-date candidate extraction and deterministic resolution rules."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import re
from typing import Any, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from media_toolkit.dates.models import DateCandidate, DateResolution


PHOTO_FIELDS = (
    ("datetimeoriginal", "EXIF_DATETIME_ORIGINAL", 10, "HIGH"),
    ("createdate", "EXIF_CREATE_DATE", 20, "MEDIUM"),
    ("datecreated", "METADATA_DATE_CREATED", 30, "MEDIUM"),
    ("gpsdatetime", "GPS_DATE_TIME", 35, "HIGH"),
)
VIDEO_FIELDS = (
    ("com.apple.quicktime.creationdate", "QUICKTIME_CREATION_DATE", 10, "HIGH"),
    ("mediacreatedate", "MEDIA_CREATE_DATE", 15, "HIGH"),
    ("creation_time", "CONTAINER_CREATION_TIME", 20, "MEDIUM"),
    ("createdate", "QUICKTIME_CREATE_DATE", 25, "MEDIUM"),
    ("encoded_date", "ENCODED_DATE", 30, "MEDIUM"),
    ("tagged_date", "TAGGED_DATE", 35, "MEDIUM"),
)
FILENAME_PATTERNS = (
    re.compile(r"(?<!\d)(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})[_-](?P<hour>\d{2})(?P<minute>\d{2})(?P<second>\d{2})(?!\d)"),
    re.compile(r"(?<!\d)(?P<year>\d{4})[-_](?P<month>\d{2})[-_](?P<day>\d{2})[ T_-]+(?P<hour>\d{2})[._-](?P<minute>\d{2})[._-](?P<second>\d{2})(?!\d)"),
    re.compile(r"(?<!\d)(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})(?!\d)"),
)


def _flatten(value: Any, result: list[tuple[str, Any]]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(child, (dict, list)):
                _flatten(child, result)
            else:
                result.append((key.rsplit(":", 1)[-1].casefold(), child))
    elif isinstance(value, list):
        for child in value:
            _flatten(child, result)


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, (str, int, float)):
        return None
    text = str(value).strip()
    if not text or text.startswith("0000:00:00"):
        return None
    normalized = re.sub(r"^(\d{4}):(\d{2}):(\d{2})", r"\1-\2-\3", text)
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _timezone(name: str | None) -> ZoneInfo | None:
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return None


def _candidate(
    source: str,
    value: str,
    parsed: datetime,
    priority: int,
    confidence: str,
    evidence_kind: str,
    default_timezone: str | None,
    explicit_offset: str | None = None,
    precision: str = "SECOND",
) -> DateCandidate:
    timezone_source = "UNKNOWN"
    timezone_name: str | None = None
    timezone_ambiguous = False
    timezone_nonexistent = False
    aware = parsed
    if parsed.tzinfo is not None:
        timezone_source = "METADATA"
        timezone_name = str(parsed.tzinfo)
    elif explicit_offset:
        offset_value = explicit_offset.strip()
        if re.fullmatch(r"[+-]\d{2}:?\d{2}", offset_value):
            compact = offset_value if ":" in offset_value else f"{offset_value[:3]}:{offset_value[3:]}"
            aware = parsed.replace(tzinfo=datetime.fromisoformat(f"2000-01-01T00:00:00{compact}").tzinfo)
            timezone_source = "METADATA"
            timezone_name = compact
    elif (zone := _timezone(default_timezone)) is not None:
        first = parsed.replace(tzinfo=zone, fold=0)
        second = parsed.replace(tzinfo=zone, fold=1)
        first_valid = first.astimezone(UTC).astimezone(zone).replace(tzinfo=None) == parsed
        second_valid = second.astimezone(UTC).astimezone(zone).replace(tzinfo=None) == parsed
        timezone_ambiguous = (
            first_valid and second_valid and first.utcoffset() != second.utcoffset()
        )
        timezone_nonexistent = not first_valid and not second_valid
        aware = first if first_valid or not second_valid else second
        timezone_source = "SOURCE"
        timezone_name = default_timezone
    utc_value = aware.astimezone(UTC) if aware.tzinfo is not None else None
    return DateCandidate(
        source=source,
        value=value,
        local_datetime=parsed.replace(tzinfo=None),
        utc_datetime=utc_value,
        timezone_name=timezone_name,
        timezone_source=timezone_source,
        priority=priority,
        confidence=confidence,
        evidence_kind=evidence_kind,
        precision=precision,
        timezone_ambiguous=timezone_ambiguous,
        timezone_nonexistent=timezone_nonexistent,
    )


def metadata_candidates(
    raw: dict[str, Any] | None,
    media_type: str,
    default_timezone: str | None,
) -> list[DateCandidate]:
    """Extract ordered photo or video date evidence from raw extractor JSON."""
    if not raw:
        return []
    flattened: list[tuple[str, Any]] = []
    _flatten(raw, flattened)
    values: dict[str, list[Any]] = {}
    for key, value in flattened:
        values.setdefault(key, []).append(value)
    fields = PHOTO_FIELDS if media_type == "PHOTO" else VIDEO_FIELDS
    candidates: list[DateCandidate] = []
    for key, source, priority, confidence in fields:
        for raw_value in values.get(key, []):
            parsed = _parse_datetime(raw_value)
            if parsed is None:
                continue
            offset_key = "offsettimeoriginal" if key == "datetimeoriginal" else "offsettime"
            explicit_offset = str(values[offset_key][0]) if values.get(offset_key) else None
            candidates.append(
                _candidate(
                    source, str(raw_value), parsed, priority, confidence,
                    "METADATA", default_timezone, explicit_offset,
                    "DATE" if re.fullmatch(r"\d{4}[:-]\d{2}[:-]\d{2}", str(raw_value)) else "SECOND",
                )
            )
    return candidates


def filename_candidates(filename: str, default_timezone: str | None) -> list[DateCandidate]:
    """Extract conservative date and optional time patterns from a filename."""
    for index, pattern in enumerate(FILENAME_PATTERNS):
        match = pattern.search(filename)
        if not match:
            continue
        parts = {
            key: int(match.groupdict().get(key) or 0)
            for key in ("year", "month", "day", "hour", "minute", "second")
        }
        try:
            parsed = datetime(
                parts["year"], parts["month"], parts["day"],
                parts["hour"], parts["minute"], parts["second"],
            )
        except ValueError:
            continue
        has_time = index < 2
        return [
            _candidate(
                "FILENAME_DATE_TIME" if has_time else "FILENAME_DATE",
                match.group(0), parsed, 50 if has_time else 55,
                "MEDIUM" if has_time else "LOW", "FILENAME", default_timezone,
                precision="SECOND" if has_time else "DATE",
            )
        ]
    return []


def filesystem_candidates(
    birth_time_ns: int | None,
    modified_time_ns: int,
    default_timezone: str | None,
    enabled: bool,
) -> list[DateCandidate]:
    """Create low-confidence candidates from absolute filesystem instants."""
    if not enabled:
        return []
    zone = _timezone(default_timezone) or UTC
    result: list[DateCandidate] = []
    for source, value, priority in (
        ("FILESYSTEM_BIRTH_TIME", birth_time_ns, 80),
        ("FILESYSTEM_MODIFIED_TIME", modified_time_ns, 90),
    ):
        if value is None:
            continue
        utc_value = datetime.fromtimestamp(value / 1_000_000_000, UTC)
        local = utc_value.astimezone(zone)
        result.append(
            DateCandidate(
                source, str(value), local.replace(tzinfo=None), utc_value,
                default_timezone or "UTC", "FILESYSTEM", priority, "LOW", "FILESYSTEM",
            )
        )
    return result


def _comparable(candidate: DateCandidate) -> datetime:
    return candidate.utc_datetime or candidate.local_datetime.replace(tzinfo=UTC)


def resolve_date(
    candidates: Iterable[DateCandidate],
    *,
    now: datetime,
    future_tolerance_days: int,
    conflict_tolerance_seconds: int,
    suspicious_year_at_or_before: int,
    filesystem_gap_days: int,
) -> DateResolution:
    """Select the best candidate and expose every reason requiring review."""
    ordered = tuple(sorted(candidates, key=lambda item: (item.priority, item.source, item.value)))
    if not ordered:
        return DateResolution("NO_DATE", None, (), ("NO_VALID_DATE_CANDIDATE",))
    selected = ordered[0]
    reasons: set[str] = set()
    if selected.timezone_ambiguous:
        reasons.add("AMBIGUOUS_LOCAL_TIME")
    if selected.timezone_nonexistent:
        reasons.add("NONEXISTENT_LOCAL_TIME")
    if selected.local_datetime.year <= suspicious_year_at_or_before:
        reasons.add("EARLY_YEAR")
    comparable_now = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
    if _comparable(selected) > comparable_now.astimezone(UTC) + timedelta(days=future_tolerance_days):
        reasons.add("FUTURE_DATE")

    metadata = [candidate for candidate in ordered if candidate.evidence_kind == "METADATA"]
    if len(metadata) > 1:
        earliest = min(_comparable(candidate) for candidate in metadata)
        latest = max(_comparable(candidate) for candidate in metadata)
        if (latest - earliest).total_seconds() > conflict_tolerance_seconds:
            reasons.add("CONTRADICTORY_METADATA")

    filesystem = [candidate for candidate in ordered if candidate.evidence_kind == "FILESYSTEM"]
    if selected.evidence_kind != "FILESYSTEM" and filesystem:
        latest_filesystem = max(_comparable(candidate) for candidate in filesystem)
        if latest_filesystem - _comparable(selected) > timedelta(days=filesystem_gap_days):
            reasons.add("FILESYSTEM_MUCH_LATER")

    if "CONTRADICTORY_METADATA" in reasons:
        status = "CONFLICT"
    elif reasons or selected.evidence_kind == "FILESYSTEM":
        if selected.evidence_kind == "FILESYSTEM":
            reasons.add("FILESYSTEM_ONLY")
        status = "SUSPICIOUS"
    else:
        status = "RESOLVED"
    return DateResolution(status, selected, ordered, tuple(sorted(reasons)))
