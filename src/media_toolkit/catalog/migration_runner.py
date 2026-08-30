"""Small, checksum-verified SQL migration runner."""

from __future__ import annotations

from hashlib import sha256
from importlib.resources import files
import re
import sqlite3

from media_toolkit.errors import DatabaseSafetyError


MIGRATION_PATTERN = re.compile(r"^(?P<version>\d{4})_(?P<name>[a-z0-9_]+)\.sql$")


def apply_migrations(connection: sqlite3.Connection) -> None:
    """Apply pending packaged SQL migrations in version order."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            migration_name TEXT NOT NULL,
            checksum TEXT NOT NULL,
            applied_at TEXT NOT NULL,
            software_version TEXT NOT NULL
        )
        """
    )
    package = files("media_toolkit.catalog.migrations")
    migrations: list[tuple[int, str, str, str]] = []
    for resource in package.iterdir():
        match = MIGRATION_PATTERN.match(resource.name)
        if match is None:
            continue
        sql = resource.read_text(encoding="utf-8")
        migrations.append(
            (int(match.group("version")), match.group("name"), sql, sha256(sql.encode()).hexdigest())
        )

    for version, name, sql, checksum in sorted(migrations):
        existing = connection.execute(
            "SELECT checksum FROM schema_version WHERE version = ?", (version,)
        ).fetchone()
        if existing is not None:
            if existing[0] != checksum:
                raise DatabaseSafetyError(
                    f"Migration {version:04d}_{name} has changed after being applied."
                )
            continue
        connection.executescript(sql)
        connection.execute(
            """
            INSERT INTO schema_version (
                version, migration_name, checksum, applied_at, software_version
            ) VALUES (?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), ?)
            """,
            (version, name, checksum, "0.1.0"),
        )
