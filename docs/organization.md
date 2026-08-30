# Physical Organization

V1 physical organization will use year directories and `no_date` for media without an accepted date. Planning, review, and WRITE execution remain separate stages.

The available `media plan create --library LIBRARY` command creates a read-only `YEAR_OR_NO_DATE` plan. It deterministically assigns resolved dates to their four-digit year and all other date states to `no_date`, records each destination collision, and produces a content checksum. It does not copy, move, rename, or modify media.

An active, detected Live Photo, RAW/JPEG, or sidecar relation is planned as one group. The primary media item's resolved year determines the destination directory for every member, while each member retains its own filename. Active ambiguous association records block affected plan items for review.

Destination collisions are recorded as CONFLICT plan items. Ambiguous active associations are recorded as BLOCKED plan items. Review plan items with the plan list command, or produce a new external CSV or JSON review file with the plan export command. Exports refuse paths inside cataloged media roots and refuse to overwrite an existing file.

Organization plan content, items, and checksums are immutable at the SQLite layer. A later controlled WRITE workflow may advance a plan status, but cannot alter the reviewed set of destinations.

The controlled COPY command requires the exact plan ID as its confirmation value, explicit source and destination roots, a conflict-free DRAFT plan, complete provenance, and exact hashes. It verifies source and copied bytes with SHA-256 and records append-only operation events. COPY never overwrites an existing destination and does not remove source media.

MOVE applies the same preconditions. It copies and verifies the destination first, checks the source hash again, then removes the source and records the removal in the journal.

Organization changes current physical locations but never changes historical provenance. A plan must carry the observation identity and immutable original relative path. Associated Live Photos, RAW and JPEG pairs, and sidecars must be planned together. Destination names must preserve the original filename component.

Active `LIVE_PHOTO_PAIR`, `RAW_JPEG_PAIR`, and `SIDECAR_ASSOCIATION` records form indivisible planning groups. A conflict must be reviewed before planning. Inactive relations remain historical evidence but do not automatically join a new operation plan.

No production organization operation may run until exact hashes, provenance records, a catalog backup, a provenance export, an immutable plan, explicit WRITE confirmation, journaling, and post-copy verification are available.
