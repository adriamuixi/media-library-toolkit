from pathlib import Path
import tempfile
import unittest

from media_toolkit.catalog.database import initialize_database
from media_toolkit.catalog.repositories import register_library, register_source
from media_toolkit.duplicates.service import list_size_candidates
from media_toolkit.scan.service import ScanRequest, run_scan


class DuplicateServiceTests(unittest.TestCase):
    def _setup(self, base: Path) -> Path:
        root = base / "media"
        state = base / "state"
        root.mkdir()
        state.mkdir()
        (root / "first.jpg").write_bytes(b"same-size-a")
        (root / "second.jpg").write_bytes(b"same-size-b")
        (root / "clip.mov").write_bytes(b"video")
        database = state / "catalog.sqlite3"
        initialize_database(database, "test", "TEST")
        register_library(database, "TEST", "Personal Media")
        register_source(database, "TEST", "Personal Media", "Synthetic", "CAMERA", None)
        generated = (state, state / "logs", state / "reports", state / "cache", database)
        run_scan(
            ScanRequest(
                database, "TEST", "Personal Media", "Synthetic", root, "all",
                False, 10, generated,
            )
        )
        return database

    def test_same_size_files_are_candidates_without_duplicate_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = self._setup(Path(temporary_directory))

            groups = list_size_candidates(database, "TEST", "Personal Media", "all")

            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0].size_bytes, len(b"same-size-a"))
            self.assertEqual(
                [member.relative_path for member in groups[0].members],
                ["first.jpg", "second.jpg"],
            )
            self.assertEqual({member.sha256 for member in groups[0].members}, {None})

    def test_media_type_filter_excludes_photo_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = self._setup(Path(temporary_directory))

            groups = list_size_candidates(database, "TEST", "Personal Media", "videos")

            self.assertEqual(groups, [])


if __name__ == "__main__":
    unittest.main()
