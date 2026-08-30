"""Deterministic year-or-no-date plan generation without media mutation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import csv
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

from media_toolkit import __version__
from media_toolkit.catalog.database import open_database, require_database
from media_toolkit.errors import CatalogError


@dataclass(frozen=True)
class PlanSummary:
    """One immutable organization plan summary."""

    plan_id: str
    status: str
    item_count: int
    conflict_count: int
    checksum: str


@dataclass(frozen=True)
class PlanItemRecord:
    """One reviewable organization plan item."""

    destination_relative_path: str
    association_group_key: str | None
    status: str
    reason: str | None


@dataclass(frozen=True)
class _AssociationGroup:
    """One active, unambiguous association component for planning."""

    key: str
    media_ids: frozenset[str]
    anchor_media_id: str


def _association_groups(connection, library_id: str) -> tuple[dict[tuple[str, str], _AssociationGroup], set[tuple[str, str]]]:
    """Return active detected groups and media blocked by active association conflicts."""
    rows = connection.execute(
        """
        SELECT source_id, primary_media_id, companion_media_id, status
        FROM media_relation
        WHERE library_id = ? AND active = 1
        ORDER BY source_id, relation_key, primary_media_id, companion_media_id
        """,
        (library_id,),
    ).fetchall()
    blocked: set[tuple[str, str]] = set()
    adjacency: dict[tuple[str, str], set[str]] = {}
    anchors: dict[tuple[str, str], set[str]] = {}
    for row in rows:
        source_id = row["source_id"]
        primary = row["primary_media_id"]
        companion = row["companion_media_id"]
        if row["status"] == "CONFLICT":
            blocked.update(((source_id, primary), (source_id, companion)))
            continue
        primary_key = (source_id, primary)
        companion_key = (source_id, companion)
        adjacency.setdefault(primary_key, set()).add(companion)
        adjacency.setdefault(companion_key, set()).add(primary)
        anchors.setdefault(primary_key, set()).add(primary)
    groups: dict[tuple[str, str], _AssociationGroup] = {}
    visited: set[tuple[str, str]] = set()
    for start in sorted(adjacency):
        if start in visited:
            continue
        source_id = start[0]
        pending = [start]
        members: set[str] = set()
        component_anchors: set[str] = set()
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            members.add(current[1])
            component_anchors.update(anchors.get(current, set()))
            pending.extend((source_id, item) for item in adjacency[current] if (source_id, item) not in visited)
        ordered_members = sorted(members)
        key = sha256(f"{source_id}:{','.join(ordered_members)}".encode()).hexdigest()
        anchor = sorted(component_anchors or members)[0]
        group = _AssociationGroup(key, frozenset(members), anchor)
        for media_id in members:
            groups[(source_id, media_id)] = group
    return groups, blocked


def create_year_or_no_date_plan(
    database: Path, environment: str, library_name: str
) -> PlanSummary:
    """Create a deterministic DRAFT or REVIEW_REQUIRED catalog plan."""
    require_database(database, environment)
    with open_database(database) as connection:
        library = connection.execute(
            "SELECT library_id FROM library WHERE environment = ? AND name = ? COLLATE NOCASE",
            (environment.upper(), library_name.strip()),
        ).fetchone()
        if library is None:
            raise CatalogError(f"Library '{library_name}' does not exist in the selected profile.")
        rows = connection.execute(
            """
            SELECT o.observation_id, o.media_id, o.original_filename, o.source_id,
                   attempt.status AS date_status, attempt.effective_capture_local
            FROM file_observation AS o
            JOIN source AS s ON s.source_id = o.source_id
            JOIN media_file AS mf ON mf.media_id = o.media_id
            LEFT JOIN media_date_resolution AS current ON current.media_id = o.media_id
            LEFT JOIN date_resolution_attempt AS attempt ON attempt.resolution_id = current.resolution_id
            WHERE s.library_id = ? AND mf.status = 'PRESENT'
            ORDER BY o.original_relative_path, o.observation_id
            """,
            (library["library_id"],),
        ).fetchall()
        association_groups, association_blocked = _association_groups(
            connection, library["library_id"]
        )
        years_by_media = {
            (row["source_id"], row["media_id"]): (
                str(row["effective_capture_local"])[:4]
                if row["date_status"] == "RESOLVED" and row["effective_capture_local"]
                else "no_date"
            )
            for row in rows
        }
        proposed: list[tuple[object, str, str | None, str | None]] = []
        for row in rows:
            media_key = (row["source_id"], row["media_id"])
            group = association_groups.get(media_key)
            year = years_by_media.get(
                (row["source_id"], group.anchor_media_id) if group else media_key,
                "no_date",
            )
            blocked_reason = "ASSOCIATION_CONFLICT" if media_key in association_blocked else None
            proposed.append((
                row, f"{year}/{row['original_filename']}",
                group.key if group else None, blocked_reason,
            ))
        destinations = {}
        for row, destination, _, _ in proposed:
            destinations.setdefault(destination, []).append(row["observation_id"])
        payload = [
            (row["observation_id"], destination, group_key, blocked_reason)
            for row, destination, group_key, blocked_reason in proposed
        ]
        checksum = sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()
        plan_id = str(uuid4())
        conflicts = sum(
            1
            for row, destination, _, blocked_reason in proposed
            if len(destinations[destination]) > 1 or blocked_reason
        )
        status = "REVIEW_REQUIRED" if conflicts else "DRAFT"
        connection.execute(
            """
            INSERT INTO organization_plan (
                plan_id, library_id, status, strategy, checksum, created_at, created_by_version
            ) VALUES (?, ?, ?, 'YEAR_OR_NO_DATE', ?, ?, ?)
            """,
            (plan_id, library["library_id"], status, checksum, datetime.now(UTC).isoformat(), __version__),
        )
        for row, destination, group_key, blocked_reason in proposed:
            collision = len(destinations[destination]) > 1
            reason = ";".join(
                part for part in (blocked_reason, "DESTINATION_COLLISION" if collision else None) if part
            ) or None
            item_status = "BLOCKED" if blocked_reason else "CONFLICT" if collision else "PROPOSED"
            connection.execute(
                """
                INSERT INTO organization_plan_item (
                    plan_item_id, plan_id, observation_id, media_id,
                    destination_relative_path, association_group_key, status, reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()), plan_id, row["observation_id"], row["media_id"], destination,
                    group_key, item_status, reason,
                ),
            )
    return PlanSummary(plan_id, status, len(proposed), conflicts, checksum)


def list_plan_items(
    database: Path, environment: str, plan_id: str
) -> list[PlanItemRecord]:
    """List one plan's deterministic review items without modifying the catalog."""
    require_database(database, environment)
    with open_database(database) as connection:
        rows = connection.execute(
            """
            SELECT item.destination_relative_path, item.association_group_key,
                   item.status, item.reason
            FROM organization_plan_item AS item
            JOIN organization_plan AS plan ON plan.plan_id = item.plan_id
            JOIN library AS library ON library.library_id = plan.library_id
            WHERE item.plan_id = ? AND library.environment = ?
            ORDER BY item.destination_relative_path, item.plan_item_id
            """,
            (plan_id, environment.upper()),
        ).fetchall()
    return [PlanItemRecord(**dict(row)) for row in rows]


def export_plan(
    database: Path, environment: str, plan_id: str, output: Path, report_format: str
) -> int:
    """Write one exclusive external CSV or JSON plan review export."""
    require_database(database, environment)
    destination = output.expanduser().resolve()
    if destination.exists():
        raise CatalogError(f"Plan export already exists: {destination}")
    with open_database(database) as connection:
        roots = connection.execute(
            """
            SELECT DISTINCT scan.root_path_snapshot
            FROM organization_plan AS plan
            JOIN scan ON scan.library_id = plan.library_id
            WHERE plan.plan_id = ?
            """,
            (plan_id,),
        ).fetchall()
        for root_row in roots:
            root = Path(root_row["root_path_snapshot"]).expanduser().resolve()
            if destination == root or destination.is_relative_to(root):
                raise CatalogError("Plan exports must remain outside media roots.")
        row = connection.execute(
            """
            SELECT plan.plan_id, plan.status AS plan_status, plan.strategy, plan.checksum,
                   item.observation_id, item.media_id, item.destination_relative_path,
                   item.association_group_key, item.status AS item_status, item.reason
            FROM organization_plan AS plan
            JOIN library AS library ON library.library_id = plan.library_id
            JOIN organization_plan_item AS item ON item.plan_id = plan.plan_id
            WHERE plan.plan_id = ? AND library.environment = ?
            ORDER BY item.destination_relative_path, item.plan_item_id
            """,
            (plan_id, environment.upper()),
        ).fetchall()
    if not row:
        raise CatalogError(f"Plan '{plan_id}' does not exist in the selected profile.")
    values = [dict(item) for item in row]
    destination.parent.mkdir(parents=True, exist_ok=True)
    if report_format == "csv":
        with destination.open("x", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=tuple(values[0]))
            writer.writeheader()
            writer.writerows(values)
    elif report_format == "json":
        with destination.open("x", encoding="utf-8") as handle:
            json.dump(values, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    else:
        raise CatalogError(f"Unsupported plan export format: {report_format}.")
    return len(values)
