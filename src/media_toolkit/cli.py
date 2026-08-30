"""Command-line interface for Media Library Toolkit."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys
from typing import Sequence

from media_toolkit import __version__
from media_toolkit.associations.service import (
    AssociationRequest,
    list_associations,
    run_association_detection,
)
from media_toolkit.catalog.database import (
    backup_database,
    get_database_status,
    initialize_database,
    reset_test_database,
)
from media_toolkit.catalog.repositories import (
    list_libraries,
    list_import_batches,
    list_sources,
    register_import_batch,
    register_library,
    register_source,
)
from media_toolkit.config import AppConfig, load_config
from media_toolkit.dates.service import (
    DateResolutionRequest,
    list_date_resolutions,
    run_date_resolution,
)
from media_toolkit.duplicates.service import (
    export_exact_duplicate_report,
    list_exact_duplicates,
    list_size_candidates,
)
from media_toolkit.errors import MediaToolkitError
from media_toolkit.hashing.service import HashRequest, list_hashes, run_hashing
from media_toolkit.logging_config import configure_logging
from media_toolkit.metadata.exiftool import ExifToolAdapter
from media_toolkit.metadata.ffprobe import FfprobeAdapter
from media_toolkit.metadata.service import MetadataRequest, run_metadata
from media_toolkit.provenance.service import export_provenance
from media_toolkit.planning.service import create_year_or_no_date_plan
from media_toolkit.scan.safety import ensure_external_working_paths
from media_toolkit.scan.service import ScanRequest, run_scan


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
    backup_parser = db_commands.add_parser("backup", help="Create a consistent catalog backup.")
    backup_parser.add_argument("--output", required=True, type=Path)
    backup_parser.set_defaults(handler=_handle_db_backup)

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

    batch_parser = commands.add_parser(
        "batch", help="Register or list immutable import batches."
    )
    batch_commands = batch_parser.add_subparsers(dest="batch_command", required=True)
    batch_add_parser = batch_commands.add_parser(
        "add", help="Register an import batch idempotently."
    )
    batch_add_parser.add_argument("--library", required=True)
    batch_add_parser.add_argument("--source", required=True, dest="source_name")
    batch_add_parser.add_argument("--name", required=True)
    batch_add_parser.add_argument("--description")
    batch_add_parser.set_defaults(handler=_handle_batch_add)
    batch_list_parser = batch_commands.add_parser("list", help="List import batches.")
    batch_list_parser.add_argument("--library")
    batch_list_parser.set_defaults(handler=_handle_batch_list)

    provenance_parser = commands.add_parser("provenance", help="Export immutable provenance.")
    provenance_commands = provenance_parser.add_subparsers(
        dest="provenance_command", required=True
    )
    provenance_export_parser = provenance_commands.add_parser(
        "export", help="Write an external CSV or JSON provenance export."
    )
    provenance_export_parser.add_argument("--library", required=True)
    provenance_export_parser.add_argument("--output", required=True, type=Path)
    provenance_export_parser.add_argument(
        "--format", choices=("csv", "json"), default="csv", dest="report_format"
    )
    provenance_export_parser.set_defaults(handler=_handle_provenance_export)

    scan_parser = commands.add_parser(
        "scan", help="Inventory a registered source root without modifying media."
    )
    scan_parser.add_argument(
        "--library", required=True, help="Name of the existing logical library."
    )
    scan_parser.add_argument(
        "--source", required=True, dest="source_name", help="Name of the registered source."
    )
    scan_parser.add_argument(
        "--batch", dest="import_batch_name", help="Existing import batch for new observations."
    )
    scan_parser.add_argument(
        "--root", required=True, type=Path, help="Physical source root for this scan."
    )
    scan_parser.add_argument(
        "--media-type",
        choices=("photos", "videos", "all"),
        default="all",
        help="Restrict inventory to photos, videos, or all regular files.",
    )
    scan_parser.add_argument(
        "--include-hidden",
        action="store_true",
        help="Include hidden files and directories for this scan.",
    )
    scan_parser.add_argument(
        "--resume",
        nargs="?",
        const="latest",
        metavar="SCAN_ID",
        help="Resume a matching interrupted scan, optionally by explicit scan ID.",
    )
    scan_parser.set_defaults(handler=_handle_scan)

    tools_parser = commands.add_parser(
        "tools", help="Inspect external metadata tool availability."
    )
    tools_commands = tools_parser.add_subparsers(dest="tools_command", required=True)
    tools_check_parser = tools_commands.add_parser(
        "check", help="Check the configured ExifTool and ffprobe executables."
    )
    tools_check_parser.set_defaults(handler=_handle_tools_check)

    metadata_parser = commands.add_parser(
        "metadata", help="Extract photo and video metadata without modifying media."
    )
    metadata_parser.add_argument(
        "--library", required=True, help="Name of the existing logical library."
    )
    metadata_parser.add_argument(
        "--source", required=True, dest="source_name", help="Name of the registered source."
    )
    metadata_parser.add_argument(
        "--root", required=True, type=Path, help="Physical source root used by the inventory scan."
    )
    metadata_parser.add_argument(
        "--media-type",
        choices=("photos", "videos", "all"),
        default="all",
        help="Restrict extraction to photos, videos, or both.",
    )
    metadata_parser.add_argument(
        "--force",
        action="store_true",
        help="Extract again even when an identical successful result is cached.",
    )
    metadata_parser.set_defaults(handler=_handle_metadata)

    dates_parser = commands.add_parser(
        "dates", help="Resolve or review effective capture dates from cataloged evidence."
    )
    dates_commands = dates_parser.add_subparsers(dest="dates_command", required=True)
    dates_resolve_parser = dates_commands.add_parser(
        "resolve", help="Resolve effective capture dates without modifying media."
    )
    dates_resolve_parser.add_argument(
        "--library", required=True, help="Name of the existing logical library."
    )
    dates_resolve_parser.add_argument(
        "--source", required=True, dest="source_name", help="Name of the registered source."
    )
    dates_resolve_parser.add_argument(
        "--media-type",
        choices=("photos", "videos", "all"),
        default="all",
        help="Restrict resolution to photos, videos, or both.",
    )
    dates_resolve_parser.add_argument(
        "--force",
        action="store_true",
        help="Create a new resolution attempt even when the inputs are unchanged.",
    )
    dates_resolve_parser.set_defaults(handler=_handle_dates_resolve)

    dates_list_parser = dates_commands.add_parser(
        "list", help="List current effective dates and unresolved review states."
    )
    dates_list_parser.add_argument(
        "--library", required=True, help="Name of the existing logical library."
    )
    dates_list_parser.add_argument(
        "--source", required=True, dest="source_name", help="Name of the registered source."
    )
    dates_list_parser.add_argument(
        "--status",
        choices=("resolved", "suspicious", "conflict", "no-date"),
        help="Optionally restrict output to one review state.",
    )
    dates_list_parser.set_defaults(handler=_handle_dates_list)

    associations_parser = commands.add_parser(
        "associations", help="Detect or list related media and sidecar files."
    )
    associations_commands = associations_parser.add_subparsers(
        dest="associations_command", required=True
    )
    associations_detect_parser = associations_commands.add_parser(
        "detect", help="Detect associations from cataloged metadata and paths."
    )
    associations_detect_parser.add_argument(
        "--library", required=True, help="Name of the existing logical library."
    )
    associations_detect_parser.add_argument(
        "--source", required=True, dest="source_name", help="Name of the registered source."
    )
    associations_detect_parser.set_defaults(handler=_handle_associations_detect)

    associations_list_parser = associations_commands.add_parser(
        "list", help="List current or historical detected associations."
    )
    associations_list_parser.add_argument(
        "--library", required=True, help="Name of the existing logical library."
    )
    associations_list_parser.add_argument(
        "--source", required=True, dest="source_name", help="Name of the registered source."
    )
    associations_list_parser.add_argument(
        "--type",
        choices=("live-photo", "raw-jpeg", "sidecar"),
        dest="relation_type",
        help="Optionally restrict output to one relation type.",
    )
    associations_list_parser.add_argument(
        "--include-inactive",
        action="store_true",
        help="Include historical relations not present in the latest detection.",
    )
    associations_list_parser.set_defaults(handler=_handle_associations_list)

    hashes_parser = commands.add_parser(
        "hashes", help="Calculate or list streaming content hashes."
    )
    hashes_commands = hashes_parser.add_subparsers(dest="hashes_command", required=True)
    hashes_calculate_parser = hashes_commands.add_parser(
        "calculate", help="Calculate SHA-256 without modifying media."
    )
    hashes_calculate_parser.add_argument(
        "--library", required=True, help="Name of the existing logical library."
    )
    hashes_calculate_parser.add_argument(
        "--source", required=True, dest="source_name", help="Name of the registered source."
    )
    hashes_calculate_parser.add_argument(
        "--root", required=True, type=Path, help="Physical source root used by the inventory scan."
    )
    hashes_calculate_parser.add_argument(
        "--media-type",
        choices=("photos", "videos", "all"),
        default="all",
        help="Restrict hashing to photos, videos, or all inventoried files.",
    )
    hashes_calculate_parser.add_argument(
        "--force",
        action="store_true",
        help="Hash again even when an identical successful result is cached.",
    )
    hashes_calculate_parser.set_defaults(handler=_handle_hashes_calculate)

    hashes_list_parser = hashes_commands.add_parser(
        "list", help="List current SHA-256 values for one source."
    )
    hashes_list_parser.add_argument(
        "--library", required=True, help="Name of the existing logical library."
    )
    hashes_list_parser.add_argument(
        "--source", required=True, dest="source_name", help="Name of the registered source."
    )
    hashes_list_parser.set_defaults(handler=_handle_hashes_list)

    duplicates_parser = commands.add_parser(
        "duplicates", help="Inspect read-only exact-duplicate evidence."
    )
    duplicates_commands = duplicates_parser.add_subparsers(
        dest="duplicates_command", required=True
    )
    duplicates_candidates_parser = duplicates_commands.add_parser(
        "candidates",
        help="List same-size candidates; equal size is not a duplicate decision.",
    )
    duplicates_candidates_parser.add_argument(
        "--library", required=True, help="Name of the existing logical library."
    )
    duplicates_candidates_parser.add_argument(
        "--media-type",
        choices=("photos", "videos", "all"),
        default="all",
        help="Restrict candidates to photos, videos, or all inventoried files.",
    )
    duplicates_candidates_parser.set_defaults(handler=_handle_duplicates_candidates)
    duplicates_exact_parser = duplicates_commands.add_parser(
        "exact",
        help="List groups with equal SHA-256 values without changing any file.",
    )
    duplicates_exact_parser.add_argument(
        "--library", required=True, help="Name of the existing logical library."
    )
    duplicates_exact_parser.add_argument(
        "--media-type",
        choices=("photos", "videos", "all"),
        default="all",
        help="Restrict groups to photos, videos, or all inventoried files.",
    )
    duplicates_exact_parser.set_defaults(handler=_handle_duplicates_exact)
    duplicates_report_parser = duplicates_commands.add_parser(
        "report", help="Write an external CSV or JSON exact-duplicate review report."
    )
    duplicates_report_parser.add_argument(
        "--library", required=True, help="Name of the existing logical library."
    )
    duplicates_report_parser.add_argument(
        "--output", required=True, type=Path, help="New external report path."
    )
    duplicates_report_parser.add_argument(
        "--format", choices=("csv", "json"), default="csv", dest="report_format"
    )
    duplicates_report_parser.add_argument(
        "--media-type", choices=("photos", "videos", "all"), default="all"
    )
    duplicates_report_parser.set_defaults(handler=_handle_duplicates_report)

    plan_parser = commands.add_parser(
        "plan", help="Create read-only deterministic organization plans."
    )
    plan_commands = plan_parser.add_subparsers(dest="plan_command", required=True)
    plan_create_parser = plan_commands.add_parser(
        "create", help="Create a YEAR_OR_NO_DATE plan without changing media."
    )
    plan_create_parser.add_argument("--library", required=True)
    plan_create_parser.set_defaults(handler=_handle_plan_create)
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


def _handle_db_backup(args: argparse.Namespace, config: AppConfig) -> int:
    profile = config.profile(args.profile)
    output = backup_database(profile.database, profile.environment, args.output)
    print(f"Catalog backup: {output}")
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


def _handle_batch_add(args: argparse.Namespace, config: AppConfig) -> int:
    profile = config.profile(args.profile)
    result = register_import_batch(
        profile.database, profile.environment, args.library, args.source_name,
        args.name, args.description,
    )
    print(f"Import batch: {result.record.name}")
    print(f"Import batch ID: {result.record.import_batch_id}")
    print(f"Source: {result.record.source_name}")
    print(f"Registration: {'CREATED' if result.created else 'EXISTING'}")
    return 0


def _handle_batch_list(args: argparse.Namespace, config: AppConfig) -> int:
    profile = config.profile(args.profile)
    rows = list_import_batches(profile.database, profile.environment, args.library)
    if not rows:
        print("No import batches found.")
        return 0
    print("NAME\tSOURCE\tCREATED_AT\tDESCRIPTION")
    for row in rows:
        print(f"{row.name}\t{row.source_name}\t{row.created_at}\t{row.description or ''}")
    return 0


def _handle_provenance_export(args: argparse.Namespace, config: AppConfig) -> int:
    profile = config.profile(args.profile)
    count = export_provenance(
        profile.database, profile.environment, args.library, args.output, args.report_format
    )
    print(f"Provenance export rows: {count}")
    print(f"Export: {args.output.expanduser().resolve()}")
    return 0


def _generated_paths(config: AppConfig, profile_name: str | None) -> tuple[Path, ...]:
    profile = config.profile(profile_name)
    return (
        config.workspace,
        config.logs,
        config.reports,
        config.cache,
        profile.database,
    )


def _handle_scan(args: argparse.Namespace, config: AppConfig) -> int:
    profile = config.profile(args.profile)
    summary = run_scan(
        ScanRequest(
            database=profile.database,
            environment=profile.environment,
            library_name=args.library,
            source_name=args.source_name,
            root=args.root,
            media_filter=args.media_type,
            include_hidden=args.include_hidden or config.scan_include_hidden,
            batch_size=config.scan_batch_size,
            generated_paths=_generated_paths(config, args.profile),
            resume_scan_id=args.resume,
            import_batch_name=args.import_batch_name,
        )
    )
    print(f"Scan ID: {summary.scan_id}")
    print(f"Status: {summary.status}")
    print(f"Discovered: {summary.discovered_count}")
    print(f"New: {summary.new_count}")
    print(f"Updated: {summary.updated_count}")
    print(f"Skipped: {summary.skipped_count}")
    print(f"Warnings: {summary.warning_count}")
    print(f"Errors: {summary.error_count}")
    print(f"Resumed: {'YES' if summary.resumed else 'NO'}")
    return 0


def _handle_tools_check(args: argparse.Namespace, config: AppConfig) -> int:
    adapters = (
        ExifToolAdapter(
            config.exiftool_command,
            config.metadata_timeout_seconds,
            config.panorama_aspect_ratio_threshold,
        ),
        FfprobeAdapter(
            config.ffprobe_command,
            config.metadata_timeout_seconds,
            config.panorama_aspect_ratio_threshold,
        ),
    )
    unavailable = False
    for adapter in adapters:
        status = adapter.status()
        print(f"{status.name}: {'AVAILABLE' if status.available else 'UNAVAILABLE'}")
        print(f"  Command: {status.command}")
        print(f"  Version: {status.version or 'UNKNOWN'}")
        if status.error:
            print(f"  Error: {status.error}")
        unavailable = unavailable or not status.available
    return 1 if unavailable else 0


def _handle_metadata(args: argparse.Namespace, config: AppConfig) -> int:
    profile = config.profile(args.profile)
    summary = run_metadata(
        MetadataRequest(
            database=profile.database,
            environment=profile.environment,
            library_name=args.library,
            source_name=args.source_name,
            root=args.root,
            media_filter=args.media_type,
            batch_size=config.metadata_batch_size,
            generated_paths=_generated_paths(config, args.profile),
            panorama_threshold=config.panorama_aspect_ratio_threshold,
            timeout_seconds=config.metadata_timeout_seconds,
            exiftool_command=config.exiftool_command,
            ffprobe_command=config.ffprobe_command,
            force=args.force,
        )
    )
    print(f"Selected: {summary.selected_count}")
    print(f"Extracted: {summary.extracted_count}")
    print(f"Cached: {summary.cached_count}")
    print(f"Errors: {summary.error_count}")
    return 1 if summary.error_count else 0


def _handle_dates_resolve(args: argparse.Namespace, config: AppConfig) -> int:
    profile = config.profile(args.profile)
    summary = run_date_resolution(
        DateResolutionRequest(
            database=profile.database,
            environment=profile.environment,
            library_name=args.library,
            source_name=args.source_name,
            media_filter=args.media_type,
            batch_size=config.date_batch_size,
            future_tolerance_days=config.date_future_tolerance_days,
            conflict_tolerance_seconds=config.date_conflict_tolerance_seconds,
            suspicious_year_at_or_before=config.date_suspicious_year_at_or_before,
            filesystem_gap_days=config.date_filesystem_gap_days,
            allow_filesystem_fallback=config.date_allow_filesystem_fallback,
            force=args.force,
        )
    )
    print(f"Selected: {summary.selected_count}")
    print(f"Resolved: {summary.resolved_count}")
    print(f"Suspicious: {summary.suspicious_count}")
    print(f"Conflicts: {summary.conflict_count}")
    print(f"No date: {summary.no_date_count}")
    print(f"Cached: {summary.cached_count}")
    return 0


def _handle_dates_list(args: argparse.Namespace, config: AppConfig) -> int:
    profile = config.profile(args.profile)
    selected_status = args.status.upper().replace("-", "_") if args.status else None
    rows = list_date_resolutions(
        profile.database,
        profile.environment,
        args.library,
        args.source_name,
        selected_status,
    )
    if not rows:
        print("No date resolutions found.")
        return 0
    print("PATH\tTYPE\tSTATUS\tLOCAL_DATE\tTIMEZONE\tSOURCE\tPRECISION\tCONFIDENCE\tREASONS")
    for row in rows:
        print(
            f"{row.relative_path}\t{row.media_type}\t{row.status}\t"
            f"{row.effective_capture_local or ''}\t{row.capture_timezone or ''}\t"
            f"{row.capture_date_source or ''}\t{row.capture_date_precision}\t"
            f"{row.capture_date_confidence}\t"
            f"{','.join(row.reasons)}"
        )
    return 0


def _handle_associations_detect(args: argparse.Namespace, config: AppConfig) -> int:
    profile = config.profile(args.profile)
    summary = run_association_detection(
        AssociationRequest(
            database=profile.database,
            environment=profile.environment,
            library_name=args.library,
            source_name=args.source_name,
        )
    )
    print(f"Files: {summary.file_count}")
    print(f"Relations: {summary.relation_count}")
    print(f"Live Photos: {summary.live_photo_count}")
    print(f"RAW/JPEG pairs: {summary.raw_jpeg_count}")
    print(f"Sidecars: {summary.sidecar_count}")
    print(f"Conflicts: {summary.conflict_count}")
    return 0


def _handle_associations_list(args: argparse.Namespace, config: AppConfig) -> int:
    profile = config.profile(args.profile)
    relation_types = {
        "live-photo": "LIVE_PHOTO_PAIR",
        "raw-jpeg": "RAW_JPEG_PAIR",
        "sidecar": "SIDECAR_ASSOCIATION",
    }
    relation_type = relation_types.get(args.relation_type)
    rows = list_associations(
        profile.database,
        profile.environment,
        args.library,
        args.source_name,
        relation_type,
        args.include_inactive,
    )
    if not rows:
        print("No associations found.")
        return 0
    print("TYPE\tSTATUS\tCONFIDENCE\tMETHOD\tPRIMARY\tCOMPANION\tACTIVE")
    for row in rows:
        print(
            f"{row.relation_type}\t{row.status}\t{row.confidence}\t"
            f"{row.match_method}\t{row.primary_path}\t{row.companion_path}\t"
            f"{'YES' if row.active else 'NO'}"
        )
    return 0


def _handle_hashes_calculate(args: argparse.Namespace, config: AppConfig) -> int:
    profile = config.profile(args.profile)
    summary = run_hashing(
        HashRequest(
            database=profile.database,
            environment=profile.environment,
            library_name=args.library,
            source_name=args.source_name,
            root=args.root,
            media_filter=args.media_type,
            batch_size=config.hash_batch_size,
            chunk_size_bytes=config.hash_chunk_size_bytes,
            generated_paths=_generated_paths(config, args.profile),
            force=args.force,
        )
    )
    print(f"Selected: {summary.selected_count}")
    print(f"Hashed: {summary.hashed_count}")
    print(f"Cached: {summary.cached_count}")
    print(f"Errors: {summary.error_count}")
    print(f"Bytes hashed: {summary.bytes_hashed}")
    return 1 if summary.error_count else 0


def _handle_hashes_list(args: argparse.Namespace, config: AppConfig) -> int:
    profile = config.profile(args.profile)
    rows = list_hashes(
        profile.database,
        profile.environment,
        args.library,
        args.source_name,
    )
    if not rows:
        print("No hashes found.")
        return 0
    print("PATH\tTYPE\tSIZE_BYTES\tSHA256\tFINISHED_AT")
    for row in rows:
        print(
            f"{row.relative_path}\t{row.media_type}\t{row.size_bytes}\t"
            f"{row.digest}\t{row.finished_at}"
        )
    return 0


def _handle_duplicates_candidates(args: argparse.Namespace, config: AppConfig) -> int:
    profile = config.profile(args.profile)
    groups = list_size_candidates(
        profile.database,
        profile.environment,
        args.library,
        args.media_type,
    )
    if not groups:
        print("No same-size candidates found.")
        return 0
    candidate_count = sum(len(group.members) for group in groups)
    print(f"Candidate groups: {len(groups)}")
    print(f"Candidate files: {candidate_count}")
    print("SIZE_BYTES\tSOURCE\tPATH\tTYPE\tSHA256")
    for group in groups:
        for member in group.members:
            digest = member.sha256 or "NOT_CALCULATED"
            print(
                f"{group.size_bytes}\t{member.source_name}\t{member.relative_path}\t"
                f"{member.media_type}\t{digest}"
            )
    return 0


def _handle_duplicates_exact(args: argparse.Namespace, config: AppConfig) -> int:
    profile = config.profile(args.profile)
    groups = list_exact_duplicates(
        profile.database,
        profile.environment,
        args.library,
        args.media_type,
        config.duplicate_source_type_priority,
    )
    if not groups:
        print("No exact duplicate groups found.")
        return 0
    duplicate_count = sum(len(group.members) for group in groups)
    print(f"Exact duplicate groups: {len(groups)}")
    print(f"Exact duplicate files: {duplicate_count}")
    print("SHA256\tSIZE_BYTES\tSOURCE\tSOURCE_TYPE\tPATH\tTYPE\tPREFERENCE")
    for group in groups:
        for member in group.members:
            preference = (
                group.preference_status
                if member.media_id == group.preferred_media_id
                else "REVIEW"
            )
            print(
                f"{group.sha256}\t{member.size_bytes}\t{member.source_name}\t"
                f"{member.source_type}\t{member.relative_path}\t{member.media_type}\t"
                f"{preference}"
            )
    return 0


def _handle_duplicates_report(args: argparse.Namespace, config: AppConfig) -> int:
    profile = config.profile(args.profile)
    count = export_exact_duplicate_report(
        profile.database,
        profile.environment,
        args.library,
        args.media_type,
        config.duplicate_source_type_priority,
        args.output,
        args.report_format,
    )
    print(f"Exact duplicate report rows: {count}")
    print(f"Report: {args.output.expanduser().resolve()}")
    return 0


def _handle_plan_create(args: argparse.Namespace, config: AppConfig) -> int:
    profile = config.profile(args.profile)
    summary = create_year_or_no_date_plan(
        profile.database, profile.environment, args.library
    )
    print(f"Plan ID: {summary.plan_id}")
    print(f"Status: {summary.status}")
    print(f"Items: {summary.item_count}")
    print(f"Conflicts: {summary.conflict_count}")
    print(f"Checksum: {summary.checksum}")
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
        elif getattr(args, "batch_command", None):
            command_name = f"batch-{args.batch_command}"
        elif getattr(args, "provenance_command", None):
            command_name = f"provenance-{args.provenance_command}"
        elif getattr(args, "plan_command", None):
            command_name = f"plan-{args.plan_command}"
        elif getattr(args, "tools_command", None):
            command_name = f"tools-{args.tools_command}"
        elif getattr(args, "dates_command", None):
            command_name = f"dates-{args.dates_command}"
        elif getattr(args, "associations_command", None):
            command_name = f"associations-{args.associations_command}"
        elif getattr(args, "hashes_command", None):
            command_name = f"hashes-{args.hashes_command}"
        elif getattr(args, "duplicates_command", None):
            command_name = f"duplicates-{args.duplicates_command}"
        if args.command in {"scan", "metadata"} or (
            args.command == "hashes" and args.hashes_command == "calculate"
        ):
            ensure_external_working_paths(
                args.root,
                _generated_paths(config, args.profile),
            )
        configure_logging(config.logs, config.log_level, command_name)
        LOGGER.info("Starting command=%s profile=%s", command_name, args.profile or config.default_profile)
        return int(args.handler(args, config))
    except MediaToolkitError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
