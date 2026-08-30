from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from media_toolkit.catalog.database import initialize_database, open_database
from media_toolkit.catalog.repositories import register_library, register_source
from media_toolkit.hashing.service import HashRequest, list_hashes, run_hashing, stream_sha256
from media_toolkit.scan.service import ScanRequest, run_scan


class HashingServiceTests(unittest.TestCase):
    def _setup(self, base: Path) -> tuple[Path, Path, tuple[Path, ...]]:
        root = base / "media"
        state = base / "state"
        root.mkdir()
        state.mkdir()
        (root / "first.jpg").write_bytes(b"same exact content")
        (root / "second.jpg").write_bytes(b"same exact content")
        (root / "clip.mov").write_bytes(b"different video content")
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

    def _request(
        self,
        root: Path,
        database: Path,
        generated: tuple[Path, ...],
        *,
        force: bool = False,
    ) -> HashRequest:
        return HashRequest(
            database, "TEST", "Personal Media", "Synthetic", root, "all",
            1, 3, generated, force,
        )

    def test_stream_sha256_uses_bounded_chunks_and_counts_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "fixture.bin"
            content = b"0123456789abcdef"
            path.write_bytes(content)

            digest, byte_count = stream_sha256(path, 3)

            self.assertEqual(digest, sha256(content).hexdigest())
            self.assertEqual(byte_count, len(content))

    def test_hashes_all_files_without_changing_media(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root, database, generated = self._setup(Path(temporary_directory))
            before = {
                path.name: (sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
                for path in root.iterdir()
            }

            summary = run_hashing(self._request(root, database, generated))
            rows = list_hashes(database, "TEST", "Personal Media", "Synthetic")

            after = {
                path.name: (sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
                for path in root.iterdir()
            }
            self.assertEqual(summary.selected_count, 3)
            self.assertEqual(summary.hashed_count, 3)
            self.assertEqual(summary.error_count, 0)
            self.assertEqual(summary.bytes_hashed, sum(path.stat().st_size for path in root.iterdir()))
            self.assertEqual(before, after)
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[1].digest, rows[2].digest)

    def test_unchanged_hashes_are_cached_and_force_preserves_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root, database, generated = self._setup(Path(temporary_directory))
            request = self._request(root, database, generated)
            run_hashing(request)

            cached = run_hashing(request)
            forced = run_hashing(self._request(root, database, generated, force=True))

            self.assertEqual(cached.cached_count, 3)
            self.assertEqual(cached.hashed_count, 0)
            self.assertEqual(forced.hashed_count, 3)
            with open_database(database) as connection:
                history_count = connection.execute(
                    "SELECT COUNT(*) AS count FROM hash_attempt"
                ).fetchone()["count"]
                current_count = connection.execute(
                    "SELECT COUNT(*) AS count FROM media_hash"
                ).fetchone()["count"]
            self.assertEqual(history_count, 6)
            self.assertEqual(current_count, 3)

    def test_changed_file_is_refused_and_other_files_continue(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root, database, generated = self._setup(Path(temporary_directory))
            (root / "first.jpg").write_bytes(b"changed after scan")

            summary = run_hashing(self._request(root, database, generated))

            self.assertEqual(summary.hashed_count, 2)
            self.assertEqual(summary.error_count, 1)
            with open_database(database) as connection:
                error = connection.execute(
                    "SELECT error_message FROM hash_attempt WHERE status = 'ERROR'"
                ).fetchone()["error_message"]
            self.assertIn("run scan again", error)


if __name__ == "__main__":
    unittest.main()
