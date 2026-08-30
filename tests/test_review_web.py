from pathlib import Path
import tempfile
import unittest

from media_toolkit.catalog.database import initialize_database
from media_toolkit.catalog.repositories import register_library
from media_toolkit.review.web import create_review_app


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


if __name__ == "__main__":
    unittest.main()
