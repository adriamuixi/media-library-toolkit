# Local Review

Local Review is a catalog interface for human review decisions. Start it with the media review command and a library name.

It binds only to the loopback address and displays the local URL. The initial pages provide paginated exact duplicate groups and the conflict, no-date, and suspicious date states. The interface does not serve, move, rename, delete, or alter media files.

Pass an explicit media root to enable photo previews. Preview requests use catalog media IDs, reject symbolic-link traversal and paths outside that root, and generate bounded JPEG files only in the configured external cache directory. Previews are regenerable and never stored in the media library.

Manual decisions are catalog-only audit events. A date correction requires a reviewer identity and reason, appends an immutable decision row, and creates a new current date-resolution attempt without changing original evidence.
