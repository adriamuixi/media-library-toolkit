"""Controlled COPY execution for reviewed organization plans."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
from uuid import uuid4

from media_toolkit.catalog.database import open_database, require_database
from media_toolkit.errors import CatalogError, MediaToolkitError
from media_toolkit.operations.provenance import require_write_provenance
from media_toolkit.scan.safety import resolve_cataloged_file, resolve_media_root


@dataclass(frozen=True)
class _CopyItem:
    """One validated plan item ready to copy."""

    plan_item_id: str
    media_id: str
    source_relative_path: str
    destination_relative_path: str
    sha256: str


def apply_copy_plan(
    database: Path,
    environment: str,
    plan_id: str,
    source_root: Path,
    destination_root: Path,
    confirmation: str,
) -> str:
    """Copy a clean reviewed plan after exhaustive validation and journaling."""
    require_database(database, environment)
    if confirmation != plan_id:
        raise CatalogError("WRITE confirmation must exactly match the organization plan ID.")
    source = resolve_media_root(source_root)
    destination = resolve_media_root(destination_root)
    if destination == source or destination.is_relative_to(source):
        raise CatalogError("The COPY destination root must remain outside the source media root.")
    with open_database(database) as connection:
        plan = connection.execute(
            "SELECT status FROM organization_plan WHERE plan_id = ?",
            (plan_id,),
        ).fetchone()
        if plan is None:
            raise CatalogError(f"Plan '{plan_id}' does not exist in the selected profile.")
        if plan["status"] != "DRAFT":
            raise CatalogError("Only clean DRAFT plans may enter controlled COPY execution.")
        rows = connection.execute(
            """
            SELECT item.plan_item_id, item.media_id, o.current_relative_path,
                   item.destination_relative_path, mi.sha256, item.status
            FROM organization_plan_item AS item
            JOIN file_observation AS o ON o.observation_id = item.observation_id
            JOIN media_item AS mi ON mi.media_item_id = o.media_item_id
            WHERE item.plan_id = ?
            ORDER BY item.destination_relative_path, item.plan_item_id
            """,
            (plan_id,),
        ).fetchall()
    if not rows:
        raise CatalogError("A WRITE operation requires at least one plan item.")
    if any(row["status"] != "PROPOSED" for row in rows):
        raise CatalogError("WRITE refuses plans containing conflicts or blocked items.")
    items = tuple(
        _CopyItem(
            row["plan_item_id"], row["media_id"], row["current_relative_path"],
            row["destination_relative_path"], row["sha256"],
        )
        for row in rows
    )
    require_write_provenance(database, environment, tuple(item.media_id for item in items))
    resolved_items = [
        (item, resolve_cataloged_file(source, item.source_relative_path),
         _safe_destination(destination, item.destination_relative_path))
        for item in items
    ]
    for item, source_path, destination_path in resolved_items:
        if destination_path.exists():
            raise CatalogError(f"COPY destination already exists: {item.destination_relative_path}")
        if _hash_file(source_path) != item.sha256:
            raise CatalogError(f"COPY source hash no longer matches catalog: {item.source_relative_path}")
    operation_id = str(uuid4())
    started_at = datetime.now(UTC).isoformat()
    with open_database(database) as connection:
        connection.execute(
            """
            INSERT INTO write_operation (
                operation_id, plan_id, strategy, status, source_root, destination_root, started_at
            ) VALUES (?, ?, 'COPY', 'RUNNING', ?, ?, ?)
            """,
            (operation_id, plan_id, str(source), str(destination), started_at),
        )
        _event(connection, operation_id, None, "OPERATION_STARTED", {"plan_id": plan_id})
        connection.execute(
            "UPDATE organization_plan SET status = 'APPROVED' WHERE plan_id = ?",
            (plan_id,),
        )
    try:
        for item, source_path, destination_path in resolved_items:
            _copy_verified(source_path, destination_path, item.sha256)
            with open_database(database) as connection:
                _event(
                    connection, operation_id, item.plan_item_id, "ITEM_COPIED",
                    {"destination_relative_path": item.destination_relative_path, "sha256": item.sha256},
                )
        completed_at = datetime.now(UTC).isoformat()
        with open_database(database) as connection:
            _event(connection, operation_id, None, "OPERATION_COMPLETED", {})
            connection.execute(
                "UPDATE write_operation SET status = 'COMPLETED', completed_at = ? WHERE operation_id = ?",
                (completed_at, operation_id),
            )
            connection.execute("UPDATE organization_plan SET status = 'APPLIED' WHERE plan_id = ?", (plan_id,))
    except Exception as exc:
        with open_database(database) as connection:
            _event(connection, operation_id, None, "OPERATION_FAILED", {"error": str(exc)})
            connection.execute(
                "UPDATE write_operation SET status = 'FAILED', completed_at = ?, failure_message = ? WHERE operation_id = ?",
                (datetime.now(UTC).isoformat(), str(exc), operation_id),
            )
        raise
    return operation_id


def _safe_destination(root: Path, relative_path: str) -> Path:
    """Return a non-symlink destination contained under its explicit root."""
    relative = Path(relative_path)
    if relative.is_absolute():
        raise MediaToolkitError("Organization destination path must be relative.")
    candidate = root
    for part in relative.parts:
        if part in ("", ".", ".."):
            raise MediaToolkitError("Organization destination path is unsafe.")
        candidate = candidate / part
    parent = candidate.parent
    while parent != root:
        if parent.exists() and parent.is_symlink():
            raise MediaToolkitError("Organization destination contains a symbolic link.")
        parent = parent.parent
    return candidate


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _copy_verified(source: Path, destination: Path, expected_sha256: str) -> None:
    """Copy through an exclusive temporary path, then atomically create destination."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.parent / f".{destination.name}.{uuid4().hex}.partial"
    try:
        with source.open("rb") as input_handle, temporary.open("xb") as output_handle:
            shutil.copyfileobj(input_handle, output_handle, length=1024 * 1024)
        shutil.copystat(source, temporary, follow_symlinks=False)
        if _hash_file(temporary) != expected_sha256:
            raise MediaToolkitError("Copied file hash verification failed.")
        os.link(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def _event(connection, operation_id: str, plan_item_id: str | None, event_type: str, details: dict) -> None:
    """Append one immutable write-operation journal event."""
    connection.execute(
        """
        INSERT INTO write_operation_event (
            event_id, operation_id, plan_item_id, event_type, details_json, recorded_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid4()), operation_id, plan_item_id, event_type,
            json.dumps(details, sort_keys=True), datetime.now(UTC).isoformat(),
        ),
    )
