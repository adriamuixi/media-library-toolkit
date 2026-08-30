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


_STYLE = """
<style>
  :root { color-scheme: dark; font-family: Inter, ui-sans-serif, system-ui, sans-serif; background: #10121a; color: #edf0f7; }
  * { box-sizing: border-box; }
  body { margin: 0; background: radial-gradient(circle at top right, #232849, #10121a 42rem); min-height: 100vh; }
  main { width: min(1100px, calc(100% - 40px)); margin: 0 auto; padding: 56px 0; }
  .eyebrow { color: #9ca9ff; font-size: .78rem; font-weight: 750; letter-spacing: .12em; text-transform: uppercase; }
  h1 { margin: 8px 0 10px; font-size: clamp(2rem, 5vw, 3.25rem); letter-spacing: -.05em; }
  .lede { color: #b9c0d3; max-width: 650px; line-height: 1.6; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(215px, 1fr)); gap: 16px; margin-top: 34px; }
  .card { display: block; min-height: 154px; padding: 22px; border: 1px solid #303653; border-radius: 18px; background: rgba(24, 28, 43, .78); color: #edf0f7; text-decoration: none; transition: transform .15s, border-color .15s; }
  .card:hover { transform: translateY(-3px); border-color: #8896ff; }
  .card strong { display: block; margin-bottom: 10px; font-size: 1.08rem; }
  .card span, .muted { color: #aeb7cb; line-height: 1.5; }
  .notice { margin-top: 32px; padding: 15px 17px; border-left: 3px solid #7180f4; border-radius: 6px; background: #1a1f31; color: #c7cde0; }
  .back { color: #aeb9ff; text-decoration: none; font-weight: 650; }
  .table-wrap { overflow-x: auto; margin-top: 28px; border: 1px solid #303653; border-radius: 16px; background: rgba(24, 28, 43, .78); }
  table { width: 100%; border-collapse: collapse; min-width: 660px; }
  th, td { padding: 15px 17px; text-align: left; border-bottom: 1px solid #2d334d; vertical-align: top; }
  th { color: #9ca9ff; font-size: .75rem; letter-spacing: .08em; text-transform: uppercase; }
  td { color: #dce1ed; font-size: .92rem; line-height: 1.45; overflow-wrap: anywhere; }
  tr:last-child td { border-bottom: 0; }
  .pager { display: flex; gap: 10px; margin-top: 22px; }
  .button { padding: 9px 13px; border: 1px solid #46507b; border-radius: 9px; color: #dce1ff; text-decoration: none; font-weight: 650; }
  .button:hover { background: #293055; }
  @media (max-width: 600px) { main { width: min(100% - 28px, 1100px); padding: 36px 0; } }
</style>
"""

_INDEX_TEMPLATE = """<!doctype html>
<title>Media Library Review</title>""" + _STYLE + """
<main>
  <div class="eyebrow">Local catalog review</div>
  <h1>Media Library Review</h1>
  <p class="lede">Review catalog evidence safely. Library: <strong>{{ library_name }}</strong>. Results are paginated at {{ page_size }} rows.</p>
  <section class="grid">
    <a class="card" href="/duplicates"><strong>Exact duplicate groups</strong><span>Compare every observed path that shares the same SHA-256 content.</span></a>
    <a class="card" href="/dates?state=conflict"><strong>Date conflicts</strong><span>Review contradictory capture-date evidence before planning.</span></a>
    <a class="card" href="/dates?state=no_date"><strong>Media without a date</strong><span>Inspect media with no accepted effective capture date.</span></a>
    <a class="card" href="/dates?state=suspicious"><strong>Suspicious dates</strong><span>Inspect dates that need a human confirmation.</span></a>
  </section>
  <p class="notice">This interface reads catalog data only. It does not serve, alter, move, or rename media.</p>
</main>
"""

_TABLE_TEMPLATE = """<!doctype html>
<title>{{ title }}</title>""" + _STYLE + """
<main>
  <a class="back" href="/">← Review index</a>
  <div class="eyebrow" style="margin-top: 32px;">Catalog review</div>
  <h1>{{ title }}</h1>
  <div class="table-wrap">
    <table>
      <thead><tr>{% for column in columns %}<th>{{ column }}</th>{% endfor %}</tr></thead>
      <tbody>{% for row in rows %}<tr>{% for value in row %}<td>{{ value }}</td>{% endfor %}</tr>{% endfor %}</tbody>
    </table>
  </div>
  {% if not rows %}<p class="notice">No matching records in this page.</p>{% endif %}
  <nav class="pager">
    {% if page > 1 %}<a class="button" href="{{ base_path }}{% if '?' in base_path %}&{% else %}?{% endif %}page={{ page - 1 }}">Previous</a>{% endif %}
    <a class="button" href="{{ base_path }}{% if '?' in base_path %}&{% else %}?{% endif %}page={{ page + 1 }}">Next</a>
  </nav>
</main>
"""
