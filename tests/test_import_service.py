from pathlib import Path
import tempfile
import unittest

from media_toolkit.catalog.database import initialize_database
from media_toolkit.catalog.repositories import register_import_batch, register_library, register_source
from media_toolkit.errors import CatalogError
from media_toolkit.imports.service import get_import_batch_summary, verify_import_batch
from media_toolkit.scan.service import ScanRequest, run_scan


class ImportServiceTests(unittest.TestCase):
    def test_summary_preserves_incomplete_batch_state_and_refuses_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            root = base / "toAnalyze"
            state = base / "state"
            root.mkdir()
            state.mkdir()
            (root / "example.bin").write_bytes(b"incremental import")
            database = state / "catalog.sqlite3"
            initialize_database(database, "test", "TEST")
            register_library(database, "TEST", "Personal Media")
            register_source(database, "TEST", "Personal Media", "Queue", "TO_ANALYZE")
            register_import_batch(database, "TEST", "Personal Media", "Queue", "QUEUE_001")
            run_scan(ScanRequest(
                database, "TEST", "Personal Media", "Queue", root, "all", False, 10,
                (state, state / "logs", state / "reports", state / "cache"),
                import_batch_name="QUEUE_001",
            ))

            summary = get_import_batch_summary(database, "TEST", "Personal Media", "QUEUE_001")

            self.assertEqual(summary.observation_count, 1)
            self.assertEqual(summary.hashed_count, 0)
            with self.assertRaises(CatalogError):
                verify_import_batch(database, "TEST", "Personal Media", "QUEUE_001")


if __name__ == "__main__":
    unittest.main()
