from pathlib import Path
import tempfile
import unittest

from media_toolkit.catalog.database import initialize_database
from media_toolkit.catalog.repositories import register_library, register_source
from media_toolkit.provenance.service import export_provenance
from media_toolkit.scan.service import ScanRequest, run_scan


class ProvenanceServiceTests(unittest.TestCase):
    def test_export_includes_immutable_path_and_source_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            root = base / "media"
            state = base / "state"
            root.mkdir()
            state.mkdir()
            (root / "photo.jpg").write_bytes(b"synthetic")
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
            output = state / "provenance.csv"

            count = export_provenance(
                database, "TEST", "Personal Media", output, "csv"
            )

            self.assertEqual(count, 1)
            rendered = output.read_text(encoding="utf-8")
            self.assertIn("original_relative_path", rendered)
            self.assertIn("photo.jpg", rendered)


if __name__ == "__main__":
    unittest.main()
