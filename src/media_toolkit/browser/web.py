"""Loopback-only, read-only browser for an organized local media library."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from unicodedata import normalize

from flask import Flask, abort, render_template_string, request, send_file, url_for
from PIL import Image, ImageOps

from media_toolkit.catalog.database import open_readonly_database, require_database
from media_toolkit.errors import CatalogError, MediaToolkitError
from media_toolkit.scan.safety import ensure_external_working_paths, resolve_cataloged_file, resolve_media_root


PAGE_SIZE = 60
THUMBNAIL_SIZE = 480


@dataclass(frozen=True)
class BrowserMedia:
    """A single safe, catalog-backed browser entry."""

    media_id: str
    current_relative_path: str
    media_type: str
    extension: str
    status: str
    capture_local: str | None


def create_browser_app(
    database: Path,
    environment: str,
    library_name: str,
    media_root: Path,
    cache_root: Path,
) -> Flask:
    """Create a local browser that reads catalog data and media without mutation."""
    require_database(database, environment)
    resolved_root = resolve_media_root(media_root)
    ensure_external_working_paths(resolved_root, (cache_root,))
    resolved_cache = cache_root.expanduser().resolve() / "media-browser-thumbnails"
    library_id = _find_library_id(database, environment, library_name)

    app = Flask(__name__)
    app.config.update(
        DATABASE=database,
        ENVIRONMENT=environment.upper(),
        LIBRARY_ID=library_id,
        LIBRARY_NAME=library_name,
        MEDIA_ROOT=resolved_root,
        THUMBNAIL_CACHE=resolved_cache,
    )

    @app.after_request
    def security_headers(response):
        """Keep the loopback UI free from external content and type guessing."""
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self'; media-src 'self'; style-src 'self' 'unsafe-inline'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/")
    def gallery() -> str:
        page = _page_number()
        year = _year_filter()
        entries = _gallery_entries(database, library_id, year, page)
        return render_template_string(
            _GALLERY_TEMPLATE,
            library_name=library_name,
            entries=entries,
            page=page,
            year=year,
            page_size=PAGE_SIZE,
        )

    @app.get("/media/<media_id>")
    def detail(media_id: str) -> str:
        entry = _find_media(database, library_id, media_id)
        if entry is None:
            abort(404, "Cataloged media was not found in this browser scope.")
        available = _is_available(resolved_root, entry.current_relative_path)
        return render_template_string(
            _DETAIL_TEMPLATE,
            library_name=library_name,
            entry=entry,
            available=available,
        )

    @app.get("/media/<media_id>/thumbnail")
    def thumbnail(media_id: str):
        entry = _find_media(database, library_id, media_id)
        if entry is None or entry.media_type != "PHOTO":
            abort(404, "A photo thumbnail is unavailable for this media entry.")
        try:
            original = resolve_cataloged_file(resolved_root, entry.current_relative_path)
            thumbnail_path = _cached_photo_thumbnail(original, resolved_cache, media_id)
        except MediaToolkitError as exc:
            abort(404, str(exc))
        except (OSError, ValueError, Image.UnidentifiedImageError) as exc:
            abort(422, f"Thumbnail unavailable: {exc}")
        return send_file(thumbnail_path, mimetype="image/jpeg", conditional=True, max_age=0)

    @app.get("/media/<media_id>/content")
    def content(media_id: str):
        entry = _find_media(database, library_id, media_id)
        if entry is None:
            abort(404, "Cataloged media was not found in this browser scope.")
        try:
            original = resolve_cataloged_file(resolved_root, entry.current_relative_path)
        except MediaToolkitError as exc:
            abort(404, str(exc))
        return send_file(original, conditional=True, max_age=0)

    return app


def _find_library_id(database: Path, environment: str, library_name: str) -> str:
    with open_readonly_database(database) as connection:
        row = connection.execute(
            "SELECT library_id FROM library WHERE environment = ? AND name = ? COLLATE NOCASE",
            (environment.upper(), library_name.strip()),
        ).fetchone()
    if row is None:
        raise CatalogError(f"Library '{library_name}' does not exist in the selected profile.")
    return str(row["library_id"])


def _gallery_entries(database: Path, library_id: str, year: str | None, page: int) -> list[BrowserMedia]:
    rows = _browser_rows(database, library_id)
    filtered = [row for row in rows if _matches_year(row, year)]
    start = (page - 1) * PAGE_SIZE
    return filtered[start : start + PAGE_SIZE]


def _find_media(database: Path, library_id: str, media_id: str) -> BrowserMedia | None:
    for entry in _browser_rows(database, library_id):
        if entry.media_id == media_id:
            return entry
    return None


def _browser_rows(database: Path, library_id: str) -> list[BrowserMedia]:
    """Read catalog records only, then apply Unicode-safe toAnalyze exclusion."""
    with open_readonly_database(database) as connection:
        rows = connection.execute(
            """
            SELECT mf.media_id, mf.media_type, mf.extension, mf.status,
                   o.current_relative_path,
                   attempt.effective_capture_local
            FROM media_file AS mf
            JOIN file_observation AS o ON o.media_id = mf.media_id
            JOIN source AS s ON s.source_id = o.source_id
            LEFT JOIN media_date_resolution AS current ON current.media_id = mf.media_id
            LEFT JOIN date_resolution_attempt AS attempt ON attempt.resolution_id = current.resolution_id
            WHERE s.library_id = ?
              AND mf.media_type = 'PHOTO'
            GROUP BY mf.media_id
            ORDER BY CASE WHEN attempt.effective_capture_local IS NULL THEN 1 ELSE 0 END,
                     attempt.effective_capture_local, o.current_relative_path, mf.media_id
            """,
            (library_id,),
        ).fetchall()
    entries = [
        BrowserMedia(
            media_id=str(row["media_id"]),
            current_relative_path=str(row["current_relative_path"]),
            media_type=str(row["media_type"]),
            extension=str(row["extension"]),
            status=str(row["status"]),
            capture_local=row["effective_capture_local"],
        )
        for row in rows
    ]
    return [entry for entry in entries if not _is_to_analyze_path(entry.current_relative_path)]


def _is_to_analyze_path(relative_path: str) -> bool:
    """Exclude only a first path component equal to toAnalyze, case-insensitively."""
    first_component = relative_path.replace("\\", "/").split("/", 1)[0]
    return normalize("NFC", first_component).casefold() == "toanalyze"


def _matches_year(entry: BrowserMedia, year: str | None) -> bool:
    if year is None:
        return True
    if year == "no_date":
        return entry.capture_local is None
    return entry.capture_local is not None and entry.capture_local.startswith(year)


def _cached_photo_thumbnail(original: Path, cache_root: Path, media_id: str) -> Path:
    """Create or reuse a bounded JPEG thumbnail outside the media root."""
    stat = original.stat()
    signature = sha256(
        f"{media_id}:{stat.st_size}:{stat.st_mtime_ns}:{THUMBNAIL_SIZE}:v1".encode()
    ).hexdigest()
    destination = cache_root / signature[:2] / f"{signature}.jpg"
    if destination.is_file():
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".partial")
    with Image.open(original) as image:
        normalized = ImageOps.exif_transpose(image)
        normalized.thumbnail((THUMBNAIL_SIZE, THUMBNAIL_SIZE))
        if normalized.mode not in ("RGB", "L"):
            normalized = normalized.convert("RGB")
        normalized.save(temporary, format="JPEG", quality=85, optimize=True)
    temporary.replace(destination)
    return destination


def _is_available(root: Path, relative_path: str) -> bool:
    try:
        resolve_cataloged_file(root, relative_path)
    except MediaToolkitError:
        return False
    return True


def _page_number() -> int:
    value = request.args.get("page", "1")
    try:
        page = int(value)
    except ValueError:
        abort(400, "Page must be a positive integer.")
    if page < 1:
        abort(400, "Page must be a positive integer.")
    return page


def _year_filter() -> str | None:
    value = request.args.get("year")
    if value in (None, ""):
        return None
    if value == "no_date" or (len(value) == 4 and value.isdecimal()):
        return value
    abort(400, "Year must be four digits or no_date.")


_STYLE = """
<style>
  :root { color-scheme: dark; font-family: Inter, ui-sans-serif, system-ui, sans-serif; background: #10121a; color: #edf0f7; }
  * { box-sizing: border-box; } body { margin: 0; background: radial-gradient(circle at top right, #232849, #10121a 42rem); min-height: 100vh; }
  main { width: min(1280px, calc(100% - 40px)); margin: 0 auto; padding: 42px 0 60px; }
  h1 { margin: 7px 0; font-size: clamp(2rem, 5vw, 3.2rem); letter-spacing: -.05em; } .eyebrow { color: #9ca9ff; font-size: .78rem; font-weight: 750; letter-spacing: .12em; text-transform: uppercase; }
  .lede, .meta { color: #b9c0d3; line-height: 1.55; } .notice { margin: 22px 0; padding: 14px 16px; border-left: 3px solid #7180f4; border-radius: 6px; background: #1a1f31; color: #c7cde0; }
  .filters, .pager { display: flex; flex-wrap: wrap; align-items: center; gap: 9px; margin: 25px 0; }.button { padding: 9px 13px; border: 1px solid #46507b; border-radius: 9px; color: #dce1ff; text-decoration: none; font-weight: 650; }.button:hover, .button.active { background: #293055; border-color: #8896ff; }
  .gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 15px; }.card { display: block; overflow: hidden; border: 1px solid #303653; border-radius: 14px; background: rgba(24, 28, 43, .82); color: #edf0f7; text-decoration: none; }.card:hover { border-color: #8896ff; transform: translateY(-2px); }.thumb { aspect-ratio: 1; width: 100%; object-fit: cover; background: #171b2b; }.placeholder { display: grid; place-items: center; aspect-ratio: 1; padding: 16px; color: #aeb7cb; text-align: center; background: #171b2b; }.caption { padding: 11px; font-size: .86rem; overflow-wrap: anywhere; }.caption strong { display: block; margin-bottom: 5px; }.detail { display: grid; gap: 25px; grid-template-columns: minmax(0, 2fr) minmax(260px, 1fr); margin-top: 28px; }.full { width: 100%; max-height: 75vh; object-fit: contain; background: #080a10; border-radius: 14px; }.panel { border: 1px solid #303653; border-radius: 14px; padding: 20px; background: rgba(24,28,43,.82); }.path { overflow-wrap: anywhere; color: #c7cde0; } @media (max-width: 720px) { main { width: min(100% - 28px, 1280px); padding-top: 30px; }.detail { grid-template-columns: 1fr; } }
</style>
"""

_GALLERY_TEMPLATE = """<!doctype html><title>{{ library_name }} browser</title>""" + _STYLE + """
<main><div class="eyebrow">Local read-only media browser</div><h1>{{ library_name }}</h1><p class="lede">Organized-library photos only. The toAnalyze directory is always excluded. This browser never changes the catalog or media.</p>
<nav class="filters"><a class="button {% if not year %}active{% endif %}" href="/">All photos</a><a class="button {% if year == 'no_date' %}active{% endif %}" href="/?year=no_date">No date</a>{% for item in ['2020','2021','2022','2023','2024','2025','2026'] %}<a class="button {% if year == item %}active{% endif %}" href="/?year={{ item }}">{{ item }}</a>{% endfor %}</nav>
<p class="meta">Page {{ page }}. Up to {{ page_size }} entries per page.</p><section class="gallery">{% for entry in entries %}<a class="card" href="{{ url_for('detail', media_id=entry.media_id) }}">{% if entry.status == 'PRESENT' %}<img class="thumb" loading="lazy" src="{{ url_for('thumbnail', media_id=entry.media_id) }}" alt="Thumbnail for {{ entry.current_relative_path }}">{% else %}<div class="placeholder">Cataloged file missing</div>{% endif %}<div class="caption"><strong>{{ entry.current_relative_path }}</strong>{{ entry.capture_local or 'No resolved date' }}</div></a>{% endfor %}</section>{% if not entries %}<p class="notice">No photos match this page and filter.</p>{% endif %}<nav class="pager">{% if page > 1 %}<a class="button" href="/?page={{ page - 1 }}{% if year %}&year={{ year }}{% endif %}">Previous</a>{% endif %}{% if entries|length == page_size %}<a class="button" href="/?page={{ page + 1 }}{% if year %}&year={{ year }}{% endif %}">Next</a>{% endif %}</nav></main>
"""

_DETAIL_TEMPLATE = """<!doctype html><title>{{ entry.current_relative_path }}</title>""" + _STYLE + """
<main><a class="button" href="/">Back to gallery</a><div class="eyebrow" style="margin-top:24px">Cataloged media</div><h1>{{ entry.current_relative_path }}</h1><section class="detail"><div>{% if available %}<img class="full" src="{{ url_for('content', media_id=entry.media_id) }}" alt="{{ entry.current_relative_path }}">{% else %}<div class="placeholder">The catalog entry remains visible, but its file is unavailable under the selected media root.</div>{% endif %}</div><aside class="panel"><p><strong>Type</strong><br>{{ entry.media_type }}</p><p><strong>Extension</strong><br>{{ entry.extension }}</p><p><strong>Capture date</strong><br>{{ entry.capture_local or 'No resolved date' }}</p><p><strong>Catalog status</strong><br>{{ entry.status }}</p><p><strong>Current relative path</strong><br><span class="path">{{ entry.current_relative_path }}</span></p>{% if available %}<a class="button" href="{{ url_for('content', media_id=entry.media_id) }}">Open original</a>{% endif %}</aside></section></main>
"""
