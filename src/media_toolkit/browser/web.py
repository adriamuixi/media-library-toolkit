"""Loopback-only, read-only browser for an organized local media library."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
import shutil
import subprocess
from unicodedata import normalize

from flask import Flask, abort, render_template_string, request, send_file, url_for
from PIL import Image, ImageOps

from media_toolkit.browser.origin import classify_whatsapp_evidence
from media_toolkit.catalog.database import open_readonly_database, require_database
from media_toolkit.errors import CatalogError, MediaToolkitError
from media_toolkit.scan.safety import ensure_external_working_paths, resolve_cataloged_file, resolve_media_root


DEFAULT_PAGE_SIZE = 100
PAGE_SIZE_OPTIONS = (100, 200, 500)
THUMBNAIL_SIZE = 256


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
    source_type: str = "UNKNOWN"
    display_width_px: int | None = None
    display_height_px: int | None = None
    aspect_ratio: float | None = None
    orientation_class: str | None = None
    is_panorama: bool | None = None
    is_whatsapp: bool = False
    whatsapp_evidence_reason: str = "NO_WHATSAPP_EVIDENCE"


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
        page_size = int(filters.get("page_size", DEFAULT_PAGE_SIZE))
        entries = _gallery_entries(database, library_id, filters, page, page_size)
        all_entries = _browser_rows(database, library_id)
        return render_template_string(
            _GALLERY_TEMPLATE,
            library_name=library_name,
            entries=entries,
            page=page,
            filters=filters,
            sources=sorted({entry.source_name for entry in all_entries}),
            source_types=sorted({entry.source_type for entry in all_entries}),
            extensions=sorted({entry.extension for entry in all_entries}),
            page_size=page_size,
            page_size_options=PAGE_SIZE_OPTIONS,
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
            detail_sections=_detail_sections(database, library_id, media_id),
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


def _gallery_entries(
    database: Path,
    library_id: str,
    filters: dict[str, str],
    page: int,
    page_size: int,
) -> list[BrowserMedia]:
    filtered = _filtered_entries(_browser_rows(database, library_id), filters)
    start = (page - 1) * page_size
    return filtered[start : start + page_size]


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
                   o.source_context_raw,
                   s.name AS source_name, s.source_type, b.name AS import_batch,
                   attempt.effective_capture_local, metadata.display_width_px,
                   metadata.display_height_px, metadata.aspect_ratio,
                   metadata.orientation_class, metadata.is_panorama
            FROM media_file AS mf
            JOIN file_observation AS o ON o.media_id = mf.media_id
            JOIN source AS s ON s.source_id = o.source_id
            JOIN import_batch AS b ON b.import_batch_id = o.import_batch_id
            LEFT JOIN media_date_resolution AS current ON current.media_id = mf.media_id
            LEFT JOIN date_resolution_attempt AS attempt ON attempt.resolution_id = current.resolution_id
            LEFT JOIN media_metadata AS metadata ON metadata.media_id = mf.media_id
            WHERE s.library_id = ?
            GROUP BY mf.media_id
            ORDER BY CASE WHEN attempt.effective_capture_local IS NULL THEN 1 ELSE 0 END,
                     attempt.effective_capture_local, o.current_relative_path, mf.media_id
            """,
            (library_id,),
        ).fetchall()
    entries = []
    for row in rows:
        whatsapp = classify_whatsapp_evidence(
            row["original_filename"],
            row["original_relative_path"],
            row["current_relative_path"],
            row["source_context_raw"],
        )
        entries.append(BrowserMedia(
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
            source_type=str(row["source_type"]),
            display_width_px=row["display_width_px"],
            display_height_px=row["display_height_px"],
            aspect_ratio=row["aspect_ratio"],
            orientation_class=row["orientation_class"],
            is_panorama=(bool(row["is_panorama"]) if row["is_panorama"] is not None else None),
            is_whatsapp=whatsapp.is_whatsapp,
            whatsapp_evidence_reason=whatsapp.reason,
        ))
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
        if filters.get("source_type") and entry.source_type != filters["source_type"]:
            continue
        if filters.get("extension") and entry.extension.casefold() != filters["extension"].casefold():
            continue
        if filters.get("orientation") and entry.orientation_class != filters["orientation"]:
            continue
        if filters.get("panorama") == "yes" and entry.is_panorama is not True:
            continue
        if filters.get("panorama") == "no" and entry.is_panorama is not False:
            continue
        if filters.get("whatsapp") == "yes" and entry.is_whatsapp is not True:
            continue
        if filters.get("whatsapp") == "no" and entry.is_whatsapp is not False:
            continue
        if not _matches_numeric_range(
            entry.display_width_px, filters.get("min_width"), filters.get("max_width")
        ):
            continue
        if not _matches_numeric_range(
            entry.display_height_px, filters.get("min_height"), filters.get("max_height")
        ):
            continue
        if not _matches_numeric_range(
            entry.aspect_ratio, filters.get("min_aspect"), filters.get("max_aspect")
        ):
            continue
        haystack = " ".join((entry.current_relative_path, entry.original_filename, entry.original_relative_path, entry.source_name, entry.import_batch)).casefold()
        if query and query not in haystack:
            continue
        result.append(entry)
    return result


def _filters() -> dict[str, str]:
    keys = (
        "year", "month", "type", "source", "source_type", "extension", "q",
        "min_width", "max_width", "min_height", "max_height",
        "min_aspect", "max_aspect", "panorama", "orientation", "whatsapp",
        "page_size",
    )
    values = {key: request.args.get(key, "").strip() for key in keys}
    values["panorama"] = values["panorama"].lower()
    values["whatsapp"] = values["whatsapp"].lower()
    if values["year"] and values["year"] != "no_date" and not (len(values["year"]) == 4 and values["year"].isdecimal()):
        abort(400, "Year must be four digits or no_date.")
    if values["month"] and not (len(values["month"]) == 7 and values["month"][4] == "-" and values["month"].replace("-", "").isdecimal()):
        abort(400, "Month must use YYYY-MM.")
    if values["type"] and values["type"].upper() not in {"PHOTO", "VIDEO"}:
        abort(400, "Media type must be PHOTO or VIDEO.")
    if values["panorama"] not in {"", "yes", "no"}:
        abort(400, "Panorama must be yes or no.")
    if values["whatsapp"] not in {"", "yes", "no"}:
        abort(400, "WhatsApp evidence must be yes or no.")
    if values["page_size"] and (
        not values["page_size"].isdecimal()
        or int(values["page_size"]) not in PAGE_SIZE_OPTIONS
    ):
        abort(400, "Page size must be 100, 200, or 500.")
    if values["orientation"] and values["orientation"].upper() not in {
        "LANDSCAPE", "PORTRAIT", "SQUARE", "UNKNOWN"
    }:
        abort(400, "Orientation is invalid.")
    for key in ("min_width", "max_width", "min_height", "max_height"):
        if values[key] and (not values[key].isdecimal() or int(values[key]) < 1):
            abort(400, f"{key.replace('_', ' ').title()} must be a positive integer.")
    for key in ("min_aspect", "max_aspect"):
        try:
            numeric_value = float(values[key]) if values[key] else 1.0
            if not math.isfinite(numeric_value) or numeric_value <= 0:
                raise ValueError
        except ValueError:
            abort(400, f"{key.replace('_', ' ').title()} must be a positive number.")
    for minimum, maximum in (
        ("min_width", "max_width"),
        ("min_height", "max_height"),
        ("min_aspect", "max_aspect"),
    ):
        if values[minimum] and values[maximum] and float(values[minimum]) > float(values[maximum]):
            abort(400, f"{minimum.replace('_', ' ').title()} cannot exceed {maximum.replace('_', ' ')}.")
    values["type"] = values["type"].upper()
    values["source_type"] = values["source_type"].upper()
    values["orientation"] = values["orientation"].upper()
    return {key: value for key, value in values.items() if value}


def _matches_numeric_range(
    value: int | float | None,
    minimum: str | None,
    maximum: str | None,
) -> bool:
    """Match an optional catalog number against inclusive request bounds."""
    if not minimum and not maximum:
        return True
    if value is None:
        return False
    return (not minimum or value >= float(minimum)) and (
        not maximum or value <= float(maximum)
    )


def _query_string(filters: dict[str, str]) -> str:
    from urllib.parse import urlencode
    return urlencode(filters)


def _neighbor(entries: list[BrowserMedia], media_id: str, direction: int) -> BrowserMedia | None:
    index = next(index for index, entry in enumerate(entries) if entry.media_id == media_id)
    neighbor_index = index + direction
    return entries[neighbor_index] if 0 <= neighbor_index < len(entries) else None


def _detail_sections(database: Path, library_id: str, media_id: str) -> list[dict[str, object]]:
    """Return all catalog-backed media detail as readable, read-only sections."""
    queries = (
        (
            "Media identity",
            """
            SELECT mf.*, l.name AS library_name, l.environment AS library_environment,
                   l.description AS library_description
            FROM media_file AS mf
            JOIN library AS l ON l.library_id = mf.library_id
            WHERE mf.media_id = ? AND mf.library_id = ?
            """,
            (media_id, library_id),
        ),
        (
            "Current file locations",
            """
            SELECT fl.*, s.name AS source_name, s.source_type, s.default_timezone
            FROM file_location AS fl
            JOIN source AS s ON s.source_id = fl.source_id
            WHERE fl.media_id = ? AND s.library_id = ?
            ORDER BY fl.normalized_relative_path, fl.location_id
            """,
            (media_id, library_id),
        ),
        (
            "Technical metadata",
            "SELECT * FROM media_metadata WHERE media_id = ?",
            (media_id,),
        ),
        (
            "Current capture-date resolution",
            """
            SELECT a.*, current.updated_at AS current_pointer_updated_at
            FROM media_date_resolution AS current
            JOIN date_resolution_attempt AS a ON a.resolution_id = current.resolution_id
            WHERE current.media_id = ?
            """,
            (media_id,),
        ),
        (
            "Capture-date resolution history",
            """
            SELECT * FROM date_resolution_attempt
            WHERE media_id = ? ORDER BY resolved_at DESC, resolution_id DESC
            """,
            (media_id,),
        ),
        (
            "Current content hash",
            """
            SELECT a.*, current.updated_at AS current_pointer_updated_at,
                   item.media_item_id AS logical_media_item_id
            FROM media_hash AS current
            JOIN hash_attempt AS a ON a.hash_id = current.hash_id
            LEFT JOIN media_item AS item ON item.sha256 = a.digest
            WHERE current.media_id = ?
            """,
            (media_id,),
        ),
        (
            "Hash calculation history",
            """
            SELECT * FROM hash_attempt
            WHERE media_id = ? ORDER BY finished_at DESC, hash_id DESC
            """,
            (media_id,),
        ),
        (
            "Immutable provenance observations",
            """
            SELECT o.*, s.name AS source_name, s.source_type, s.default_timezone,
                   b.name AS import_batch_name, b.description AS import_batch_description,
                   b.created_at AS import_batch_created_at
            FROM file_observation AS o
            JOIN source AS s ON s.source_id = o.source_id
            JOIN import_batch AS b ON b.import_batch_id = o.import_batch_id
            WHERE o.media_id = ? AND s.library_id = ?
            ORDER BY o.observed_at, o.observation_id
            """,
            (media_id, library_id),
        ),
        (
            "Observation location history",
            """
            SELECT h.*, o.original_relative_path, s.name AS source_name
            FROM observation_location_history AS h
            JOIN file_observation AS o ON o.observation_id = h.observation_id
            JOIN source AS s ON s.source_id = o.source_id
            WHERE o.media_id = ? AND s.library_id = ?
            ORDER BY h.recorded_at DESC, h.observation_location_id DESC
            """,
            (media_id, library_id),
        ),
        (
            "Media associations",
            """
            SELECT r.*,
                   CASE WHEN r.primary_media_id = ? THEN 'PRIMARY' ELSE 'COMPANION' END AS media_role,
                   CASE WHEN r.primary_media_id = ? THEN r.companion_media_id ELSE r.primary_media_id END AS related_media_id,
                   related.original_filename AS related_original_filename,
                   s.name AS source_name
            FROM media_relation AS r
            JOIN source AS s ON s.source_id = r.source_id
            JOIN media_file AS related ON related.media_id = CASE
                WHEN r.primary_media_id = ? THEN r.companion_media_id ELSE r.primary_media_id END
            WHERE r.library_id = ? AND (r.primary_media_id = ? OR r.companion_media_id = ?)
            ORDER BY r.active DESC, r.relation_type, r.relation_id
            """,
            (media_id, media_id, media_id, library_id, media_id, media_id),
        ),
        (
            "Metadata extraction history and raw evidence",
            """
            SELECT * FROM metadata_extraction
            WHERE media_id = ? ORDER BY extracted_at DESC, extraction_id DESC
            """,
            (media_id,),
        ),
        (
            "Manual review decisions",
            """
            SELECT * FROM manual_review_decision
            WHERE media_id = ? ORDER BY decided_at DESC, decision_id DESC
            """,
            (media_id,),
        ),
    )
    json_fields = {
        "arguments_json",
        "candidates_json",
        "reasons_json",
        "details_json",
        "raw_metadata_json",
        "decision_value_json",
    }
    sections: list[dict[str, object]] = []
    with open_readonly_database(database) as connection:
        for title, sql, parameters in queries:
            records = []
            for row in connection.execute(sql, parameters).fetchall():
                record = dict(row)
                for key in json_fields.intersection(record):
                    record[key] = _pretty_json(record[key])
                records.append(record)
            sections.append(
                {
                    "title": title,
                    "records": records,
                    "open": title in {
                        "Media identity",
                        "Current file locations",
                        "Technical metadata",
                        "Current capture-date resolution",
                        "Current content hash",
                        "Immutable provenance observations",
                    },
                }
            )
    return sections


def _pretty_json(value: object) -> object:
    """Pretty-print valid stored JSON while preserving malformed historical text."""
    if not isinstance(value, str):
        return value
    try:
        return json.dumps(json.loads(value), indent=2, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return value


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
  main { width: min(1800px, calc(100% - 32px)); margin: 0 auto; padding: 32px 0 52px; }
  h1 { margin: 7px 0; font-size: clamp(2rem, 5vw, 3.2rem); letter-spacing: -.05em; } .eyebrow { color: #9ca9ff; font-size: .78rem; font-weight: 750; letter-spacing: .12em; text-transform: uppercase; }
  .lede, .meta { color: #b9c0d3; line-height: 1.55; } .notice { margin: 22px 0; padding: 14px 16px; border-left: 3px solid #7180f4; border-radius: 6px; background: #1a1f31; color: #c7cde0; }
  .filters, .pager { display: flex; flex-wrap: wrap; align-items: center; gap: 9px; margin: 25px 0; }.button { padding: 9px 13px; border: 1px solid #46507b; border-radius: 9px; color: #dce1ff; text-decoration: none; font-weight: 650; }.button:hover, .button.active { background: #293055; border-color: #8896ff; }
  .gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 8px; }.card { display: block; min-width: 0; overflow: hidden; border: 1px solid #303653; border-radius: 8px; background: rgba(24, 28, 43, .82); color: #edf0f7; text-decoration: none; }.card:hover { border-color: #8896ff; transform: translateY(-1px); }.thumb-wrap { position: relative; aspect-ratio: 1; background: #171b2b; }.thumb { display: block; width: 100%; height: 100%; object-fit: cover; }.placeholder { display: grid; place-items: center; height: 100%; padding: 8px; color: #aeb7cb; font-size: .72rem; text-align: center; background: #171b2b; }.whatsapp-origin-icon, .whatsapp-detail-icon { position: absolute; display: grid; place-items: center; border: 1px solid rgba(255,255,255,.8); border-radius: 50%; background: #25d366; box-shadow: 0 1px 5px rgba(0,0,0,.65); }.whatsapp-origin-icon { left: 5px; bottom: 5px; width: 23px; height: 23px; }.whatsapp-origin-icon svg { width: 19px; height: 19px; }.caption { padding: 6px 7px; font-size: .7rem; line-height: 1.3; overflow-wrap: anywhere; }.caption strong { display: -webkit-box; margin-bottom: 3px; overflow: hidden; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }.detail { display: grid; gap: 25px; grid-template-columns: minmax(0, 2fr) minmax(260px, 1fr); margin-top: 28px; }.detail-preview { position: relative; min-height: 120px; }.slider-arrow { position: absolute; z-index: 2; top: 50%; display: grid; width: 46px; height: 58px; place-items: center; border: 1px solid rgba(255,255,255,.65); border-radius: 10px; background: rgba(8,10,16,.68); color: #fff; font-size: 2rem; font-weight: 750; line-height: 1; text-decoration: none; transform: translateY(-50%); backdrop-filter: blur(4px); }.slider-arrow:hover, .slider-arrow:focus-visible { background: rgba(41,48,85,.92); border-color: #fff; outline: none; }.slider-arrow.previous { left: 10px; }.slider-arrow.next { right: 10px; }.whatsapp-detail-icon { left: 10px; bottom: 10px; width: 42px; height: 42px; }.whatsapp-detail-icon svg { width: 35px; height: 35px; }.full { display: block; width: 100%; max-height: 75vh; object-fit: contain; background: #080a10; border-radius: 14px; }.panel { border: 1px solid #303653; border-radius: 14px; padding: 20px; background: rgba(24,28,43,.82); }.path { overflow-wrap: anywhere; color: #c7cde0; }
  .catalog-sections { display: grid; gap: 14px; margin-top: 25px; }.catalog-section { border: 1px solid #303653; border-radius: 14px; background: rgba(24,28,43,.82); overflow: hidden; }.catalog-section summary { cursor: pointer; padding: 17px 20px; font-size: 1.08rem; font-weight: 750; }.catalog-section[open] summary { border-bottom: 1px solid #303653; }.record { padding: 18px 20px; }.record + .record { border-top: 1px solid #303653; }.fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 13px 22px; margin: 0; }.field { min-width: 0; }.field dt { margin-bottom: 4px; color: #99a5c6; font-size: .76rem; font-weight: 750; letter-spacing: .06em; text-transform: uppercase; }.field dd { margin: 0; color: #edf0f7; line-height: 1.42; overflow-wrap: anywhere; white-space: pre-wrap; }.empty { margin: 0; padding: 18px 20px; color: #99a5c6; }.record-count { color: #99a5c6; font-size: .8rem; font-weight: 500; }
  @media (max-width: 720px) { main { width: min(100% - 28px, 1280px); padding-top: 30px; }.detail { grid-template-columns: 1fr; }.fields { grid-template-columns: 1fr; } }
</style>
"""

_GALLERY_TEMPLATE = """<!doctype html><title>{{ library_name }} browser</title>""" + _STYLE + """
<main><nav class="pager"><a class="button active" href="/">Browser</a><a class="button" href="http://127.0.0.1:8081">Database</a><a class="button" href="http://127.0.0.1:8082">Review</a></nav><div class="eyebrow">Local read-only media browser</div><h1>{{ library_name }}</h1><p class="lede">Organized-library media only. The toAnalyze directory is always excluded.</p>
<form class="filters" method="get">
  <input name="q" value="{{ filters.get('q', '') }}" placeholder="Search filename or provenance">
  <input name="year" value="{{ filters.get('year', '') }}" placeholder="Year">
  <input name="month" value="{{ filters.get('month', '') }}" placeholder="YYYY-MM">
  <select name="type"><option value="">All media types</option><option value="PHOTO"{% if filters.get('type') == 'PHOTO' %} selected{% endif %}>Photos</option><option value="VIDEO"{% if filters.get('type') == 'VIDEO' %} selected{% endif %}>Videos</option></select>
  <select name="source"><option value="">All source names</option>{% for source in sources %}<option{% if filters.get('source') == source %} selected{% endif %}>{{ source }}</option>{% endfor %}</select>
  <select name="source_type"><option value="">All source types</option>{% for source_type in source_types %}<option{% if filters.get('source_type') == source_type %} selected{% endif %}>{{ source_type }}</option>{% endfor %}</select>
  <select name="extension"><option value="">All extensions</option>{% for extension in extensions %}<option{% if filters.get('extension') == extension %} selected{% endif %}>{{ extension }}</option>{% endfor %}</select>
  <select name="orientation"><option value="">All orientations</option>{% for orientation in ('LANDSCAPE', 'PORTRAIT', 'SQUARE', 'UNKNOWN') %}<option{% if filters.get('orientation') == orientation %} selected{% endif %}>{{ orientation }}</option>{% endfor %}</select>
  <select name="panorama"><option value="">Panorama: any</option><option value="yes"{% if filters.get('panorama') == 'yes' %} selected{% endif %}>Panorama: yes</option><option value="no"{% if filters.get('panorama') == 'no' %} selected{% endif %}>Panorama: no</option></select>
  <select name="whatsapp"><option value="">WhatsApp evidence: any</option><option value="yes"{% if filters.get('whatsapp') == 'yes' %} selected{% endif %}>WhatsApp evidence: yes</option><option value="no"{% if filters.get('whatsapp') == 'no' %} selected{% endif %}>WhatsApp evidence: no</option></select>
  <input name="min_width" type="number" min="1" value="{{ filters.get('min_width', '') }}" placeholder="Min width px">
  <input name="max_width" type="number" min="1" value="{{ filters.get('max_width', '') }}" placeholder="Max width px">
  <input name="min_height" type="number" min="1" value="{{ filters.get('min_height', '') }}" placeholder="Min height px">
  <input name="max_height" type="number" min="1" value="{{ filters.get('max_height', '') }}" placeholder="Max height px">
  <input name="min_aspect" type="number" min="0.01" step="0.01" value="{{ filters.get('min_aspect', '') }}" placeholder="Min aspect ratio">
  <input name="max_aspect" type="number" min="0.01" step="0.01" value="{{ filters.get('max_aspect', '') }}" placeholder="Max aspect ratio">
  <select name="page_size" aria-label="Items per page">{% for option in page_size_options %}<option value="{{ option }}"{% if page_size == option %} selected{% endif %}>{{ option }} per page</option>{% endfor %}</select>
  <button class="button">Apply filters</button><a class="button" href="/">Clear</a>
</form>
<p class="meta">Page {{ page }}. Up to {{ page_size }} entries per page.</p><section class="gallery">{% for entry in entries %}<a class="card" href="{{ url_for('detail', media_id=entry.media_id, **filters) }}"><div class="thumb-wrap">{% if entry.status == 'PRESENT' %}<img class="thumb" loading="lazy" src="{{ url_for('thumbnail', media_id=entry.media_id) }}" alt="Thumbnail for {{ entry.current_relative_path }}">{% else %}<div class="placeholder">Cataloged file missing</div>{% endif %}{% if entry.is_whatsapp %}<span class="whatsapp-origin-icon" role="img" aria-label="WhatsApp evidence" title="WhatsApp evidence: {{ entry.whatsapp_evidence_reason }}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4.3a7.7 7.7 0 0 0-6.55 11.76L4.3 20.2l4.27-1.12A7.7 7.7 0 1 0 12 4.3Z" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><path d="M8.3 7.3c.5 4.3 4.1 7.9 8.4 8.4l1.1-2.5-2.8-1.1-1 1c-1.4-.7-2.4-1.7-3.1-3.1l1-1-1.1-2.8-2.5 1.1Z" fill="#fff" stroke="#fff" stroke-width=".35" stroke-linejoin="round"/></svg></span>{% endif %}</div><div class="caption"><strong>{{ entry.current_relative_path }}</strong>{{ entry.media_type }} · {{ entry.capture_local or 'No resolved date' }}{% if entry.is_whatsapp %} · WhatsApp evidence{% endif %}</div></a>{% endfor %}</section>{% if not entries %}<p class="notice">No media match this page and filter.</p>{% endif %}<nav class="pager">{% if page > 1 %}<a class="button" href="/?page={{ page - 1 }}&{{ filters|urlencode }}">Previous</a>{% endif %}{% if entries|length == page_size %}<a class="button" href="/?page={{ page + 1 }}&{{ filters|urlencode }}">Next</a>{% endif %}</nav></main>
"""

_DETAIL_TEMPLATE = """<!doctype html><title>{{ entry.current_relative_path }}</title>""" + _STYLE + """
<main>
  <nav class="pager"><a class="button" href="/?{{ return_query }}">Browser</a><a class="button" href="http://127.0.0.1:8081">Database</a><a class="button" href="http://127.0.0.1:8082">Review</a></nav>
  <a class="button" href="/?{{ return_query }}">Back to gallery</a>
  <div class="eyebrow" style="margin-top:24px">Cataloged media</div>
  <h1>{{ entry.current_relative_path }}</h1>
  <section class="detail">
    <div class="detail-preview">{% if available and entry.media_type == 'PHOTO' %}<img class="full" src="{{ url_for('content', media_id=entry.media_id) }}" alt="{{ entry.current_relative_path }}">{% elif available and entry.media_type == 'VIDEO' %}<video class="full" controls src="{{ url_for('content', media_id=entry.media_id) }}">Preview unavailable in browser.</video>{% else %}<div class="placeholder">The catalog entry remains visible, but its file is unavailable under the selected media root.</div>{% endif %}{% if previous %}<a id="preview-previous-link" class="slider-arrow previous" href="{{ url_for('detail', media_id=previous.media_id) }}?{{ return_query }}" aria-label="Previous media" title="Previous media">&#8249;</a>{% endif %}{% if next_item %}<a id="preview-next-link" class="slider-arrow next" href="{{ url_for('detail', media_id=next_item.media_id) }}?{{ return_query }}" aria-label="Next media" title="Next media">&#8250;</a>{% endif %}{% if entry.is_whatsapp %}<span class="whatsapp-detail-icon" role="img" aria-label="WhatsApp evidence" title="WhatsApp evidence: {{ entry.whatsapp_evidence_reason }}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4.3a7.7 7.7 0 0 0-6.55 11.76L4.3 20.2l4.27-1.12A7.7 7.7 0 1 0 12 4.3Z" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><path d="M8.3 7.3c.5 4.3 4.1 7.9 8.4 8.4l1.1-2.5-2.8-1.1-1 1c-1.4-.7-2.4-1.7-3.1-3.1l1-1-1.1-2.8-2.5 1.1Z" fill="#fff" stroke="#fff" stroke-width=".35" stroke-linejoin="round"/></svg></span>{% endif %}</div>
    <aside class="panel"><p><strong>Type</strong><br>{{ entry.media_type }}</p><p><strong>Extension and size</strong><br>{{ entry.extension }} · {{ entry.size_bytes }} bytes</p><p><strong>Capture date</strong><br>{{ entry.capture_local or 'No resolved date' }}</p><p><strong>Catalog status</strong><br>{{ entry.status }}</p><p><strong>WhatsApp evidence</strong><br>{{ 'YES' if entry.is_whatsapp else 'NO' }} · {{ entry.whatsapp_evidence_reason }}</p><p><strong>Registered source</strong><br>{{ entry.source_name }} · {{ entry.source_type }}</p><p><strong>Current relative path</strong><br><span class="path">{{ entry.current_relative_path }}</span></p><p><strong>Media ID</strong><br><span class="path">{{ entry.media_id }}</span></p></aside>
  </section>
  <section class="catalog-sections" aria-label="Complete catalog information">
    {% for section in detail_sections %}
      <details class="catalog-section"{% if section['open'] %} open{% endif %}>
        <summary>{{ section['title'] }} <span class="record-count">{{ section['records']|length }} record{% if section['records']|length != 1 %}s{% endif %}</span></summary>
        {% if section['records'] %}
          {% for record in section['records'] %}
            <article class="record"><dl class="fields">
              {% for key, value in record.items() %}<div class="field"><dt>{{ key|replace('_', ' ') }}</dt><dd>{% if value is none %}Not recorded{% elif value == '' %}Empty{% else %}{{ value }}{% endif %}</dd></div>{% endfor %}
            </dl></article>
          {% endfor %}
        {% else %}<p class="empty">No catalog record is available for this section.</p>{% endif %}
      </details>
    {% endfor %}
  </section>
  {% if duplicates|length > 1 %}<section class="panel" style="margin-top:25px"><h2>Exact duplicate observations</h2>{% for item in duplicates %}<p class="path">{{ item['source_name'] }} · {{ item['original_relative_path'] }}{% if item['current_relative_path'] != item['original_relative_path'] %}<br>Current: {{ item['current_relative_path'] }}{% endif %}</p>{% endfor %}</section>{% endif %}
  <nav class="pager">{% if previous %}<a id="previous-link" class="button" href="{{ url_for('detail', media_id=previous.media_id) }}?{{ return_query }}">Previous</a>{% endif %}{% if next_item %}<a id="next-link" class="button" href="{{ url_for('detail', media_id=next_item.media_id) }}?{{ return_query }}">Next</a>{% endif %}</nav>
</main>
<script>document.addEventListener('keydown', event => { if (event.target.matches('input,select,textarea,video')) return; if (event.key === 'Escape') location.href='/?{{ return_query }}'; if (event.key === 'ArrowLeft') document.getElementById('preview-previous-link')?.click(); if (event.key === 'ArrowRight') document.getElementById('preview-next-link')?.click(); });</script>
"""
