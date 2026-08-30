from pathlib import Path
import tempfile
import unittest

from media_toolkit.catalog.database import initialize_database, open_database
from media_toolkit.catalog.repositories import register_library, register_source
from media_toolkit.hashing.service import HashRequest, run_hashing
from media_toolkit.operations.write import apply_copy_plan, apply_move_plan
from media_toolkit.planning.service import create_year_or_no_date_plan
from media_toolkit.scan.service import ScanRequest, run_scan


class WriteOperationTests(unittest.TestCase):
    def test_copy_requires_exact_confirmation_and_verifies_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            source = base / "source"
            destination = base / "destination"
            state = base / "state"
            source.mkdir()
            destination.mkdir()
            state.mkdir()
            (source / "IMG.jpg").write_bytes(b"verified content")
            database = state / "catalog.sqlite3"
            initialize_database(database, "test", "TEST")
            register_library(database, "TEST", "Personal Media")
            register_source(database, "TEST", "Personal Media", "Synthetic", "CAMERA")
            generated = (state, state / "logs", state / "reports", state / "cache")
            run_scan(
                ScanRequest(
                    database, "TEST", "Personal Media", "Synthetic", source, "all",
                    False, 10, generated,
                )
            )
            run_hashing(
                HashRequest(
                    database, "TEST", "Personal Media", "Synthetic", source, "all",
                    10, 1024, generated, False,
                )
            )
            plan = create_year_or_no_date_plan(database, "TEST", "Personal Media")
            with self.assertRaisesRegex(Exception, "confirmation"):
                apply_copy_plan(database, "TEST", plan.plan_id, source, destination, "wrong")

            operation_id = apply_copy_plan(
                database, "TEST", plan.plan_id, source, destination, plan.plan_id
            )

            self.assertEqual((destination / "no_date" / "IMG.jpg").read_bytes(), b"verified content")
            self.assertEqual((source / "IMG.jpg").read_bytes(), b"verified content")
            with open_database(database) as connection:
                operation = connection.execute(
                    "SELECT status FROM write_operation WHERE operation_id = ?",
                    (operation_id,),
                ).fetchone()
                events = connection.execute(
                    "SELECT event_type FROM write_operation_event WHERE operation_id = ? ORDER BY recorded_at",
                    (operation_id,),
                ).fetchall()
                plan_status = connection.execute(
                    "SELECT status FROM organization_plan WHERE plan_id = ?",
                    (plan.plan_id,),
                ).fetchone()
            self.assertEqual(operation["status"], "COMPLETED")
            self.assertEqual(plan_status["status"], "APPLIED")
            self.assertEqual(
                [row["event_type"] for row in events],
                ["OPERATION_STARTED", "ITEM_COPIED", "OPERATION_COMPLETED"],
            )
            with self.assertRaisesRegex(Exception, "DRAFT"):
                apply_copy_plan(database, "TEST", plan.plan_id, source, destination, plan.plan_id)

    def test_move_removes_source_only_after_verified_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            source = base / "source"
            destination = base / "destination"
            state = base / "state"
            source.mkdir()
            destination.mkdir()
            state.mkdir()
            (source / "IMG.jpg").write_bytes(b"move verified content")
            database = state / "catalog.sqlite3"
            initialize_database(database, "test", "TEST")
            register_library(database, "TEST", "Personal Media")
            register_source(database, "TEST", "Personal Media", "Synthetic", "CAMERA")
            generated = (state, state / "logs", state / "reports", state / "cache")
            run_scan(
                ScanRequest(
                    database, "TEST", "Personal Media", "Synthetic", source, "all",
                    False, 10, generated,
                )
            )
            run_hashing(
                HashRequest(
                    database, "TEST", "Personal Media", "Synthetic", source, "all",
                    10, 1024, generated, False,
                )
            )
            plan = create_year_or_no_date_plan(database, "TEST", "Personal Media")

            operation_id = apply_move_plan(
                database, "TEST", plan.plan_id, source, destination, plan.plan_id
            )

            self.assertFalse((source / "IMG.jpg").exists())
            self.assertEqual((destination / "no_date" / "IMG.jpg").read_bytes(), b"move verified content")
            with open_database(database) as connection:
                events = connection.execute(
                    "SELECT event_type FROM write_operation_event WHERE operation_id = ? ORDER BY recorded_at",
                    (operation_id,),
                ).fetchall()
                location = connection.execute(
                    "SELECT current_relative_path FROM file_observation"
                ).fetchone()
                history = connection.execute(
                    "SELECT reason FROM observation_location_history ORDER BY recorded_at DESC LIMIT 1"
                ).fetchone()
            self.assertIn("ITEM_SOURCE_REMOVED", [row["event_type"] for row in events])
            self.assertEqual(location["current_relative_path"], "no_date/IMG.jpg")
            self.assertEqual(history["reason"], "FUTURE_OPERATION")


if __name__ == "__main__":
    unittest.main()
