from contextlib import closing
from hashlib import sha256
from importlib.resources import files
from pathlib import Path
import sqlite3
import tempfile
import unittest

from media_toolkit.catalog.database import (
    backup_database,
    get_database_status,
    initialize_database,
    reset_test_database,
)
from media_toolkit.errors import DatabaseSafetyError


class DatabaseTests(unittest.TestCase):
    def test_initialize_creates_marked_test_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "catalog.sqlite3"

            status = initialize_database(path, "test", "TEST")

            self.assertTrue(status.exists)
            self.assertEqual(status.environment, "TEST")
            self.assertEqual(status.profile_name, "test")
            self.assertEqual(status.schema_version, 15)
            self.assertTrue(status.database_id)

    def test_reinitialization_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "catalog.sqlite3"

            first = initialize_database(path, "test", "TEST")
            second = initialize_database(path, "test", "TEST")

            self.assertEqual(first.database_id, second.database_id)
            self.assertEqual(second.schema_version, 15)

    def test_reset_recreates_test_catalog_with_new_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "catalog.sqlite3"
            first = initialize_database(path, "test", "TEST")
            with closing(sqlite3.connect(path)) as connection:
                with connection:
                    connection.execute(
                        """
                        INSERT INTO library (
                            library_id, name, environment, created_at, updated_at
                        ) VALUES ('temporary', 'Temporary', 'TEST', 'now', 'now')
                        """
                    )

            second = reset_test_database(path, "test", "TEST")

            self.assertNotEqual(first.database_id, second.database_id)
            with closing(sqlite3.connect(path)) as connection:
                count = connection.execute("SELECT COUNT(*) FROM library").fetchone()[0]
            self.assertEqual(count, 0)

    def test_reset_refuses_production_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "catalog.sqlite3"
            initialize_database(path, "production", "PRODUCTION")

            with self.assertRaises(DatabaseSafetyError):
                reset_test_database(path, "production", "PRODUCTION")

    def test_reset_refuses_production_database_with_test_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "catalog.sqlite3"
            initialize_database(path, "production", "PRODUCTION")

            with self.assertRaises(DatabaseSafetyError):
                reset_test_database(path, "test", "TEST")

    def test_status_does_not_create_missing_database(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "missing.sqlite3"

            status = get_database_status(path)

            self.assertFalse(status.exists)
            self.assertFalse(path.exists())

    def test_backup_creates_separate_consistent_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            path = base / "catalog.sqlite3"
            initialize_database(path, "test", "TEST")

            backup = backup_database(path, "TEST", base / "backup.sqlite3")

            self.assertTrue(backup.is_file())
            self.assertEqual(get_database_status(backup).environment, "TEST")

    def test_initialize_refuses_to_adopt_unmarked_sqlite_database(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "unrelated.sqlite3"
            with closing(sqlite3.connect(path)) as connection:
                with connection:
                    connection.execute("CREATE TABLE unrelated (value TEXT)")

            with self.assertRaises(DatabaseSafetyError):
                initialize_database(path, "test", "TEST")

            with closing(sqlite3.connect(path)) as connection:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
            self.assertEqual(tables, {"unrelated"})

    def test_initialize_migrates_existing_foundation_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "foundation.sqlite3"
            migration = files("media_toolkit.catalog.migrations").joinpath(
                "0001_foundation.sql"
            )
            migration_sql = migration.read_text(encoding="utf-8")
            migration_checksum = sha256(migration_sql.encode()).hexdigest()
            with closing(sqlite3.connect(path)) as connection:
                with connection:
                    connection.execute(
                        """
                        CREATE TABLE schema_version (
                            version INTEGER PRIMARY KEY,
                            migration_name TEXT NOT NULL,
                            checksum TEXT NOT NULL,
                            applied_at TEXT NOT NULL,
                            software_version TEXT NOT NULL
                        )
                        """
                    )
                    connection.executescript(migration_sql)
                    connection.execute(
                        """
                        INSERT INTO schema_version (
                            version,
                            migration_name,
                            checksum,
                            applied_at,
                            software_version
                        ) VALUES (1, 'foundation', ?, 'now', '0.1.0')
                        """,
                        (migration_checksum,),
                    )
                    connection.execute(
                        """
                        INSERT INTO catalog_metadata (
                            singleton,
                            database_id,
                            profile_name,
                            environment,
                            created_at
                        ) VALUES (1, 'foundation-id', 'test', 'TEST', 'now')
                        """
                    )

            status = initialize_database(path, "test", "TEST")

            self.assertEqual(status.schema_version, 15)
            with closing(sqlite3.connect(path)) as connection:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
            self.assertIn("media_file", tables)
            self.assertIn("file_location", tables)
            self.assertIn("scan_error", tables)
            self.assertIn("scan_checkpoint", tables)
            self.assertIn("metadata_extraction", tables)
            self.assertIn("media_metadata", tables)
            self.assertIn("date_resolution_attempt", tables)
            self.assertIn("media_date_resolution", tables)
            self.assertIn("media_relation", tables)
            self.assertIn("hash_attempt", tables)
            self.assertIn("media_hash", tables)
            self.assertIn("import_batch", tables)
            self.assertIn("file_observation", tables)
            self.assertIn("media_item", tables)
            self.assertIn("observation_location_history", tables)
            self.assertIn("organization_plan", tables)


if __name__ == "__main__":
    unittest.main()
