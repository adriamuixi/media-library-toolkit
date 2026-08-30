from pathlib import Path
import tempfile
import unittest

from media_toolkit.catalog.database import initialize_database, open_database
from media_toolkit.catalog.repositories import register_library, register_source
from media_toolkit.planning.service import create_year_or_no_date_plan, export_plan, list_plan_items
from media_toolkit.scan.service import ScanRequest, run_scan


class PlanningServiceTests(unittest.TestCase):
    def test_plan_uses_no_date_and_marks_destination_collisions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            root = base / "media"
            state = base / "state"
            (root / "one").mkdir(parents=True)
            (root / "two").mkdir()
            state.mkdir()
            (root / "one" / "IMG.jpg").write_bytes(b"one")
            (root / "two" / "IMG.jpg").write_bytes(b"two")
            database = state / "catalog.sqlite3"
            initialize_database(database, "test", "TEST")
            register_library(database, "TEST", "Personal Media")
            register_source(database, "TEST", "Personal Media", "Synthetic", "CAMERA")
            run_scan(
                ScanRequest(
                    database, "TEST", "Personal Media", "Synthetic", root, "all",
                    False, 10, (state, state / "logs", state / "reports", state / "cache"),
                )
            )

            summary = create_year_or_no_date_plan(database, "TEST", "Personal Media")

            self.assertEqual(summary.status, "REVIEW_REQUIRED")
            self.assertEqual(summary.conflict_count, 2)
            with open_database(database) as connection:
                rows = connection.execute(
                    "SELECT destination_relative_path, status FROM organization_plan_item"
                ).fetchall()
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(row["destination_relative_path"] == "no_date/IMG.jpg" for row in rows))
            self.assertTrue(all(row["status"] == "CONFLICT" for row in rows))
            with open_database(database) as connection:
                with self.assertRaisesRegex(Exception, "immutable"):
                    connection.execute(
                        "UPDATE organization_plan SET checksum = ? WHERE plan_id = ?",
                        ("0" * 64, summary.plan_id),
                    )
                with self.assertRaisesRegex(Exception, "immutable"):
                    connection.execute(
                        "UPDATE organization_plan_item SET status = 'PROPOSED' WHERE plan_id = ?",
                        (summary.plan_id,),
                    )

    def test_plan_keeps_detected_associations_in_the_primary_year(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            root = base / "media"
            state = base / "state"
            root.mkdir()
            state.mkdir()
            (root / "IMG.jpg").write_bytes(b"photo")
            (root / "IMG.mov").write_bytes(b"video")
            database = state / "catalog.sqlite3"
            initialize_database(database, "test", "TEST")
            register_library(database, "TEST", "Personal Media")
            register_source(database, "TEST", "Personal Media", "Synthetic", "CAMERA")
            run_scan(
                ScanRequest(
                    database, "TEST", "Personal Media", "Synthetic", root, "all",
                    False, 10, (state, state / "logs", state / "reports", state / "cache"),
                )
            )
            with open_database(database) as connection:
                source = connection.execute("SELECT source_id, library_id FROM source").fetchone()
                media = connection.execute(
                    "SELECT media_id FROM file_location ORDER BY relative_path"
                ).fetchall()
                photo_id, video_id = (row["media_id"] for row in media)
                connection.execute(
                    """
                    INSERT INTO date_resolution_attempt (
                        resolution_id, media_id, extraction_id, status,
                        effective_capture_local, effective_capture_at_utc,
                        capture_timezone, timezone_source, capture_date_source,
                        capture_date_precision, capture_date_confidence,
                        input_signature, candidates_json, reasons_json, resolved_at
                    ) VALUES (
                        'resolution-photo', ?, NULL, 'RESOLVED',
                        '2012-12-31T23:58:12', NULL, NULL, 'UNKNOWN', 'TEST',
                        'SECOND', 'HIGH', 'test', '[]', '[]', '2026-01-01T00:00:00+00:00'
                    )
                    """,
                    (photo_id,),
                )
                connection.execute(
                    "INSERT INTO media_date_resolution (media_id, resolution_id, updated_at) VALUES (?, 'resolution-photo', '2026-01-01T00:00:00+00:00')",
                    (photo_id,),
                )
                connection.execute(
                    """
                    INSERT INTO media_relation (
                        relation_id, library_id, source_id, primary_media_id,
                        companion_media_id, relation_type, confidence, status,
                        match_method, relation_key, details_json, active,
                        first_detected_at, last_detected_at
                    ) VALUES (
                        'relation-photo-video', ?, ?, ?, ?, 'LIVE_PHOTO_PAIR',
                        'HIGH', 'DETECTED', 'METADATA_IDENTIFIER', 'test',
                        '{}', 1, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
                    )
                    """,
                    (source["library_id"], source["source_id"], photo_id, video_id),
                )

            summary = create_year_or_no_date_plan(database, "TEST", "Personal Media")

            self.assertEqual(summary.status, "DRAFT")
            with open_database(database) as connection:
                rows = connection.execute(
                    "SELECT destination_relative_path, association_group_key, status FROM organization_plan_item ORDER BY destination_relative_path"
                ).fetchall()
            self.assertEqual(
                [row["destination_relative_path"] for row in rows],
                ["2012/IMG.jpg", "2012/IMG.mov"],
            )
            self.assertEqual(len({row["association_group_key"] for row in rows}), 1)
            self.assertTrue(all(row["status"] == "PROPOSED" for row in rows))

    def test_plan_can_be_listed_and_exported_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            root = base / "media"
            state = base / "state"
            root.mkdir()
            state.mkdir()
            (root / "IMG.jpg").write_bytes(b"photo")
            database = state / "catalog.sqlite3"
            initialize_database(database, "test", "TEST")
            register_library(database, "TEST", "Personal Media")
            register_source(database, "TEST", "Personal Media", "Synthetic", "CAMERA")
            run_scan(
                ScanRequest(
                    database, "TEST", "Personal Media", "Synthetic", root, "all",
                    False, 10, (state, state / "logs", state / "reports", state / "cache"),
                )
            )
            summary = create_year_or_no_date_plan(database, "TEST", "Personal Media")
            rows = list_plan_items(database, "TEST", summary.plan_id)
            output = base / "plan.json"
            count = export_plan(database, "TEST", summary.plan_id, output, "json")

            self.assertEqual(len(rows), 1)
            self.assertEqual(count, 1)
            self.assertTrue(output.is_file())
            with self.assertRaisesRegex(Exception, "already exists"):
                export_plan(database, "TEST", summary.plan_id, output, "json")

    def test_plan_blocks_active_ambiguous_associations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            root = base / "media"
            state = base / "state"
            root.mkdir()
            state.mkdir()
            (root / "IMG.jpg").write_bytes(b"photo")
            (root / "IMG.xmp").write_bytes(b"sidecar")
            database = state / "catalog.sqlite3"
            initialize_database(database, "test", "TEST")
            register_library(database, "TEST", "Personal Media")
            register_source(database, "TEST", "Personal Media", "Synthetic", "CAMERA")
            run_scan(
                ScanRequest(
                    database, "TEST", "Personal Media", "Synthetic", root, "all",
                    False, 10, (state, state / "logs", state / "reports", state / "cache"),
                )
            )
            with open_database(database) as connection:
                source = connection.execute("SELECT source_id, library_id FROM source").fetchone()
                media = connection.execute(
                    "SELECT media_id FROM file_location ORDER BY relative_path"
                ).fetchall()
                connection.execute(
                    """
                    INSERT INTO media_relation (
                        relation_id, library_id, source_id, primary_media_id,
                        companion_media_id, relation_type, confidence, status,
                        match_method, relation_key, details_json, active,
                        first_detected_at, last_detected_at
                    ) VALUES (
                        'relation-conflict', ?, ?, ?, ?, 'SIDECAR_ASSOCIATION',
                        'LOW', 'CONFLICT', 'BASENAME', 'test',
                        '{}', 1, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
                    )
                    """,
                    (source["library_id"], source["source_id"], media[0]["media_id"], media[1]["media_id"]),
                )

            summary = create_year_or_no_date_plan(database, "TEST", "Personal Media")

            self.assertEqual(summary.status, "REVIEW_REQUIRED")
            self.assertEqual(summary.conflict_count, 2)
            with open_database(database) as connection:
                rows = connection.execute(
                    "SELECT status, reason FROM organization_plan_item ORDER BY plan_item_id"
                ).fetchall()
            self.assertTrue(all(row["status"] == "BLOCKED" for row in rows))
            self.assertTrue(all(row["reason"] == "ASSOCIATION_CONFLICT" for row in rows))


if __name__ == "__main__":
    unittest.main()
