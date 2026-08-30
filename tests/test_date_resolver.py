from datetime import UTC, datetime
import unittest

from media_toolkit.dates.resolver import (
    filename_candidates,
    filesystem_candidates,
    metadata_candidates,
    resolve_date,
)


class DateResolverTests(unittest.TestCase):
    def test_photo_original_date_wins_and_uses_source_timezone(self) -> None:
        raw = {
            "EXIF:DateTimeOriginal": "2012:12:31 23:58:12",
            "EXIF:CreateDate": "2013:01:01 00:00:00",
        }

        candidates = metadata_candidates(raw, "PHOTO", "Europe/Madrid")
        resolution = resolve_date(
            candidates,
            now=datetime(2026, 1, 1, tzinfo=UTC),
            future_tolerance_days=2,
            conflict_tolerance_seconds=86400,
            suspicious_year_at_or_before=1980,
            filesystem_gap_days=3650,
        )

        self.assertEqual(resolution.status, "RESOLVED")
        self.assertEqual(resolution.selected.source, "EXIF_DATETIME_ORIGINAL")
        self.assertEqual(
            resolution.selected.utc_datetime,
            datetime(2012, 12, 31, 22, 58, 12, tzinfo=UTC),
        )
        self.assertEqual(resolution.selected.timezone_source, "SOURCE")

    def test_contradictory_video_metadata_is_a_conflict(self) -> None:
        raw = {
            "format": {
                "tags": {
                    "com.apple.quicktime.creationdate": "2020-01-01T10:00:00Z",
                    "creation_time": "2021-01-01T10:00:00Z",
                }
            }
        }

        resolution = resolve_date(
            metadata_candidates(raw, "VIDEO", None),
            now=datetime(2026, 1, 1, tzinfo=UTC),
            future_tolerance_days=2,
            conflict_tolerance_seconds=86400,
            suspicious_year_at_or_before=1980,
            filesystem_gap_days=3650,
        )

        self.assertEqual(resolution.status, "CONFLICT")
        self.assertIn("CONTRADICTORY_METADATA", resolution.reasons)

    def test_filename_date_is_used_without_inventing_a_time(self) -> None:
        candidates = filename_candidates("IMG-20180705-WA0001.jpg", "Europe/Madrid")

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].source, "FILENAME_DATE")
        self.assertEqual(candidates[0].local_datetime, datetime(2018, 7, 5))
        self.assertEqual(candidates[0].confidence, "LOW")
        self.assertEqual(candidates[0].precision, "DATE")

    def test_future_and_early_dates_are_suspicious(self) -> None:
        future = metadata_candidates(
            {"EXIF:DateTimeOriginal": "2030:01:01 00:00:00"}, "PHOTO", "UTC"
        )
        early = metadata_candidates(
            {"EXIF:DateTimeOriginal": "1970:01:01 00:00:00"}, "PHOTO", "UTC"
        )

        future_resolution = resolve_date(
            future,
            now=datetime(2026, 1, 1, tzinfo=UTC),
            future_tolerance_days=2,
            conflict_tolerance_seconds=86400,
            suspicious_year_at_or_before=1980,
            filesystem_gap_days=3650,
        )
        early_resolution = resolve_date(
            early,
            now=datetime(2026, 1, 1, tzinfo=UTC),
            future_tolerance_days=2,
            conflict_tolerance_seconds=86400,
            suspicious_year_at_or_before=1980,
            filesystem_gap_days=3650,
        )

        self.assertEqual(future_resolution.status, "SUSPICIOUS")
        self.assertIn("FUTURE_DATE", future_resolution.reasons)
        self.assertEqual(early_resolution.status, "SUSPICIOUS")
        self.assertIn("EARLY_YEAR", early_resolution.reasons)

    def test_filesystem_fallback_is_explicit_and_suspicious(self) -> None:
        disabled = filesystem_candidates(None, 1_700_000_000_000_000_000, None, False)
        enabled = filesystem_candidates(None, 1_700_000_000_000_000_000, None, True)

        no_date = resolve_date(
            disabled,
            now=datetime(2026, 1, 1, tzinfo=UTC),
            future_tolerance_days=2,
            conflict_tolerance_seconds=86400,
            suspicious_year_at_or_before=1980,
            filesystem_gap_days=3650,
        )
        fallback = resolve_date(
            enabled,
            now=datetime(2026, 1, 1, tzinfo=UTC),
            future_tolerance_days=2,
            conflict_tolerance_seconds=86400,
            suspicious_year_at_or_before=1980,
            filesystem_gap_days=3650,
        )

        self.assertEqual(no_date.status, "NO_DATE")
        self.assertEqual(fallback.status, "SUSPICIOUS")
        self.assertIn("FILESYSTEM_ONLY", fallback.reasons)

    def test_ambiguous_source_timezone_requires_review(self) -> None:
        candidates = metadata_candidates(
            {"EXIF:DateTimeOriginal": "2025:10:26 02:30:00"},
            "PHOTO",
            "Europe/Madrid",
        )

        resolution = resolve_date(
            candidates,
            now=datetime(2026, 1, 1, tzinfo=UTC),
            future_tolerance_days=2,
            conflict_tolerance_seconds=86400,
            suspicious_year_at_or_before=1980,
            filesystem_gap_days=3650,
        )

        self.assertEqual(resolution.status, "SUSPICIOUS")
        self.assertIn("AMBIGUOUS_LOCAL_TIME", resolution.reasons)


if __name__ == "__main__":
    unittest.main()
