# Effective Capture Dates

## Stored Result

Each current media item receives one of four states:

```text
RESOLVED
SUSPICIOUS
CONFLICT
NO_DATE
```

A selected date retains its local wall-clock value, UTC instant when calculable, timezone name, timezone source, capture-date source, `SECOND`, `DATE`, or `UNKNOWN` precision, and `HIGH`, `MEDIUM`, `LOW`, or `UNKNOWN` confidence. Every candidate remains in immutable resolution history. Date-only filename evidence is explicitly marked `DATE`; its storage representation must never be interpreted as a genuine midnight capture time.

## Photo Priority

The initial photo hierarchy is:

1. EXIF `DateTimeOriginal`;
2. EXIF `CreateDate`;
3. equivalent `DateCreated` metadata;
4. GPS date and time;
5. conservative date and time parsed from the filename;
6. conservative date-only filename pattern;
7. optional filesystem birth and modification times.

## Video Priority

The initial video hierarchy is:

1. Apple QuickTime creation date;
2. media creation date;
3. container `creation_time`;
4. QuickTime create date;
5. encoded or tagged date;
6. conservative filename evidence;
7. optional filesystem evidence.

Priorities select a candidate but never delete lower-priority evidence.

## Timezones

An offset embedded in metadata is authoritative for conversion. Otherwise, the registered source's IANA timezone is applied while the unmodified local time remains stored. If neither is available, local time remains useful but UTC stays null.

Ambiguous and nonexistent daylight-saving local times are deterministic but marked for review. The catalog records whether timezone information came from `METADATA`, `SOURCE`, `FILESYSTEM`, or remained `UNKNOWN`.

## Review Rules

The initial configurable rules mark dates for review when:

- the selected year is at or before 1980;
- the date exceeds the allowed future tolerance;
- metadata candidates differ beyond the conflict tolerance;
- a filesystem time is much later than stronger capture evidence;
- source-timezone conversion is ambiguous or nonexistent;
- filesystem evidence is the only selected source.

Contradictory metadata produces `CONFLICT`. Other review reasons produce `SUSPICIOUS`. Missing valid evidence produces `NO_DATE`; the system does not invent a value.

Filesystem fallback is disabled by default. It can be enabled in configuration for targeted recovery work, but its result remains low-confidence and suspicious.
