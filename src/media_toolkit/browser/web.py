"""Loopback-only, read-only browser for an organized local media library."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import shutil
import subprocess
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
    source_name: str
    import_batch: str
    original_filename: str
    original_relative_path: str
    size_bytes: int


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
        filters = _filters()
        entries = _gallery_entries(database, library_id, filters, page)
        all_entries = _browser_rows(database, library_id)
        return render_template_string(
            _GALLERY_TEMPLATE,
            library_name=library_name,
            entries=entries,
            page=page,
            filters=filters,
            sources=sorted({entry.source_name for entry in all_entries}),
            extensions=sorted({entry.extension for entry in all_entries}),
            page_size=PAGE_SIZE,
        )

    @app.get("/media/<media_id>")
    def detail(media_id: str) -> str:
        filters = _filters()
        entries = _filtered_entries(_browser_rows(database, library_id), filters)
        entry = next((item for item in entries if item.media_id == media_id), None)
        if entry is None:
            abort(404, "Cataloged media was not found in this browser scope.")
        available = _is_available(resolved_root, entry.current_relative_path)
        return render_template_string(
            _DETAIL_TEMPLATE,
            library_name=library_name,
            entry=entry,
            available=available,
            previous=_neighbor(entries, entry.media_id, -1),
            next_item=_neighbor(entries, entry.media_id, 1),
            provenance=_provenance_rows(database, library_id, media_id),
            metadata=_metadata_row(database, media_id),
            duplicates=_duplicate_rows(database, library_id, media_id),
            return_query=_query_string(filters),
        )

    @app.get("/media/<media_id>/thumbnail")
    def thumbnail(media_id: str):
        entry = _find_media(database, library_id, media_id)
        if entry is None:
            abort(404, "A thumbnail is unavailable for this media entry.")
        try:
            original = resolve_cataloged_file(resolved_root, entry.current_relative_path)
            if entry.media_type == "PHOTO":
                thumbnail_path = _cached_photo_thumbnail(original, resolved_cache, media_id)
            elif entry.media_type == "VIDEO":
                thumbnail_path = _cached_video_thumbnail(original, resolved_cache, media_id)
            else:
                abort(404, "A thumbnail is unavailable for this media type.")
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


def _gallery_entries(database: Path, library_id: str, filters: dict[str, str], page: int) -> list[BrowserMedia]:
    filtered = _filtered_entries(_browser_rows(database, library_id), filters)
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
            SELECT mf.media_id, mf.media_type, mf.extension, mf.status, mf.size_bytes,
                   o.current_relative_path, o.original_filename, o.original_relative_path,
                   s.name AS source_name, b.name AS import_batch,
                   attempt.effective_capture_local
            FROM media_file AS mf
            JOIN file_observation AS o ON o.media_id = mf.media_id
            JOIN source AS s ON s.source_id = o.source_id
            JOIN import_batch AS b ON b.import_batch_id = o.import_batch_id
            LEFT JOIN media_date_resolution AS current ON current.media_id = mf.media_id
            LEFT JOIN date_resolution_attempt AS attempt ON attempt.resolution_id = current.resolution_id
            WHERE s.library_id = ?
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
            source_name=str(row["source_name"]),
            import_batch=str(row["import_batch"]),
            original_filename=str(row["original_filename"]),
            original_relative_path=str(row["original_relative_path"]),
            size_bytes=int(row["size_bytes"]),
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


def _filtered_entries(entries: list[BrowserMedia], filters: dict[str, str]) -> list[BrowserMedia]:
    query = filters.get("q", "").casefold()
    result = []
    for entry in entries:
        if not _matches_year(entry, filters.get("year")):
            continue
        if filters.get("month") and not (entry.capture_local or "").startswith(filters["month"]):
            continue
        if filters.get("type") and entry.media_type.casefold() != filters["type"].casefold():
            continue
        if filters.get("source") and entry.source_name != filters["source"]:
            continue
        if filters.get("extension") and entry.extension.casefold() != filters["extension"].casefold():
            continue
        haystack = " ".join((entry.current_relative_path, entry.original_filename, entry.original_relative_path, entry.source_name, entry.import_batch)).casefold()
        if query and query not in haystack:
            continue
        result.append(entry)
    return result


def _filters() -> dict[str, str]:
    values = {key: request.args.get(key, "").strip() for key in ("year", "month", "type", "source", "extension", "q")}
    if values["year"] and values["year"] != "no_date" and not (len(values["year"]) == 4 and values["year"].isdecimal()):
        abort(400, "Year must be four digits or no_date.")
    if values["month"] and not (len(values["month"]) == 7 and values["month"][4] == "-" and values["month"].replace("-", "").isdecimal()):
        abort(400, "Month must use YYYY-MM.")
    if values["type"] and values["type"].upper() not in {"PHOTO", "VIDEO"}:
        abort(400, "Media type must be PHOTO or VIDEO.")
    return {key: value for key, value in values.items() if value}


def _query_string(filters: dict[str, str]) -> str:
    from urllib.parse import urlencode
    return urlencode(filters)


def _neighbor(entries: list[BrowserMedia], media_id: str, direction: int) -> BrowserMedia | None:
    index = next(index for index, entry in enumerate(entries) if entry.media_id == media_id)
    neighbor_index = index + direction
    return entries[neighbor_index] if 0 <= neighbor_index < len(entries) else None


def _provenance_rows(database: Path, library_id: str, media_id: str):
    with open_readonly_database(database) as connection:
        return connection.execute("""SELECT o.original_filename, o.original_relative_path, o.current_relative_path, s.source_type, s.name AS source_name, b.name AS import_batch, o.source_context_raw, o.source_context_normalized FROM file_observation AS o JOIN source AS s ON s.source_id=o.source_id JOIN import_batch AS b ON b.import_batch_id=o.import_batch_id WHERE o.media_id=? AND s.library_id=? ORDER BY o.observed_at, o.observation_id""", (media_id, library_id)).fetchall()


def _metadata_row(database: Path, media_id: str):
    with open_readonly_database(database) as connection:
        return connection.execute("SELECT * FROM media_metadata WHERE media_id = ?", (media_id,)).fetchone()


def _duplicate_rows(database: Path, library_id: str, media_id: str):
    with open_readonly_database(database) as connection:
        return connection.execute(
            """
            SELECT other.original_relative_path, other.current_relative_path, source.name AS source_name
            FROM file_observation AS current
            JOIN file_observation AS other ON other.media_item_id = current.media_item_id
            JOIN source ON source.source_id = other.source_id
            WHERE current.media_id = ? AND source.library_id = ?
              AND current.media_item_id IS NOT NULL
            ORDER BY other.original_relative_path, other.observation_id
            """,
            (media_id, library_id),
        ).fetchall()


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


def _cached_video_thumbnail(original: Path, cache_root: Path, media_id: str) -> Path:
    """Render one representative video frame externally when ffmpeg is available."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise ValueError("Video thumbnails require ffmpeg to be installed.")
    stat = original.stat()
    signature = sha256(
        f"{media_id}:{stat.st_size}:{stat.st_mtime_ns}:{THUMBNAIL_SIZE}:video-v1".encode()
    ).hexdigest()
    destination = cache_root / signature[:2] / f"{signature}.jpg"
    if destination.is_file():
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f"{destination.stem}.partial.jpg")
    completed = subprocess.run(
        [
            ffmpeg, "-v", "error", "-ss", "00:00:01", "-i", str(original),
            "-frames:v", "1", "-vf", f"scale={THUMBNAIL_SIZE}:-2", str(temporary),
        ],
        check=False, capture_output=True, text=True,
    )
    if completed.returncode != 0 or not temporary.is_file():
        temporary.unlink(missing_ok=True)
        raise ValueError("Video thumbnail generation failed.")
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
<main><nav class="pager"><a class="button active" href="/">Browser</a><a class="button" href="http://127.0.0.1:8081">Database</a><a class="button" href="http://127.0.0.1:8082">Review</a></nav><div class="eyebrow">Local read-only media browser</div><h1>{{ library_name }}</h1><p class="lede">Organized-library media only. The toAnalyze directory is always excluded.</p>
<form class="filters" method="get"><input name="q" value="{{ filters.get('q', '') }}" placeholder="Search filename or provenance"><input name="year" value="{{ filters.get('year', '') }}" placeholder="Year"><input name="month" value="{{ filters.get('month', '') }}" placeholder="YYYY-MM"><select name="type"><option value="">All types</option><option value="PHOTO">Photos</option><option value="VIDEO">Videos</option></select><select name="source"><option value="">All sources</option>{% for source in sources %}<option>{{ source }}</option>{% endfor %}</select><select name="extension"><option value="">All extensions</option>{% for extension in extensions %}<option>{{ extension }}</option>{% endfor %}</select><button class="button">Filter</button></form>
<p class="meta">Page {{ page }}. Up to {{ page_size }} entries per page.</p><section class="gallery">{% for entry in entries %}<a class="card" href="{{ url_for('detail', media_id=entry.media_id, **filters) }}">{% if entry.status == 'PRESENT' %}<img class="thumb" loading="lazy" src="{{ url_for('thumbnail', media_id=entry.media_id) }}" alt="Thumbnail for {{ entry.current_relative_path }}">{% else %}<div class="placeholder">Cataloged file missing</div>{% endif %}<div class="caption"><strong>{{ entry.current_relative_path }}</strong>{{ entry.media_type }} · {{ entry.capture_local or 'No resolved date' }}</div></a>{% endfor %}</section>{% if not entries %}<p class="notice">No media match this page and filter.</p>{% endif %}<nav class="pager">{% if page > 1 %}<a class="button" href="/?page={{ page - 1 }}&{{ filters|urlencode }}">Previous</a>{% endif %}{% if entries|length == page_size %}<a class="button" href="/?page={{ page + 1 }}&{{ filters|urlencode }}">Next</a>{% endif %}</nav></main>
"""

_DETAIL_TEMPLATE = """<!doctype html><title>{{ entry.current_relative_path }}</title>""" + _STYLE + """
<main><nav class="pager"><a class="button" href="/?{{ return_query }}">Browser</a><a class="button" href="http://127.0.0.1:8081">Database</a><a class="button" href="http://127.0.0.1:8082">Review</a></nav><a class="button" href="/?{{ return_query }}">Back to gallery</a><div class="eyebrow" style="margin-top:24px">Cataloged media</div><h1>{{ entry.current_relative_path }}</h1><section class="detail"><div>{% if available and entry.media_type == 'PHOTO' %}<img class="full" src="{{ url_for('content', media_id=entry.media_id) }}" alt="{{ entry.current_relative_path }}">{% elif available and entry.media_type == 'VIDEO' %}<video class="full" controls src="{{ url_for('content', media_id=entry.media_id) }}>Preview unavailable in browser.</video>{% else %}<div class="placeholder">The catalog entry remains visible, but its file is unavailable under the selected media root.</div>{% endif %}</div><aside class="panel"><p><strong>Type</strong><br>{{ entry.media_type }}</p><p><strong>Extension and size</strong><br>{{ entry.extension }} · {{ entry.size_bytes }} bytes</p><p><strong>Capture date</strong><br>{{ entry.capture_local or 'No resolved date' }}</p><p><strong>Catalog status</strong><br>{{ entry.status }}</p><p><strong>Current relative path</strong><br><span class="path">{{ entry.current_relative_path }}</span></p>{% if metadata %}<p><strong>Technical metadata</strong><br>{{ metadata['display_width_px'] or '-' }} × {{ metadata['display_height_px'] or '-' }}{% if metadata['duration_ms'] %} · {{ metadata['duration_ms'] }} ms{% endif %}</p>{% endif %}</aside></section><section class="panel"><h2>Immutable provenance</h2>{% for item in provenance %}<p class="path"><strong>{{ item['source_name'] }} · {{ item['import_batch'] }}</strong><br>Original: {{ item['original_relative_path'] }}<br>Current: {{ item['current_relative_path'] }}</p>{% endfor %}</section>{% if duplicates|length > 1 %}<section class="panel"><h2>Exact duplicate observations</h2>{% for item in duplicates %}<p class="path">{{ item['source_name'] }} · {{ item['original_relative_path'] }}</p>{% endfor %}</section>{% endif %}<nav class="pager">{% if previous %}<a id="previous-link" class="button" href="{{ url_for('detail', media_id=previous.media_id) }}?{{ return_query }}">Previous</a>{% endif %}{% if next_item %}<a id="next-link" class="button" href="{{ url_for('detail', media_id=next_item.media_id) }}?{{ return_query }}">Next</a>{% endif %}</nav></main><script>document.addEventListener('keydown', event => { if (event.target.matches('input,select,textarea')) return; if (event.key === 'Escape') location.href='/?{{ return_query }}'; if (event.key === 'ArrowLeft') document.getElementById('previous-link')?.click(); if (event.key === 'ArrowRight') document.getElementById('next-link')?.click(); });</script>
"""
