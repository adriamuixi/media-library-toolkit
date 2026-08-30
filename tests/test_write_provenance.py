from pathlib import Path
import tempfile
import unittest

from media_toolkit.catalog.database import initialize_database, open_database
from media_toolkit.catalog.repositories import register_library, register_source
from media_toolkit.errors import CatalogError
from media_toolkit.hashing.service import HashRequest, run_hashing
from media_toolkit.operations.provenance import require_write_provenance
from media_toolkit.scan.service import ScanRequest, run_scan


class WriteProvenanceTests(unittest.TestCase):
    def test_requires_complete_provenance_and_logical_identity(self) -> None:
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
            generated = (state, state / "logs", state / "reports", state / "cache")
            run_scan(
                ScanRequest(
                    database, "TEST", "Personal Media", "Synthetic", root, "all",
                    False, 10, generated,
                )
            )
            with open_database(database) as connection:
                media_id = connection.execute(
                    "SELECT media_id FROM media_file"
                ).fetchone()["media_id"]
            with self.assertRaises(CatalogError):
                require_write_provenance(database, "TEST", (media_id,))
            run_hashing(
                HashRequest(
                    database, "TEST", "Personal Media", "Synthetic", root, "all",
                    10, 1024, generated,
                )
            )
            require_write_provenance(database, "TEST", (media_id,))


if __name__ == "__main__":
    unittest.main()
