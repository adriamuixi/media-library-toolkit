from pathlib import Path
import tempfile
import unittest

from media_toolkit.catalog.database import initialize_database, open_database
from media_toolkit.catalog.repositories import register_library, register_source
from media_toolkit.planning.service import create_year_or_no_date_plan
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


if __name__ == "__main__":
    unittest.main()
