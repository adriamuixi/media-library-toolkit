"""Conservative catalog-only origin evidence for browser filtering."""

from __future__ import annotations

from dataclasses import dataclass
import re
from unicodedata import normalize


_WHATSAPP_FILENAME_PATTERNS = (
    re.compile(
        r"^(?:IMG|VID|AUD|PTT|DOC|STK)-\d{8}-WA\d+"
        r"(?:-\d+| \(\d+\))?(?:\.[^.]+)?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^WhatsApp (?:Image|Video|Audio|Ptt|Document) \d{4}-\d{2}-\d{2} at "
        r"\d{1,2}\.\d{2}\.\d{2}(?: \(\d+\))?(?:\.[^.]+)?$",
        re.IGNORECASE,
    ),
)

_WHATSAPP_PATH_COMPONENTS = frozenset(
    {
        "whatsapp",
        "whatsapp animated gifs",
        "whatsapp audio",
        "whatsapp documents",
        "whatsapp images",
        "whatsapp stickers",
        "whatsapp video",
        "whatsapp voice notes",
    }
)


@dataclass(frozen=True)
class WhatsAppEvidence:
    """A deterministic WhatsApp classification and its explainable reason."""

    is_whatsapp: bool
    reason: str


def classify_whatsapp_evidence(*catalog_values: str | None) -> WhatsAppEvidence:
    """Classify immutable filenames and paths without reading or changing media."""
    normalized_values = tuple(
        normalize("NFC", value).replace("\\", "/")
        for value in catalog_values
        if value
    )
    for value in normalized_values:
        filename = value.rsplit("/", 1)[-1]
        if any(pattern.fullmatch(filename) for pattern in _WHATSAPP_FILENAME_PATTERNS):
            return WhatsAppEvidence(True, "FILENAME_PATTERN")
    for value in normalized_values:
        components = {component.casefold() for component in value.split("/") if component}
        if components.intersection(_WHATSAPP_PATH_COMPONENTS):
            return WhatsAppEvidence(True, "PATH_COMPONENT")
    return WhatsAppEvidence(False, "NO_WHATSAPP_EVIDENCE")
