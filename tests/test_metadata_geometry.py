import unittest

from media_toolkit.metadata.geometry import derive_geometry


class MetadataGeometryTests(unittest.TestCase):
    def test_rotation_swaps_display_dimensions(self) -> None:
        geometry = derive_geometry(4000, 3000, 90, None, 2.0)

        self.assertEqual((geometry.display_width_px, geometry.display_height_px), (3000, 4000))
        self.assertEqual(geometry.orientation_class, "PORTRAIT")
        self.assertEqual(geometry.megapixels, 12.0)
        self.assertFalse(geometry.is_panorama)

    def test_panorama_uses_deterministic_threshold(self) -> None:
        geometry = derive_geometry(6000, 2000, 0, None, 2.5)

        self.assertTrue(geometry.is_panorama)
        self.assertEqual(geometry.panorama_reason, "ASPECT_RATIO_THRESHOLD")

    def test_projection_metadata_is_authoritative(self) -> None:
        geometry = derive_geometry(2000, 1500, None, "Equirectangular", 3.0)

        self.assertTrue(geometry.is_panorama)
        self.assertEqual(geometry.panorama_reason, "PROJECTION_METADATA")

    def test_missing_dimensions_remain_unknown(self) -> None:
        geometry = derive_geometry(None, 1000, None, None, 2.0)

        self.assertEqual(geometry.orientation_class, "UNKNOWN")
        self.assertIsNone(geometry.megapixels)


if __name__ == "__main__":
    unittest.main()
