from pathlib import Path
import tempfile
import unittest

from media_toolkit.catalog.database import initialize_database
from media_toolkit.catalog.repositories import register_library, register_source
from media_toolkit.duplicates.service import (
    ExactDuplicateMember,
    _exact_group,
    list_exact_duplicates,
    list_size_candidates,
)
from media_toolkit.hashing.service import HashRequest, run_hashing
from media_toolkit.scan.service import ScanRequest, run_scan


class DuplicateServiceTests(unittest.TestCase):
    def _setup(self, base: Path) -> Path:
        root = base / "media"
        state = base / "state"
        root.mkdir()
        state.mkdir()
        (root / "first.jpg").write_bytes(b"exact-content")
        (root / "second.jpg").write_bytes(b"exact-content")
        (root / "different.jpg").write_bytes(b"same-size-but-different")
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
        return root, database, generated

    def test_same_size_files_are_candidates_without_duplicate_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            _, database, _ = self._setup(Path(temporary_directory))

            groups = list_size_candidates(database, "TEST", "Personal Media", "all")

            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0].size_bytes, len(b"exact-content"))
            self.assertEqual(
                [member.relative_path for member in groups[0].members],
                ["first.jpg", "second.jpg"],
            )
            self.assertEqual({member.sha256 for member in groups[0].members}, {None})

    def test_media_type_filter_excludes_photo_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            _, database, _ = self._setup(Path(temporary_directory))

            groups = list_size_candidates(database, "TEST", "Personal Media", "videos")

            self.assertEqual(groups, [])

    def test_equal_sha256_values_create_exact_groups(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root, database, generated = self._setup(Path(temporary_directory))
            run_hashing(
                HashRequest(
                    database, "TEST", "Personal Media", "Synthetic", root, "all",
                    10, 1024, generated,
                )
            )

            groups = list_exact_duplicates(database, "TEST", "Personal Media", "all")

            self.assertEqual(len(groups), 1)
            self.assertEqual(len(groups[0].sha256), 64)
            self.assertEqual(
                [member.relative_path for member in groups[0].members],
                ["first.jpg", "second.jpg"],
            )
            self.assertEqual(groups[0].preference_status, "UNCONFIGURED")

    def test_unique_best_source_type_is_only_a_recommendation(self) -> None:
        members = [
            ExactDuplicateMember("camera", "Camera", "CAMERA", "a.jpg", "PHOTO", 1),
            ExactDuplicateMember(
                "master", "Master", "MASTER_LIBRARY", "b.jpg", "PHOTO", 1
            ),
        ]

        group = _exact_group("a" * 64, members, ("MASTER_LIBRARY", "CAMERA"))

        self.assertEqual(group.preferred_media_id, "master")
        self.assertEqual(group.preference_status, "SOURCE_TYPE")


if __name__ == "__main__":
    unittest.main()
