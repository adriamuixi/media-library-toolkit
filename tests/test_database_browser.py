import json
from pathlib import Path
import tempfile
import unittest

from media_toolkit.database_browser import build_datasette_command, build_datasette_metadata


class DatabaseBrowserTests(unittest.TestCase):
    def test_metadata_exposes_versioned_saved_queries_without_database_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            metadata_path = build_datasette_metadata(base, base / "catalog.sqlite3")

            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

            queries = metadata["databases"]["catalog"]["queries"]
            self.assertIn("exact_duplicates", queries)
            self.assertIn("provenance", queries)
            self.assertIn("SELECT", queries["no_date"]["sql"])

    def test_command_tracks_external_catalog_updates_without_immutable_mode(self) -> None:
        command = build_datasette_command(
            "/example/python",
            Path("/catalog.sqlite3"),
            Path("/metadata.json"),
            8081,
        )

        self.assertNotIn("--immutable", command)
        self.assertIn("/catalog.sqlite3", command)
        self.assertEqual(command[-4:], ["--host", "127.0.0.1", "--port", "8081"])


if __name__ == "__main__":
    unittest.main()
