from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from media_toolkit.catalog.database import initialize_database
from media_toolkit.catalog.repositories import register_library, register_source
from media_toolkit.cli import main
from media_toolkit.metadata.models import ToolStatus


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

    def test_cli_checks_both_metadata_tools(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            config_path = self._write_config(base)
            previous_cwd = Path.cwd()
            output = StringIO()
            try:
                __import__("os").chdir(base)
                with (
                    patch(
                        "media_toolkit.cli.ExifToolAdapter.status",
                        return_value=ToolStatus(
                            "ExifTool", "/tools/exiftool", True, "13.0", None
                        ),
                    ),
                    patch(
                        "media_toolkit.cli.FfprobeAdapter.status",
                        return_value=ToolStatus(
                            "ffprobe", "ffprobe", False, None, "Executable was not found."
                        ),
                    ),
                    redirect_stdout(output),
                ):
                    result = main(["--config", str(config_path), "tools", "check"])
            finally:
                __import__("os").chdir(previous_cwd)

            self.assertEqual(result, 1)
            self.assertIn("ExifTool: AVAILABLE", output.getvalue())
            self.assertIn("ffprobe: UNAVAILABLE", output.getvalue())

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

    def test_cli_runs_read_only_scan(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            media_root = base / "media"
            media_root.mkdir()
            media_file = media_root / "synthetic.JPG"
            media_file.write_bytes(b"synthetic-photo")
            config_path = self._write_config(base)
            previous_cwd = Path.cwd()
            try:
                __import__("os").chdir(base)
                output = StringIO()
                with redirect_stdout(output):
                    commands = [
                        [
                            "--config",
                            str(config_path),
                            "--profile",
                            "test",
                            "init",
                        ],
                        [
                            "--config",
                            str(config_path),
                            "--profile",
                            "test",
                            "library",
                            "add",
                            "Personal Media",
                        ],
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
                            "Synthetic Camera",
                            "--type",
                            "camera",
                        ],
                        [
                            "--config",
                            str(config_path),
                            "--profile",
                            "test",
                            "scan",
                            "--library",
                            "Personal Media",
                            "--source",
                            "Synthetic Camera",
                            "--root",
                            str(media_root),
                            "--media-type",
                            "photos",
                        ],
                    ]
                    for command in commands:
                        self.assertEqual(main(command), 0)
            finally:
                __import__("os").chdir(previous_cwd)

            self.assertEqual(media_file.read_bytes(), b"synthetic-photo")
            self.assertIn("Discovered: 1", output.getvalue())
            self.assertIn("New: 1", output.getvalue())

    def test_cli_rejects_scan_log_directory_inside_media_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            media_root = base / "media"
            state_root = base / "state"
            media_root.mkdir()
            state_root.mkdir()
            database = state_root / "catalog.sqlite3"
            initialize_database(database, "test", "TEST")
            register_library(database, "TEST", "Personal Media")
            register_source(
                database,
                "TEST",
                "Personal Media",
                "Synthetic Camera",
                "CAMERA",
            )
            unsafe_logs = media_root / "generated-logs"
            config_path = base / "unsafe-scan.toml"
            config_path.write_text(
                f"""
[paths]
workspace = "{state_root / 'workspace'}"
logs = "{unsafe_logs}"
reports = "{state_root / 'reports'}"
cache = "{state_root / 'cache'}"

[profiles.test]
database = "{database}"
environment = "TEST"
""".strip(),
                encoding="utf-8",
            )
            error = StringIO()

            with redirect_stderr(error):
                result = main(
                    [
                        "--config",
                        str(config_path),
                        "--profile",
                        "test",
                        "scan",
                        "--library",
                        "Personal Media",
                        "--source",
                        "Synthetic Camera",
                        "--root",
                        str(media_root),
                    ]
                )

            self.assertEqual(result, 2)
            self.assertIn("must remain outside the media root", error.getvalue())
            self.assertFalse(unsafe_logs.exists())


if __name__ == "__main__":
    unittest.main()
