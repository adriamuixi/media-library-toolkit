from pathlib import Path
import tempfile
import unittest

from media_toolkit.config import load_config
from media_toolkit.errors import ConfigurationError


class ConfigTests(unittest.TestCase):
    def test_defaults_separate_test_and_production_databases(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            config = load_config(base_directory=base)

            production = config.profile("production")
            test = config.profile("test")

            self.assertEqual(production.environment, "PRODUCTION")
            self.assertEqual(test.environment, "TEST")
            self.assertNotEqual(production.database, test.database)
            self.assertTrue(production.database.is_relative_to(base))
            self.assertTrue(test.database.is_relative_to(base))
            self.assertEqual(config.panorama_aspect_ratio_threshold, 2.0)

    def test_default_media_mode_must_remain_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            config_path = base / "unsafe.toml"
            config_path.write_text(
                '[safety]\ndefault_media_mode = "write"\n', encoding="utf-8"
            )

            with self.assertRaises(ConfigurationError):
                load_config(config_path, base_directory=base)

    def test_panorama_threshold_must_be_greater_than_one(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            config_path = base / "invalid-panorama.toml"
            config_path.write_text(
                "[metadata]\npanorama_aspect_ratio_threshold = 1.0\n",
                encoding="utf-8",
            )

            with self.assertRaises(ConfigurationError):
                load_config(config_path, base_directory=base)


if __name__ == "__main__":
    unittest.main()
