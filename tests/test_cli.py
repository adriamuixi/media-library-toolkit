from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest

from media_toolkit.cli import main


class CliTests(unittest.TestCase):
    def _write_config(self, directory: Path) -> Path:
        config_path = directory / "test-config.toml"
        config_path.write_text(
            """
[paths]
workspace = "./workspace"
logs = "./logs"
reports = "./reports"
cache = "./cache"

[profiles.test]
database = "./workspace/catalog.sqlite3"
environment = "TEST"
""".strip(),
            encoding="utf-8",
        )
        return config_path

    def test_cli_initializes_and_resets_test_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            config_path = self._write_config(base)
            previous_cwd = Path.cwd()
            try:
                __import__("os").chdir(base)
                output = StringIO()
                with redirect_stdout(output):
                    init_result = main(
                        ["--config", str(config_path), "--profile", "test", "init"]
                    )
                    reset_result = main(
                        [
                            "--config",
                            str(config_path),
                            "--profile",
                            "test",
                            "db",
                            "reset",
                            "--confirm-reset",
                        ]
                    )
            finally:
                __import__("os").chdir(previous_cwd)

            self.assertEqual(init_result, 0)
            self.assertEqual(reset_result, 0)
            self.assertIn("TEST catalog reset", output.getvalue())

    def test_cli_requires_explicit_reset_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            config_path = self._write_config(base)
            previous_cwd = Path.cwd()
            try:
                __import__("os").chdir(base)
                error = StringIO()
                with redirect_stderr(error):
                    result = main(
                        [
                            "--config",
                            str(config_path),
                            "--profile",
                            "test",
                            "db",
                            "reset",
                        ]
                    )
            finally:
                __import__("os").chdir(previous_cwd)

            self.assertEqual(result, 2)
            self.assertIn("Reset was not confirmed", error.getvalue())

    def test_cli_registers_and_lists_library_and_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            config_path = self._write_config(base)
            previous_cwd = Path.cwd()
            try:
                __import__("os").chdir(base)
                output = StringIO()
                with redirect_stdout(output):
                    self.assertEqual(
                        main(
                            [
                                "--config",
                                str(config_path),
                                "--profile",
                                "test",
                                "init",
                            ]
                        ),
                        0,
                    )
                    self.assertEqual(
                        main(
                            [
                                "--config",
                                str(config_path),
                                "--profile",
                                "test",
                                "library",
                                "add",
                                "Personal Media",
                                "--description",
                                "Synthetic test library",
                            ]
                        ),
                        0,
                    )
                    self.assertEqual(
                        main(
                            [
                                "--config",
                                str(config_path),
                                "--profile",
                                "test",
                                "source",
                                "add",
                                "--library",
                                "Personal Media",
                                "--name",
                                "iPhone Personal",
                                "--type",
                                "iphone",
                                "--default-timezone",
                                "Europe/Madrid",
                            ]
                        ),
                        0,
                    )
                    self.assertEqual(
                        main(
                            [
                                "--config",
                                str(config_path),
                                "--profile",
                                "test",
                                "source",
                                "list",
                                "--library",
                                "Personal Media",
                            ]
                        ),
                        0,
                    )
            finally:
                __import__("os").chdir(previous_cwd)

            rendered = output.getvalue()
            self.assertIn("Registration: CREATED", rendered)
            self.assertIn("iPhone Personal", rendered)
            self.assertIn("Europe/Madrid", rendered)


if __name__ == "__main__":
    unittest.main()
