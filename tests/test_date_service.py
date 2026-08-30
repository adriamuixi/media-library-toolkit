from datetime import UTC, datetime
import json
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from media_toolkit.catalog.database import initialize_database, open_database
from media_toolkit.catalog.repositories import register_library, register_source
from media_toolkit.dates.service import (
    DateResolutionRequest,
    list_date_resolutions,
    run_date_resolution,
)
from media_toolkit.scan.service import ScanRequest, run_scan


class DateServiceTests(unittest.TestCase):
    def _setup(self, base: Path) -> tuple[Path, Path]:
        root = base / "media"
        state = base / "state"
        root.mkdir()
        state.mkdir()
        (root / "photo.jpg").write_bytes(b"photo")
        (root / "unknown.jpg").write_bytes(b"unknown")
        database = state / "catalog.sqlite3"
        initialize_database(database, "test", "TEST")
        register_library(database, "TEST", "Personal Media")
        register_source(
            database, "TEST", "Personal Media", "Old Disk", "OLD_DISK", "Europe/Madrid"
        )
        generated = (state, state / "logs", state / "reports", state / "cache", database)
        run_scan(
            ScanRequest(
                database, "TEST", "Personal Media", "Old Disk", root, "all",
                False, 10, generated,
            )
        )
        with open_database(database) as connection:
            row = connection.execute(
                """
                SELECT fl.location_id, fl.media_id, fl.size_bytes, fl.modified_time_ns
                FROM file_location AS fl
                WHERE fl.relative_path = 'photo.jpg'
                """
            ).fetchone()
            connection.execute(
                """
                INSERT INTO metadata_extraction (
                    extraction_id, media_id, location_id, extractor, extractor_version,
                    status, input_size_bytes, input_modified_time_ns, config_signature,
                    extracted_at, raw_metadata_json
                ) VALUES (?, ?, ?, 'EXIFTOOL', '13.0', 'SUCCESS', ?, ?, 'test', ?, ?)
                """,
                (
                    str(uuid4()), row["media_id"], row["location_id"], row["size_bytes"],
                    row["modified_time_ns"], datetime.now(UTC).isoformat(),
                    json.dumps({"EXIF:DateTimeOriginal": "2012:12:31 23:58:12"}),
                ),
            )
        return root, database

    def _request(self, database: Path, *, force: bool = False) -> DateResolutionRequest:
        return DateResolutionRequest(
            database=database,
            environment="TEST",
            library_name="Personal Media",
            source_name="Old Disk",
            media_filter="all",
            batch_size=1,
            future_tolerance_days=2,
            conflict_tolerance_seconds=86400,
            suspicious_year_at_or_before=1980,
            filesystem_gap_days=3650,
            allow_filesystem_fallback=False,
            force=force,
        )

    def test_persists_resolved_and_no_date_states(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            _, database = self._setup(Path(temporary_directory))

            summary = run_date_resolution(
                self._request(database), now=datetime(2026, 1, 1, tzinfo=UTC)
            )
            rows = list_date_resolutions(
                database, "TEST", "Personal Media", "Old Disk"
            )

            self.assertEqual(summary.selected_count, 2)
            self.assertEqual(summary.resolved_count, 1)
            self.assertEqual(summary.no_date_count, 1)
            self.assertEqual([row.status for row in rows], ["RESOLVED", "NO_DATE"])
            self.assertEqual(rows[0].capture_date_source, "EXIF_DATETIME_ORIGINAL")
            self.assertEqual(rows[0].capture_timezone, "Europe/Madrid")
            self.assertEqual(rows[1].capture_date_confidence, "UNKNOWN")

    def test_unchanged_inputs_are_cached_and_force_preserves_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            _, database = self._setup(Path(temporary_directory))
            request = self._request(database)
            run_date_resolution(request, now=datetime(2026, 1, 1, tzinfo=UTC))

            cached = run_date_resolution(request, now=datetime(2026, 1, 1, tzinfo=UTC))
            forced = run_date_resolution(
                self._request(database, force=True),
                now=datetime(2026, 1, 1, tzinfo=UTC),
            )

            self.assertEqual(cached.cached_count, 2)
            self.assertEqual(forced.cached_count, 0)
            with open_database(database) as connection:
                history_count = connection.execute(
                    "SELECT COUNT(*) AS count FROM date_resolution_attempt"
                ).fetchone()["count"]
                current_count = connection.execute(
                    "SELECT COUNT(*) AS count FROM media_date_resolution"
                ).fetchone()["count"]
            self.assertEqual(history_count, 4)
            self.assertEqual(current_count, 2)


if __name__ == "__main__":
    unittest.main()
