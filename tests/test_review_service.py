from pathlib import Path
import tempfile
import unittest

from media_toolkit.catalog.database import initialize_database, open_database
from media_toolkit.catalog.repositories import register_library, register_source
from media_toolkit.review.service import apply_manual_date_resolution
from media_toolkit.scan.service import ScanRequest, run_scan


class ReviewServiceTests(unittest.TestCase):
    def test_manual_date_decision_is_audited_and_replaces_only_current_resolution(self) -> None:
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
            with open_database(database) as connection:
                media_id = connection.execute("SELECT media_id FROM media_file").fetchone()["media_id"]

            decision_id = apply_manual_date_resolution(
                database, "TEST", media_id, "2012-12-31T23:58:12",
                "Verified against family album.", "local-reviewer",
            )

            with open_database(database) as connection:
                decision = connection.execute(
                    "SELECT reason, decided_by FROM manual_review_decision WHERE decision_id = ?",
                    (decision_id,),
                ).fetchone()
                resolution = connection.execute(
                    """
                    SELECT attempt.effective_capture_local, attempt.capture_date_source
                    FROM media_date_resolution AS current
                    JOIN date_resolution_attempt AS attempt
                      ON attempt.resolution_id = current.resolution_id
                    WHERE current.media_id = ?
                    """,
                    (media_id,),
                ).fetchone()
            self.assertEqual(decision["reason"], "Verified against family album.")
            self.assertEqual(decision["decided_by"], "local-reviewer")
            self.assertEqual(resolution["effective_capture_local"], "2012-12-31T23:58:12")
            self.assertEqual(resolution["capture_date_source"], "MANUAL")


if __name__ == "__main__":
    unittest.main()
