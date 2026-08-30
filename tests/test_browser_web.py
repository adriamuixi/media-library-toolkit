from pathlib import Path
import sqlite3
import tempfile
import unittest

from PIL import Image

from media_toolkit.browser.web import BrowserMedia, _filtered_entries, create_browser_app
from media_toolkit.catalog.database import (
    initialize_database,
    open_database,
    open_readonly_database,
)
from media_toolkit.catalog.repositories import register_library, register_source
from media_toolkit.scan.service import ScanRequest, run_scan


class BrowserWebTests(unittest.TestCase):
    def test_browser_reads_photos_caches_thumbnails_and_excludes_to_analyze(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            root = base / "media"
            state = base / "state"
            (root / "2024").mkdir(parents=True)
            (root / "toAnalyze").mkdir()
            state.mkdir()
            whatsapp_name = "IMG-20240101-WA0001.jpg"
            Image.new("RGB", (1200, 800), color="navy").save(root / "2024" / whatsapp_name)
            Image.new("RGB", (1000, 700), color="green").save(root / "2024" / "second.jpg")
            Image.new("RGB", (800, 1200), color="red").save(root / "toAnalyze" / "private.jpg")
            database = state / "catalog.sqlite3"
            initialize_database(database, "test", "TEST")
            register_library(database, "TEST", "Personal Media")
            register_source(database, "TEST", "Personal Media", "Organized", "MASTER_LIBRARY")
            run_scan(
                ScanRequest(
                    database, "TEST", "Personal Media", "Organized", root, "all", False,
                    10, (state, state / "logs", state / "reports", state / "cache"),
                )
            )
            with open_database(database) as connection:
                visible_id = connection.execute(
                    "SELECT media_id FROM media_file WHERE original_filename = ?",
                    (whatsapp_name,),
                ).fetchone()["media_id"]
                hidden_id = connection.execute(
                    "SELECT media_id FROM media_file WHERE original_filename = 'private.jpg'"
                ).fetchone()["media_id"]
                second_id = connection.execute(
                    "SELECT media_id FROM media_file WHERE original_filename = 'second.jpg'"
                ).fetchone()["media_id"]
            application = create_browser_app(
                database, "TEST", "Personal Media", root, state / "cache"
            )
            client = application.test_client()

            gallery = client.get("/")
            gallery_200 = client.get("/?page_size=200")
            invalid_page_size = client.get("/?page_size=60")
            detail = client.get(f"/media/{visible_id}")
            second_detail = client.get(f"/media/{second_id}")
            thumbnail = client.get(f"/media/{visible_id}/thumbnail")
            content = client.get(f"/media/{visible_id}/content")
            excluded_detail = client.get(f"/media/{hidden_id}")

            self.assertEqual(gallery.status_code, 200)
            self.assertEqual(gallery_200.status_code, 200)
            self.assertIn(b"Up to 200 entries per page", gallery_200.data)
            self.assertEqual(invalid_page_size.status_code, 400)
            self.assertIn(b'name="page_size"', gallery.data)
            self.assertIn(b"100 per page", gallery.data)
            self.assertIn(b"200 per page", gallery.data)
            self.assertIn(b"500 per page", gallery.data)
            self.assertIn(f"2024/{whatsapp_name}".encode(), gallery.data)
            self.assertIn(b'class="whatsapp-origin-icon"', gallery.data)
            self.assertIn(b'aria-label="WhatsApp evidence"', gallery.data)
            self.assertNotIn(b"toAnalyze/private.jpg", gallery.data)
            self.assertIn(b"http://127.0.0.1:8082", gallery.data)
            self.assertIn(b'name="min_width"', gallery.data)
            self.assertIn(b'name="max_height"', gallery.data)
            self.assertIn(b'name="min_aspect"', gallery.data)
            self.assertIn(b'name="panorama"', gallery.data)
            self.assertIn(b'name="orientation"', gallery.data)
            self.assertIn(b'name="source_type"', gallery.data)
            self.assertIn(b'name="whatsapp"', gallery.data)
            self.assertEqual(detail.status_code, 200)
            self.assertIn(b'class="whatsapp-detail-icon"', detail.data)
            self.assertIn(b'id="preview-next-link"', detail.data)
            self.assertIn(b'aria-label="Next media"', detail.data)
            self.assertIn(b'id="preview-previous-link"', second_detail.data)
            self.assertIn(b'aria-label="Previous media"', second_detail.data)
            self.assertIn(b"ArrowLeft", detail.data)
            self.assertIn(b"ArrowRight", detail.data)
            self.assertIn(b"Complete catalog information", detail.data)
            self.assertIn(b"Media identity", detail.data)
            self.assertIn(b"Current file locations", detail.data)
            self.assertIn(b"Technical metadata", detail.data)
            self.assertIn(b"Capture-date resolution history", detail.data)
            self.assertIn(b"Metadata extraction history and raw evidence", detail.data)
            self.assertIn(visible_id.encode(), detail.data)
            self.assertIn(b"modified time ns", detail.data)
            self.assertEqual(thumbnail.status_code, 200)
            self.assertEqual(thumbnail.mimetype, "image/jpeg")
            self.assertEqual(content.status_code, 200)
            self.assertEqual(excluded_detail.status_code, 404)
            self.assertTrue(any((state / "cache" / "media-browser-thumbnails").rglob("*.jpg")))
            self.assertEqual(
                sorted(root.rglob("*.jpg")),
                [
                    root / "2024" / whatsapp_name,
                    root / "2024" / "second.jpg",
                    root / "toAnalyze" / "private.jpg",
                ],
            )
            thumbnail.close()
            content.close()

    def test_readonly_catalog_connection_refuses_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "catalog.sqlite3"
            initialize_database(database, "test", "TEST")
            with open_readonly_database(database) as connection:
                with self.assertRaises(sqlite3.OperationalError):
                    connection.execute("CREATE TABLE browser_write_attempt (value TEXT)")

    def test_filtering_remains_bounded_for_a_large_catalog_shape(self) -> None:
        entry = BrowserMedia(
            "media", "2024/IMG.jpg", "PHOTO", "jpg", "PRESENT", "2024-01-01T10:00:00",
            "Camera", "BATCH", "IMG.jpg", "2024/IMG.jpg", 1,
            "WHATSAPP", 8000, 2000, 4.0, "LANDSCAPE", True,
            True, "FILENAME_PATTERN",
        )
        entries = [entry] * 100_000
        filtered = _filtered_entries(
            entries,
            {
                "year": "2024",
                "q": "img",
                "source_type": "WHATSAPP",
                "min_width": "8000",
                "max_height": "2000",
                "min_aspect": "4",
                "panorama": "yes",
                "orientation": "LANDSCAPE",
                "whatsapp": "yes",
            },
        )
        self.assertEqual(len(filtered), 100_000)

        self.assertEqual(
            _filtered_entries(entries, {"min_width": "8001"}),
            [],
        )
        self.assertEqual(
            _filtered_entries(entries, {"panorama": "no"}),
            [],
        )
        self.assertEqual(
            _filtered_entries(entries, {"whatsapp": "no"}),
            [],
        )


if __name__ == "__main__":
    unittest.main()
