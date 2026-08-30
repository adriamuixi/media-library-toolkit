from pathlib import Path
import tempfile
import unittest

from PIL import Image
from media_toolkit.catalog.database import initialize_database
from media_toolkit.catalog.repositories import register_library, register_source
from media_toolkit.review.web import create_review_app
from media_toolkit.scan.service import ScanRequest, run_scan


class ReviewWebTests(unittest.TestCase):
    def test_review_index_and_empty_pages_are_paginated_and_catalog_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = Path(temporary_directory) / "catalog.sqlite3"
            initialize_database(database, "test", "TEST")
            register_library(database, "TEST", "Personal Media")

            application = create_review_app(database, "TEST", "Personal Media")
            client = application.test_client()

            index = client.get("/")
            duplicates = client.get("/duplicates?page=1")
            no_date = client.get("/dates?state=no_date&page=1")
            invalid_page = client.get("/duplicates?page=0")

            self.assertEqual(index.status_code, 200)
            self.assertIn(b"Media Library Review", index.data)
            self.assertEqual(duplicates.status_code, 200)
            self.assertIn(b"No matching records in this page.", duplicates.data)
            self.assertEqual(no_date.status_code, 200)
            self.assertEqual(invalid_page.status_code, 400)

    def test_photo_preview_uses_an_external_regenerable_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            root = base / "media"
            state = base / "state"
            root.mkdir()
            state.mkdir()
            Image.new("RGB", (1200, 800), color="navy").save(root / "IMG.jpg")
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
            from media_toolkit.catalog.database import open_database
            with open_database(database) as connection:
                media_id = connection.execute("SELECT media_id FROM media_file").fetchone()["media_id"]
            application = create_review_app(
                database, "TEST", "Personal Media", root, state / "cache"
            )

            response = application.test_client().get(f"/previews/{media_id}")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, "image/jpeg")
            self.assertTrue(any((state / "cache" / "review-previews").rglob("*.jpg")))
            self.assertEqual(list(root.rglob("*.jpg")), [root / "IMG.jpg"])
            response.close()


if __name__ == "__main__":
    unittest.main()
