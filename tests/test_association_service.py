from pathlib import Path
import tempfile
import unittest

from media_toolkit.associations.service import (
    AssociationRequest,
    _identifiers,
    list_associations,
    run_association_detection,
)
from media_toolkit.catalog.database import initialize_database, open_database
from media_toolkit.catalog.repositories import register_library, register_source
from media_toolkit.scan.service import ScanRequest, run_scan


class AssociationServiceTests(unittest.TestCase):
    def test_extracts_live_photo_identifiers_from_both_tool_shapes(self) -> None:
        raw = """{"XMP:ContentIdentifier":"ASSET-1","format":{"tags":{"com.apple.quicktime.content.identifier":"ASSET-2"}}}"""

        self.assertEqual(_identifiers(raw), ("asset-1", "asset-2"))

    def _setup(self, base: Path) -> tuple[Path, Path]:
        root = base / "media"
        state = base / "state"
        root.mkdir()
        state.mkdir()
        fixtures = {
            "live/IMG_100.HEIC": b"photo",
            "live/IMG_100.MOV": b"video",
            "raw/DSC_1.CR3": b"raw",
            "raw/DSC_1.JPG": b"jpeg",
            "raw/DSC_1.XMP": b"sidecar",
            "edit/IMG_200.JPG": b"edited",
            "edit/IMG_200.AAE": b"adjustment",
        }
        for relative_path, content in fixtures.items():
            path = root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        database = state / "catalog.sqlite3"
        initialize_database(database, "test", "TEST")
        register_library(database, "TEST", "Personal Media")
        register_source(database, "TEST", "Personal Media", "Camera", "CAMERA", None)
        generated = (state, state / "logs", state / "reports", state / "cache", database)
        run_scan(
            ScanRequest(
                database, "TEST", "Personal Media", "Camera", root, "all",
                False, 10, generated,
            )
        )
        return root, database

    def _request(self, database: Path) -> AssociationRequest:
        return AssociationRequest(database, "TEST", "Personal Media", "Camera")

    def test_detects_live_raw_jpeg_and_sidecar_relations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            _, database = self._setup(Path(temporary_directory))

            summary = run_association_detection(self._request(database))
            rows = list_associations(database, "TEST", "Personal Media", "Camera")

            self.assertEqual(summary.file_count, 7)
            self.assertEqual(summary.relation_count, 4)
            self.assertEqual(summary.live_photo_count, 1)
            self.assertEqual(summary.raw_jpeg_count, 1)
            self.assertEqual(summary.sidecar_count, 2)
            self.assertEqual(summary.conflict_count, 0)
            self.assertEqual(len(rows), 4)
            self.assertTrue(all(row.active for row in rows))

    def test_repeated_detection_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            _, database = self._setup(Path(temporary_directory))
            request = self._request(database)

            first = run_association_detection(request)
            second = run_association_detection(request)

            self.assertEqual(first, second)
            with open_database(database) as connection:
                count = connection.execute(
                    "SELECT COUNT(*) AS count FROM media_relation"
                ).fetchone()["count"]
            self.assertEqual(count, 4)

    def test_disappeared_relation_becomes_inactive_without_losing_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            _, database = self._setup(Path(temporary_directory))
            request = self._request(database)
            run_association_detection(request)
            with open_database(database) as connection:
                media_id = connection.execute(
                    "SELECT media_id FROM file_location WHERE relative_path = 'live/IMG_100.MOV'"
                ).fetchone()["media_id"]
                connection.execute(
                    "UPDATE file_location SET present = 0 WHERE media_id = ?",
                    (media_id,),
                )
                connection.execute(
                    "UPDATE media_file SET status = 'MISSING' WHERE media_id = ?",
                    (media_id,),
                )

            summary = run_association_detection(request)
            active = list_associations(database, "TEST", "Personal Media", "Camera")
            history = list_associations(
                database, "TEST", "Personal Media", "Camera", include_inactive=True
            )

            self.assertEqual(summary.live_photo_count, 0)
            self.assertEqual(len(active), 3)
            self.assertEqual(len(history), 4)
            inactive_live = [row for row in history if row.relation_type == "LIVE_PHOTO_PAIR"]
            self.assertEqual(len(inactive_live), 1)
            self.assertFalse(inactive_live[0].active)


if __name__ == "__main__":
    unittest.main()
