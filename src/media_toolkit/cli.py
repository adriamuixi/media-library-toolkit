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
from media_toolkit.catalog.repositories import (
    list_libraries,
    list_sources,
    register_library,
    register_source,
)
from media_toolkit.config import AppConfig, load_config
from media_toolkit.errors import MediaToolkitError
from media_toolkit.logging_config import configure_logging


LOGGER = logging.getLogger(__name__)

SOURCE_TYPES = (
    "ANDROID",
    "CAMERA",
    "DOWNLOAD",
    "IPHONE",
    "MASTER_LIBRARY",
    "OLD_DISK",
    "SCREENSHOT",
    "TO_ANALYZE",
    "UNKNOWN",
    "WHATSAPP",
)


def _source_type(value: str) -> str:
    return value.strip().upper().replace("-", "_")


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

    library_parser = commands.add_parser(
        "library", help="Register or list logical media libraries."
    )
    library_commands = library_parser.add_subparsers(
        dest="library_command", required=True
    )

    library_add_parser = library_commands.add_parser(
        "add", help="Register a logical media library idempotently."
    )
    library_add_parser.add_argument("name", help="Stable human-readable library name.")
    library_add_parser.add_argument(
        "--description", help="Optional description of the library."
    )
    library_add_parser.set_defaults(handler=_handle_library_add)

    library_list_parser = library_commands.add_parser(
        "list", help="List libraries in the selected catalog profile."
    )
    library_list_parser.set_defaults(handler=_handle_library_list)

    source_parser = commands.add_parser(
        "source", help="Register or list media provenance sources."
    )
    source_commands = source_parser.add_subparsers(dest="source_command", required=True)

    source_add_parser = source_commands.add_parser(
        "add", help="Register a source within an existing library idempotently."
    )
    source_add_parser.add_argument(
        "--library", required=True, help="Name of the existing logical library."
    )
    source_add_parser.add_argument("--name", required=True, help="Stable source name.")
    source_add_parser.add_argument(
        "--type",
        required=True,
        type=_source_type,
        choices=SOURCE_TYPES,
        dest="source_type",
        help="Source provenance type.",
    )
    source_add_parser.add_argument(
        "--default-timezone",
        help="Optional IANA timezone, such as Europe/Madrid.",
    )
    source_add_parser.set_defaults(handler=_handle_source_add)

    source_list_parser = source_commands.add_parser(
        "list", help="List sources in the selected catalog profile."
    )
    source_list_parser.add_argument(
        "--library", help="Optionally restrict results to one library name."
    )
    source_list_parser.set_defaults(handler=_handle_source_list)
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


def _handle_library_add(args: argparse.Namespace, config: AppConfig) -> int:
    profile = config.profile(args.profile)
    result = register_library(
        profile.database,
        profile.environment,
        args.name,
        args.description,
    )
    record = result.record
    print(f"Library: {record.name}")
    print(f"Library ID: {record.library_id}")
    print(f"Environment: {record.environment}")
    print(f"Registration: {'CREATED' if result.created else 'EXISTING'}")
    return 0


def _handle_library_list(args: argparse.Namespace, config: AppConfig) -> int:
    profile = config.profile(args.profile)
    records = list_libraries(profile.database, profile.environment)
    if not records:
        print("No libraries registered.")
        return 0
    print("NAME\tENVIRONMENT\tLIBRARY_ID\tDESCRIPTION")
    for record in records:
        print(
            f"{record.name}\t{record.environment}\t{record.library_id}\t"
            f"{record.description or ''}"
        )
    return 0


def _handle_source_add(args: argparse.Namespace, config: AppConfig) -> int:
    profile = config.profile(args.profile)
    result = register_source(
        profile.database,
        profile.environment,
        args.library,
        args.name,
        args.source_type,
        args.default_timezone,
    )
    record = result.record
    print(f"Source: {record.name}")
    print(f"Source ID: {record.source_id}")
    print(f"Library: {record.library_name}")
    print(f"Source type: {record.source_type}")
    print(f"Default timezone: {record.default_timezone or 'UNKNOWN'}")
    print(f"Registration: {'CREATED' if result.created else 'EXISTING'}")
    return 0


def _handle_source_list(args: argparse.Namespace, config: AppConfig) -> int:
    profile = config.profile(args.profile)
    records = list_sources(profile.database, profile.environment, args.library)
    if not records:
        print("No sources registered.")
        return 0
    print("LIBRARY\tNAME\tTYPE\tTIMEZONE\tSOURCE_ID")
    for record in records:
        print(
            f"{record.library_name}\t{record.name}\t{record.source_type}\t"
            f"{record.default_timezone or 'UNKNOWN'}\t{record.source_id}"
        )
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
        elif getattr(args, "library_command", None):
            command_name = f"library-{args.library_command}"
        elif getattr(args, "source_command", None):
            command_name = f"source-{args.source_command}"
        configure_logging(config.logs, config.log_level, command_name)
        LOGGER.info("Starting command=%s profile=%s", command_name, args.profile or config.default_profile)
        return int(args.handler(args, config))
    except MediaToolkitError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
