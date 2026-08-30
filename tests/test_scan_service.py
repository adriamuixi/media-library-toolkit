from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from media_toolkit.catalog.database import initialize_database, open_database
from media_toolkit.catalog.repositories import register_library, register_source
from media_toolkit.errors import MediaToolkitError
from media_toolkit.scan.service import ScanRequest, run_scan


class ScanServiceTests(unittest.TestCase):
    def _setup(self, base: Path) -> tuple[Path, Path, tuple[Path, ...]]:
        media_root = base / "media"
        state_root = base / "state"
        media_root.mkdir()
        state_root.mkdir()
        database = state_root / "catalog.sqlite3"
        initialize_database(database, "test", "TEST")
        register_library(database, "TEST", "Personal Media")
        register_source(
            database,
            "TEST",
            "Personal Media",
            "Synthetic Camera",
            "CAMERA",
            "Europe/Madrid",
        )
        generated_paths = (
            state_root,
            state_root / "logs",
            state_root / "reports",
            state_root / "cache",
            database,
        )
        return media_root, database, generated_paths

    def _request(
        self,
        media_root: Path,
        database: Path,
        generated_paths: tuple[Path, ...],
        *,
        media_filter: str = "all",
        include_hidden: bool = False,
        batch_size: int = 2,
    ) -> ScanRequest:
        return ScanRequest(
            database=database,
            environment="TEST",
            library_name="Personal Media",
            source_name="Synthetic Camera",
            root=media_root,
            media_filter=media_filter,
            include_hidden=include_hidden,
            batch_size=batch_size,
            generated_paths=generated_paths,
        )

    def _create_fixture_files(self, media_root: Path) -> None:
        nested = media_root / "nested"
        nested.mkdir()
        (media_root / "photo.JPG").write_bytes(b"synthetic-photo")
        (nested / "clip.MOV").write_bytes(b"synthetic-video")
        (nested / "photo.XMP").write_text("synthetic sidecar", encoding="utf-8")
        (media_root / "notes.txt").write_text("synthetic unknown", encoding="utf-8")
        (media_root / ".hidden.jpg").write_bytes(b"synthetic-hidden")

    def test_scan_catalogs_relative_paths_and_all_basic_types(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            media_root, database, generated_paths = self._setup(
                Path(temporary_directory)
            )
            self._create_fixture_files(media_root)

            summary = run_scan(
                self._request(media_root, database, generated_paths)
            )

            self.assertEqual(summary.status, "COMPLETED")
            self.assertEqual(summary.discovered_count, 4)
            self.assertEqual(summary.new_count, 4)
            self.assertEqual(summary.updated_count, 0)
            self.assertEqual(summary.skipped_count, 1)
            with open_database(database) as connection:
                rows = connection.execute(
                    """
                    SELECT fl.relative_path, mf.media_type
                    FROM file_location AS fl
                    JOIN media_file AS mf ON mf.media_id = fl.media_id
                    ORDER BY fl.relative_path
                    """
                ).fetchall()
            self.assertEqual(
                [(row["relative_path"], row["media_type"]) for row in rows],
                [
                    ("nested/clip.MOV", "VIDEO"),
                    ("nested/photo.XMP", "SIDECAR"),
                    ("notes.txt", "UNKNOWN"),
                    ("photo.JPG", "PHOTO"),
                ],
            )
            self.assertTrue(all(not Path(row["relative_path"]).is_absolute() for row in rows))

    def test_repeated_scan_is_idempotent_and_preserves_media_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            media_root, database, generated_paths = self._setup(
                Path(temporary_directory)
            )
            self._create_fixture_files(media_root)
            request = self._request(media_root, database, generated_paths)

            first = run_scan(request)
            with open_database(database) as connection:
                first_ids = {
                    row["relative_path"]: row["media_id"]
                    for row in connection.execute(
                        "SELECT relative_path, media_id FROM file_location"
                    )
                }
            second = run_scan(request)
            with open_database(database) as connection:
                second_ids = {
                    row["relative_path"]: row["media_id"]
                    for row in connection.execute(
                        "SELECT relative_path, media_id FROM file_location"
                    )
                }
                media_count = connection.execute(
                    "SELECT COUNT(*) AS count FROM media_file"
                ).fetchone()["count"]

            self.assertEqual(first.new_count, 4)
            self.assertEqual(second.new_count, 0)
            self.assertEqual(second.updated_count, 4)
            self.assertEqual(media_count, 4)
            self.assertEqual(first_ids, second_ids)

    def test_photo_filter_only_catalogs_photos(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            media_root, database, generated_paths = self._setup(
                Path(temporary_directory)
            )
            self._create_fixture_files(media_root)

            summary = run_scan(
                self._request(
                    media_root,
                    database,
                    generated_paths,
                    media_filter="photos",
                )
            )

            self.assertEqual(summary.discovered_count, 1)
            with open_database(database) as connection:
                media_types = [
                    row["media_type"]
                    for row in connection.execute("SELECT media_type FROM media_file")
                ]
            self.assertEqual(media_types, ["PHOTO"])

    def test_scan_does_not_change_media_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            media_root, database, generated_paths = self._setup(
                Path(temporary_directory)
            )
            self._create_fixture_files(media_root)
            paths = sorted(path for path in media_root.rglob("*") if path.is_file())
            before = {
                path.relative_to(media_root).as_posix(): (
                    sha256(path.read_bytes()).hexdigest(),
                    path.stat().st_size,
                    path.stat().st_mtime_ns,
                )
                for path in paths
            }

            run_scan(self._request(media_root, database, generated_paths))

            after_paths = sorted(path for path in media_root.rglob("*") if path.is_file())
            after = {
                path.relative_to(media_root).as_posix(): (
                    sha256(path.read_bytes()).hexdigest(),
                    path.stat().st_size,
                    path.stat().st_mtime_ns,
                )
                for path in after_paths
            }
            self.assertEqual(before, after)

    def test_scan_rejects_generated_state_inside_media_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            media_root, database, generated_paths = self._setup(
                Path(temporary_directory)
            )
            unsafe_paths = generated_paths + (media_root / "cache",)

            with self.assertRaises(MediaToolkitError):
                run_scan(self._request(media_root, database, unsafe_paths))

            self.assertFalse((media_root / "cache").exists())

    def test_symlink_is_skipped_and_recorded_when_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            media_root, database, generated_paths = self._setup(
                Path(temporary_directory)
            )
            target = media_root / "target.jpg"
            target.write_bytes(b"synthetic-target")
            link = media_root / "linked.jpg"
            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest("Symbolic links are unavailable on this platform")

            summary = run_scan(
                self._request(media_root, database, generated_paths)
            )

            self.assertEqual(summary.discovered_count, 1)
            self.assertEqual(summary.warning_count, 1)
            with open_database(database) as connection:
                error_type = connection.execute(
                    "SELECT error_type FROM scan_error"
                ).fetchone()["error_type"]
            self.assertEqual(error_type, "SYMLINK_SKIPPED")


if __name__ == "__main__":
    unittest.main()
