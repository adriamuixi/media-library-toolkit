from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from media_toolkit.catalog.database import initialize_database, open_database
from media_toolkit.catalog.repositories import register_library, register_source
from media_toolkit.metadata.models import AdapterExtraction, NormalizedMetadata, ToolStatus
from media_toolkit.metadata.service import MetadataRequest, run_metadata
from media_toolkit.scan.service import ScanRequest, run_scan


class FakeAdapter:
    def __init__(
        self,
        extractor_name: str,
        normalized: NormalizedMetadata,
        *,
        available: bool = True,
    ):
        self.extractor_name = extractor_name
        self.normalized = normalized
        self.available = available
        self.calls = 0

    def status(self) -> ToolStatus:
        return ToolStatus(
            self.extractor_name,
            "/synthetic/tool",
            self.available,
            "1.0" if self.available else None,
            None if self.available else "Executable was not found.",
        )

    def extract(self, path: Path, status: ToolStatus) -> AdapterExtraction:
        self.calls += 1
        return AdapterExtraction(
            raw_metadata={"SyntheticPath": path.name, "Version": status.version},
            normalized=self.normalized,
        )


class MetadataServiceTests(unittest.TestCase):
    def _setup(self, base: Path) -> tuple[Path, Path, tuple[Path, ...]]:
        root = base / "media"
        state = base / "state"
        root.mkdir()
        state.mkdir()
        (root / "photo.jpg").write_bytes(b"synthetic photo")
        (root / "video.mov").write_bytes(b"synthetic video")
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
        self, root: Path, database: Path, generated: tuple[Path, ...], *, force: bool = False
    ) -> MetadataRequest:
        return MetadataRequest(
            database, "TEST", "Personal Media", "Synthetic", root, "all", 1,
            generated, 4.0, 2000, 10, "exiftool", "ffprobe", force,
        )

    def _adapters(self) -> dict[str, FakeAdapter]:
        return {
            "PHOTO": FakeAdapter(
                "EXIFTOOL",
                NormalizedMetadata(
                    stored_width_px=4000, stored_height_px=3000,
                    display_width_px=4000, display_height_px=3000,
                    megapixels=12.0, aspect_ratio=1.33333333,
                    orientation_class="LANDSCAPE", panorama_reason="NOT_PANORAMIC",
                    camera_model="Synthetic Camera",
                ),
            ),
            "VIDEO": FakeAdapter(
                "FFPROBE",
                NormalizedMetadata(
                    stored_width_px=1920, stored_height_px=1080,
                    display_width_px=1920, display_height_px=1080,
                    megapixels=2.0736, aspect_ratio=1.77777778,
                    orientation_class="LANDSCAPE", panorama_reason="NOT_PANORAMIC",
                    duration_ms=4321, video_codec="h264", audio_codec="aac",
                ),
            ),
        }

    def test_extracts_queryable_and_raw_metadata_without_changing_media(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root, database, generated = self._setup(Path(temporary_directory))
            before = {
                path.name: (sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
                for path in root.iterdir()
            }

            summary = run_metadata(self._request(root, database, generated), self._adapters())

            after = {
                path.name: (sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
                for path in root.iterdir()
            }
            self.assertEqual(summary.extracted_count, 2)
            self.assertEqual(summary.error_count, 0)
            self.assertEqual(before, after)
            with open_database(database) as connection:
                rows = connection.execute(
                    "SELECT duration_ms, stored_width_px FROM media_metadata ORDER BY duration_ms"
                ).fetchall()
                raw = connection.execute(
                    "SELECT raw_metadata_json FROM metadata_extraction WHERE status = 'SUCCESS'"
                ).fetchall()
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[1]["duration_ms"], 4321)
            self.assertTrue(all("SyntheticPath" in row["raw_metadata_json"] for row in raw))

    def test_successful_results_are_cached_and_force_bypasses_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root, database, generated = self._setup(Path(temporary_directory))
            adapters = self._adapters()
            run_metadata(self._request(root, database, generated), adapters)

            cached = run_metadata(self._request(root, database, generated), adapters)
            forced = run_metadata(
                self._request(root, database, generated, force=True), adapters
            )

            self.assertEqual(cached.cached_count, 2)
            self.assertEqual(cached.extracted_count, 0)
            self.assertEqual(forced.extracted_count, 2)
            self.assertEqual(adapters["PHOTO"].calls, 2)
            self.assertEqual(adapters["VIDEO"].calls, 2)

    def test_changed_file_is_recorded_as_error_and_not_extracted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root, database, generated = self._setup(Path(temporary_directory))
            (root / "photo.jpg").write_bytes(b"changed after scan")
            adapters = self._adapters()

            summary = run_metadata(self._request(root, database, generated), adapters)

            self.assertEqual(summary.error_count, 1)
            self.assertEqual(summary.extracted_count, 1)
            self.assertEqual(adapters["PHOTO"].calls, 0)
            with open_database(database) as connection:
                error = connection.execute(
                    "SELECT error_message FROM metadata_extraction WHERE status = 'ERROR'"
                ).fetchone()
            self.assertIn("run scan again", error["error_message"])

    def test_unavailable_photo_tool_does_not_block_video_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root, database, generated = self._setup(Path(temporary_directory))
            adapters = self._adapters()
            photo = adapters["PHOTO"]
            adapters["PHOTO"] = FakeAdapter(
                photo.extractor_name,
                photo.normalized,
                available=False,
            )

            summary = run_metadata(self._request(root, database, generated), adapters)

            self.assertEqual(summary.extracted_count, 1)
            self.assertEqual(summary.error_count, 1)
            self.assertEqual(adapters["VIDEO"].calls, 1)
            with open_database(database) as connection:
                error_type = connection.execute(
                    "SELECT error_type FROM metadata_extraction WHERE status = 'ERROR'"
                ).fetchone()["error_type"]
            self.assertEqual(error_type, "TOOL_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
