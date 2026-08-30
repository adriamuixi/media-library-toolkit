# Media Associations

## Purpose

Some physical files form one logical capture or editing unit and must remain together during future rename and organization operations. Association detection reads only SQLite and never changes media.

## Live Photos

A Live Photo normally contains a still image and a short MOV file. Exact matching embedded content identifiers produce `HIGH` confidence even when filenames differ. When identifiers are absent, a same-directory compatible basename produces:

- `MEDIUM` confidence for HEIC or HEIF plus MOV;
- `LOW` confidence for JPEG plus MOV.

Multiple photos or videos for one identifier or basename produce `CONFLICT` records instead of a silent choice.

## RAW and JPEG

A same-directory RAW and JPEG basename produces a `HIGH` confidence `RAW_JPEG_PAIR`. Both files are retained. They are complementary representations and must not be classified as exact duplicates merely because they depict the same capture.

## Sidecars

Sidecars remain independent cataloged files:

- XMP, DOP, and PP3 prefer a matching RAW file and otherwise match a photo;
- AAE matches a non-RAW photo;
- THM matches a video;
- other recognized sidecars use a conservative photo or video basename match.

Ambiguous targets produce `CONFLICT`. Detection does not create, modify, merge, or embed sidecar data.

## History

Every relation is scoped to its observed source. Repeating detection updates matching rows without duplication. Relations no longer present become inactive rather than being deleted. Future operation planning uses active, non-conflicting relations and retains inactive rows for audit.
