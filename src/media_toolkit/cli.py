"""Command-line interface for Media Library Toolkit."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys
from typing import Sequence

from media_toolkit import __version__
from media_toolkit.catalog.database import (
    get_database_status,
    initialize_database,
    reset_test_database,
)
from media_toolkit.config import AppConfig, load_config
from media_toolkit.errors import MediaToolkitError
from media_toolkit.logging_config import configure_logging


LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build the complete CLI parser."""
    parser = argparse.ArgumentParser(
        prog="media",
        description="Safely catalog and organize personal media libraries.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", type=Path, help="Path to a local TOML configuration file.")
    parser.add_argument(
        "--profile",
        help="Configuration profile to use. Defaults to the configured production profile.",
    )

    commands = parser.add_subparsers(dest="command", required=True)

    init_parser = commands.add_parser(
        "init", help="Create working directories and initialize the selected catalog."
    )
    init_parser.set_defaults(handler=_handle_init)

    db_parser = commands.add_parser("db", help="Inspect or safely manage the SQLite catalog.")
    db_commands = db_parser.add_subparsers(dest="db_command", required=True)

    status_parser = db_commands.add_parser("status", help="Show catalog identity and schema status.")
    status_parser.set_defaults(handler=_handle_db_status)

    reset_parser = db_commands.add_parser(
        "reset",
        help="Delete and recreate a TEST catalog. Production catalogs are always refused.",
    )
    reset_parser.add_argument(
        "--confirm-reset",
        action="store_true",
        help="Confirm permanent deletion of the selected TEST catalog.",
    )
    reset_parser.set_defaults(handler=_handle_db_reset)
    return parser


def _prepare_directories(config: AppConfig) -> None:
    for path in (config.workspace, config.logs, config.reports, config.cache):
        path.mkdir(parents=True, exist_ok=True)


def _handle_init(args: argparse.Namespace, config: AppConfig) -> int:
    profile = config.profile(args.profile)
    _prepare_directories(config)
    status = initialize_database(profile.database, profile.name, profile.environment)
    print(f"Catalog initialized: {status.path}")
    print(f"Database ID: {status.database_id}")
    print(f"Profile: {status.profile_name}")
    print(f"Environment: {status.environment}")
    print(f"Schema version: {status.schema_version}")
    return 0


def _handle_db_status(args: argparse.Namespace, config: AppConfig) -> int:
    profile = config.profile(args.profile)
    status = get_database_status(profile.database)
    print(f"Catalog path: {status.path}")
    if not status.exists:
        print("Status: NOT INITIALIZED")
        return 0
    print("Status: READY")
    print(f"Database ID: {status.database_id}")
    print(f"Profile: {status.profile_name}")
    print(f"Environment: {status.environment}")
    print(f"Schema version: {status.schema_version}")
    return 0


def _handle_db_reset(args: argparse.Namespace, config: AppConfig) -> int:
    if not args.confirm_reset:
        raise MediaToolkitError(
            "Reset was not confirmed. Add --confirm-reset to reset a TEST catalog."
        )
    profile = config.profile(args.profile)
    status = reset_test_database(profile.database, profile.name, profile.environment)
    print(f"TEST catalog reset: {status.path}")
    print(f"New database ID: {status.database_id}")
    print(f"Schema version: {status.schema_version}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and convert expected failures into concise messages."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        command_name = args.command
        if getattr(args, "db_command", None):
            command_name = f"db-{args.db_command}"
        configure_logging(config.logs, config.log_level, command_name)
        LOGGER.info("Starting command=%s profile=%s", command_name, args.profile or config.default_profile)
        return int(args.handler(args, config))
    except MediaToolkitError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
