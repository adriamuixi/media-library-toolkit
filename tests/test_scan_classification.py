from pathlib import Path
import unittest

from media_toolkit.scan.classification import classify_path, matches_media_filter


class ScanClassificationTests(unittest.TestCase):
    def test_classification_is_case_insensitive(self) -> None:
        self.assertEqual(classify_path(Path("photo.JPEG")), "PHOTO")
        self.assertEqual(classify_path(Path("clip.MOV")), "VIDEO")
        self.assertEqual(classify_path(Path("edit.XMP")), "SIDECAR")
        self.assertEqual(classify_path(Path("notes.txt")), "UNKNOWN")

    def test_media_filters_are_explicit(self) -> None:
        self.assertTrue(matches_media_filter("PHOTO", "photos"))
        self.assertFalse(matches_media_filter("VIDEO", "photos"))
        self.assertTrue(matches_media_filter("VIDEO", "videos"))
        self.assertTrue(matches_media_filter("UNKNOWN", "all"))


if __name__ == "__main__":
    unittest.main()
