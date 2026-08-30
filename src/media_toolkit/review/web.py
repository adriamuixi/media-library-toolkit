"""Loopback-only local HTML review interface."""

from __future__ import annotations

from pathlib import Path

from flask import Flask, abort, render_template_string, request

from media_toolkit.catalog.database import open_database, require_database
from media_toolkit.errors import CatalogError


PAGE_SIZE = 50


def create_review_app(database: Path, environment: str, library_name: str) -> Flask:
    """Create a catalog-backed local review app without filesystem media access."""
    require_database(database, environment)
    with open_database(database) as connection:
        library = connection.execute(
            "SELECT library_id FROM library WHERE environment = ? AND name = ? COLLATE NOCASE",
            (environment.upper(), library_name.strip()),
        ).fetchone()
    if library is None:
        raise CatalogError(f"Library '{library_name}' does not exist in the selected profile.")
    library_id = library["library_id"]
    app = Flask(__name__)
    app.config.update(DATABASE=database, ENVIRONMENT=environment.upper(), LIBRARY_ID=library_id)

    @app.get("/")
    def index() -> str:
        return render_template_string(
            _INDEX_TEMPLATE,
            library_name=library_name,
            page_size=PAGE_SIZE,
        )

    @app.get("/duplicates")
    def duplicates() -> str:
        page = _page_number()
        with open_database(database) as connection:
            rows = connection.execute(
                """
                SELECT mi.sha256, COUNT(DISTINCT o.observation_id) AS observation_count,
                       GROUP_CONCAT(o.original_relative_path, ' | ') AS original_paths
                FROM media_item AS mi
                JOIN file_observation AS o ON o.media_item_id = mi.media_item_id
                JOIN source AS s ON s.source_id = o.source_id
                WHERE s.library_id = ?
                GROUP BY mi.media_item_id, mi.sha256
                HAVING COUNT(DISTINCT o.observation_id) > 1
                ORDER BY mi.sha256
                LIMIT ? OFFSET ?
                """,
                (library_id, PAGE_SIZE, (page - 1) * PAGE_SIZE),
            ).fetchall()
        return render_template_string(
            _TABLE_TEMPLATE,
            title="Exact duplicate groups",
            page=page,
            columns=("SHA-256", "Observations", "Historical paths"),
            rows=[(row["sha256"], row["observation_count"], row["original_paths"]) for row in rows],
            base_path="/duplicates",
        )

    @app.get("/dates")
    def dates() -> str:
        page = _page_number()
        state = request.args.get("state", "all").upper()
        allowed_states = {"ALL", "CONFLICT", "NO_DATE", "SUSPICIOUS"}
        if state not in allowed_states:
            abort(400, "Unsupported date review state.")
        clauses = ["s.library_id = ?"]
        parameters: list[object] = [library_id]
        if state != "ALL":
            clauses.append("attempt.status = ?")
            parameters.append(state)
        parameters.extend((PAGE_SIZE, (page - 1) * PAGE_SIZE))
        with open_database(database) as connection:
            rows = connection.execute(
                f"""
                SELECT mf.media_id, o.current_relative_path, attempt.status,
                       attempt.effective_capture_local, attempt.reasons_json
                FROM file_observation AS o
                JOIN source AS s ON s.source_id = o.source_id
                JOIN media_file AS mf ON mf.media_id = o.media_id
                JOIN media_date_resolution AS current ON current.media_id = mf.media_id
                JOIN date_resolution_attempt AS attempt ON attempt.resolution_id = current.resolution_id
                WHERE {' AND '.join(clauses)}
                ORDER BY attempt.status, o.current_relative_path
                LIMIT ? OFFSET ?
                """,
                parameters,
            ).fetchall()
        return render_template_string(
            _TABLE_TEMPLATE,
            title=f"Date review: {state.lower()}",
            page=page,
            columns=("Path", "State", "Effective local date", "Reasons"),
            rows=[
                (row["current_relative_path"], row["status"], row["effective_capture_local"] or "-", row["reasons_json"])
                for row in rows
            ],
            base_path=f"/dates?state={state.lower()}",
        )

    return app


def _page_number() -> int:
    value = request.args.get("page", "1")
    try:
        page = int(value)
    except ValueError:
        abort(400, "Page must be a positive integer.")
    if page < 1:
        abort(400, "Page must be a positive integer.")
    return page


_INDEX_TEMPLATE = """<!doctype html>
<title>Media Library Review</title>
<h1>Media Library Review</h1>
<p>Library: {{ library_name }}. Results are paginated at {{ page_size }} rows.</p>
<ul>
  <li><a href="/duplicates">Exact duplicate groups</a></li>
  <li><a href="/dates?state=conflict">Date conflicts</a></li>
  <li><a href="/dates?state=no_date">Media without a date</a></li>
  <li><a href="/dates?state=suspicious">Suspicious dates</a></li>
</ul>
<p>This interface reads catalog data only. It does not serve, alter, move, or rename media.</p>
"""

_TABLE_TEMPLATE = """<!doctype html>
<title>{{ title }}</title>
<h1>{{ title }}</h1>
<p><a href="/">Back to review index</a></p>
<table border="1">
  <thead><tr>{% for column in columns %}<th>{{ column }}</th>{% endfor %}</tr></thead>
  <tbody>{% for row in rows %}<tr>{% for value in row %}<td>{{ value }}</td>{% endfor %}</tr>{% endfor %}</tbody>
</table>
{% if not rows %}<p>No matching records.</p>{% endif %}
<p>
  {% if page > 1 %}<a href="{{ base_path }}{% if '?' in base_path %}&{% else %}?{% endif %}page={{ page - 1 }}">Previous</a>{% endif %}
  <a href="{{ base_path }}{% if '?' in base_path %}&{% else %}?{% endif %}page={{ page + 1 }}">Next</a>
</p>
"""
