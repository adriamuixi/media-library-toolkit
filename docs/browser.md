# Local Media Browser

## Purpose

Local Media Browser is a read-only visual interface for an organized media library. It combines physical files with the existing SQLite catalog without creating a parallel catalog or re-extracting metadata during page loads.

It represents the definitive organized library:

```text
1998/
1999/
...
2026/
no_date/
```

`toAnalyze/` is an ingestion and review queue and is excluded unconditionally from browser results, statistics, thumbnails, detail views, search, and content serving. Exclusion compares the normalized, case-folded first path component for exact equality with `toAnalyze`; it does not rely on a fragile substring check.

## Dependencies and Architecture

The browser uses the optional browser installation extra so the core CLI remains dependency-light. Install it with the documented browser extra. The stack is:

```text
Flask
server-rendered HTML
CSS
vanilla JavaScript
read-only SQLite
external thumbnail cache
```

Flask is preferred to FastAPI because this is a local HTML application with a small internal JSON API, not a public API platform. It avoids an ASGI server and typed validation stack while providing mature routing, templates, safe response handling, and conditional file delivery. React, Node, npm, and a separate frontend build are out of scope.

The conceptual command is:

```bash
media browse \
  --library "Personal Media" \
  --root "/Volumes/MEDIA_LIBRARY" \
  --port 8080
```

It binds to `127.0.0.1` and prints `http://127.0.0.1:8080`. Browser V1 will not provide a remote-bind option. Any later network exposure requires a separate security decision, explicit warning, and authentication analysis.

## Data Model Boundary

SQLite remains the source of truth for identity, current and original paths, effective dates, metadata, source, import batch, exact duplicates, relations, and processing state. The filesystem supplies only current media bytes and existence checks.

Implementation waits until current organized paths and immutable provenance exist. Browser queries must never infer catalog history by walking the organized directories. Missing physical files remain visible from SQLite with a `FILE MISSING` state.

The browser relies on the existing catalog indexes for media type, current paths, dates, hashes, and provenance. Additional indexes require representative query-plan measurements rather than speculative bulk creation.

## Gallery

The primary page is a thumbnail-focused responsive grid. Each tile shows a thumbnail, photo or video type, effective date, and current filename. Video duration, resolution, and source may be shown when they remain visually secondary.

V1 filters are:

- year, including `No Date`;
- month based on effective date, independent of physical directories;
- photos or videos;
- source;
- source provenance type, such as `WHATSAPP`, `CAMERA`, or `OLD_DISK`;
- extension.
- inclusive minimum and maximum display width in pixels;
- inclusive minimum and maximum display height in pixels;
- inclusive minimum and maximum aspect ratio;
- panorama state;
- conservative WhatsApp evidence derived from cataloged filenames, paths, and source-folder context;
- orientation class (`LANDSCAPE`, `PORTRAIT`, `SQUARE`, or `UNKNOWN`).

Numeric and derived filters use normalized catalog metadata and exclude records where the requested field has not been extracted. Source name and source provenance type remain separate filters; folder names do not implicitly rewrite registered provenance.

WhatsApp evidence is also separate from registered provenance. It recognizes anchored WhatsApp filename forms such as `IMG-YYYYMMDD-WA####` and exact known path components such as `WhatsApp Images` or `WhatsApp Video`. The result and its reason are visible on the media detail page. A negative result means that no supported evidence was found; it does not prove that WhatsApp was never involved.

Gallery thumbnails with positive WhatsApp evidence display a small green chat-and-phone badge in the lower-left corner. The badge has an accessible label and tooltip containing the evidence reason; it is rendered by the local page without external assets.

The individual media detail preview repeats the badge at a larger size in its lower-left corner so the origin evidence remains immediately visible outside the gallery.

Text search covers current filename, original filename, original relative path, raw and normalized source context, source name, and import batch. Optional simple filters such as GPS availability, duplicate state, and RAW state are added only when supported cheaply by the final indexed schema.

Default ordering is effective capture date ascending with deterministic media-ID tie-breaking. Other options are descending capture date, filename, file size, and import date. Date-only precision must not be presented as a genuine midnight capture time.

The implementation uses deterministic pages with a user-selectable size of 100, 200, or 500 entries and defaults to 100. The compact gallery uses 120-pixel minimum columns, small gaps, and 256-pixel cached thumbnails so substantially more media fit on screen without serving full originals. The selected page size is retained with filters and detail navigation. Its filter shape has a 100,000-entry regression test; cursor pagination can replace deep offsets later only if representative measurements justify it.

## Detail View

The detail page has a large preview, a compact summary, and structured catalog sections. Current records are expanded by default; potentially large immutable histories remain available in collapsible sections. It shows every stored field from:

- current and original filenames and relative paths;
- extension, size, and SHA-256;
- effective date, source, confidence, precision, and original candidate dates;
- photo geometry and camera settings;
- video duration, codecs, frame rate, bitrate, and dynamic range;
- source, source context, and import batch;
- exact duplicate observations and historical paths;
- active Live Photo, RAW/JPEG, and sidecar relations;
- useful catalog processing state.
- media identity and every current file-location record;
- current and historical date resolutions, including candidate and reason JSON;
- current and historical hash attempts;
- all normalized technical metadata fields;
- immutable provenance and location-transition history;
- active and inactive media associations;
- metadata extraction history, including raw extractor JSON and errors;
- immutable manual review decisions.

Previous and next links retain the active filter, search, and sort state. Left and right arrow keys navigate when focus is not inside an input; Escape returns to the gallery.

The preview also places large previous and next slider controls at its left and right edges. These controls and the keyboard arrow shortcuts share the same filtered navigation targets. A control is omitted when no media exists in that direction.

Photos use a larger cached preview with fit-to-screen behavior and optional basic zoom. Videos use native `<video controls>` only when the browser can play the original codec. Unsupported content displays `Preview unavailable in browser`; Browser V1 does not automatically transcode the library.

## Thumbnail Cache

Gallery pages never serve full-size originals as thumbnails. Thumbnails and larger previews are generated lazily, with bounded concurrency, and stored under the configured external cache directory.

The stable key uses SHA-256 when available. Before hashes exist, a temporary key may combine media ID, cataloged size, modification time, thumbnail profile, and renderer version. A rename does not invalidate a hash-keyed thumbnail. Cache entries are reconstructible and contain no authoritative history.

Photo rendering uses a small adapter chain selected during implementation, with explicit support reporting for common images, HEIC, and RAW embedded previews. Video rendering invokes ffmpeg for one bounded representative frame near ten percent or a small minimum offset. It does not decode an entire video. Black-frame avoidance is optional and bounded; it must never turn one thumbnail into an unbounded analysis job.

Thumbnail generation failure creates a cached failure state or placeholder and does not block other media. The cache must never be located under the organized root.

## Internal Routes

The internal interface is intentionally small:

```text
GET /api/media
GET /api/media/{media_id}
GET /api/media/{media_id}/thumbnail
GET /api/media/{media_id}/content
GET /api/filters
GET /api/stats
```

HTML routes may wrap these queries directly in Browser V0. This is not a versioned public API. No arbitrary SQL, arbitrary path, directory listing, upload, or mutation endpoint is allowed.

Content responses support conditional and range requests for efficient video seeking. Originals are requested only from a detail view or explicit playback action.

## File-Serving Safety

The client supplies only `media_id`. The backend resolves the current relative path from SQLite, combines it with the explicit organized root, and validates all of the following before serving bytes:

1. The catalog record belongs to the selected library.
2. Its current path is not in `toAnalyze`.
3. No path component is a symbolic link.
4. The canonical result remains inside the canonical organized root.
5. The target is a regular file and matches relevant catalog preconditions.

Traversal strings, absolute catalog paths, missing files, changed files, and unsupported objects receive non-revealing error responses. Security headers include a restrictive Content Security Policy, `X-Content-Type-Options: nosniff`, and no cross-origin access. Templates escape catalog text by default.

SQLite is opened with `mode=ro` for browser requests. The server binds only to loopback, does not launch with debug mode, and does not expose personal paths in unexpected error pages.

## Missing and Corrupt Files

A missing original remains in gallery and detail queries using catalog metadata, with thumbnail and content endpoints returning a clear missing state. Corrupt or unsupported files show `Preview unavailable`. Neither condition aborts the page or hides historical provenance.

## Iterative Delivery

### Browser V0

- loopback-only Flask server and SQLite mode=ro query layer;
- paginated photo gallery and year or no-date filter;
- unconditional Unicode-safe toAnalyze exclusion;
- lazy photo thumbnails outside media roots;
- basic media detail view with missing-file state;
- media-ID-only content serving with root and symbolic-link validation.

### Browser V1

- video thumbnails through an optional local ffmpeg installation and compatible native playback;
- month, source, media-type, and extension filters;
- provenance search;
- technical and immutable historical detail;
- complete per-media catalog records and raw extraction evidence;
- stable sorting and filtered previous/next navigation.

### Browser V1.1

- exact duplicate observation expansion;
- dedicated `no_date` filter;
- keyboard navigation;
- responsive dark theme;
- a 100,000-entry filter-shape regression test.

## Limitations

Browser V1 does not delete, move, rename, upload, transcode, edit metadata, edit catalog decisions, or expose remote access. Future annotations must use audited SQLite decision services from Local Review and must not weaken the browser's read-only routes.
