from pathlib import Path
import tempfile
import unittest

from media_toolkit.catalog.database import initialize_database
from media_toolkit.catalog.repositories import (
    list_libraries,
    list_sources,
    register_library,
    register_source,
    register_import_batch,
)
from media_toolkit.errors import CatalogError, DatabaseSafetyError


class CatalogRepositoryTests(unittest.TestCase):
    def _database(self, directory: str) -> Path:
        path = Path(directory) / "catalog.sqlite3"
        initialize_database(path, "test", "TEST")
        return path

    def test_library_registration_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = self._database(temporary_directory)

            first = register_library(
                database, "TEST", "Personal Media", "Synthetic test library"
            )
            second = register_library(
                database, "TEST", "Personal Media", "Synthetic test library"
            )

            self.assertTrue(first.created)
            self.assertFalse(second.created)
            self.assertEqual(first.record.library_id, second.record.library_id)
            self.assertEqual(len(list_libraries(database, "TEST")), 1)

    def test_library_registration_refuses_conflicting_description(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = self._database(temporary_directory)
            register_library(database, "TEST", "Personal Media", "First")

            with self.assertRaises(CatalogError):
                register_library(database, "TEST", "Personal Media", "Second")

    def test_source_registration_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = self._database(temporary_directory)
            register_library(database, "TEST", "Personal Media")

            first = register_source(
                database,
                "TEST",
                "Personal Media",
                "iPhone Personal",
                "IPHONE",
                "Europe/Madrid",
            )
            second = register_source(
                database,
                "TEST",
                "Personal Media",
                "iPhone Personal",
                "IPHONE",
                "Europe/Madrid",
            )

            self.assertTrue(first.created)
            self.assertFalse(second.created)
            self.assertEqual(first.record.source_id, second.record.source_id)
            self.assertEqual(len(list_sources(database, "TEST")), 1)

    def test_source_registration_refuses_conflicting_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = self._database(temporary_directory)
            register_library(database, "TEST", "Personal Media")
            register_source(
                database, "TEST", "Personal Media", "Phone", "IPHONE"
            )

            with self.assertRaises(CatalogError):
                register_source(
                    database, "TEST", "Personal Media", "Phone", "ANDROID"
                )

    def test_source_registration_requires_existing_library(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = self._database(temporary_directory)

            with self.assertRaises(CatalogError):
                register_source(
                    database, "TEST", "Missing", "Phone", "IPHONE"
                )

    def test_source_registration_validates_iana_timezone(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = self._database(temporary_directory)
            register_library(database, "TEST", "Personal Media")

            with self.assertRaises(CatalogError):
                register_source(
                    database,
                    "TEST",
                    "Personal Media",
                    "Phone",
                    "IPHONE",
                    "Madrid/Europe",
                )

    def test_catalog_operations_require_matching_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = self._database(temporary_directory)

            with self.assertRaises(DatabaseSafetyError):
                list_libraries(database, "PRODUCTION")

    def test_list_order_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = self._database(temporary_directory)
            register_library(database, "TEST", "Zulu")
            register_library(database, "TEST", "alpha")

            records = list_libraries(database, "TEST")

            self.assertEqual([record.name for record in records], ["alpha", "Zulu"])


    def test_import_batch_registration_is_idempotent_and_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = self._database(temporary_directory)
            register_library(database, "TEST", "Personal Media")
            register_source(database, "TEST", "Personal Media", "Old Disk", "OLD_DISK")
            first = register_import_batch(
                database, "TEST", "Personal Media", "Old Disk", "WD_OLD_2026_08"
            )
            second = register_import_batch(
                database, "TEST", "Personal Media", "Old Disk", "WD_OLD_2026_08"
            )
            self.assertTrue(first.created)
            self.assertFalse(second.created)
            with self.assertRaises(CatalogError):
                register_import_batch(
                    database, "TEST", "Personal Media", "Old Disk",
                    "WD_OLD_2026_08", "Changed",
                )


if __name__ == "__main__":
    unittest.main()
