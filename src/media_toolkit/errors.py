"""Application-specific exceptions."""


class MediaToolkitError(Exception):
    """Base exception for expected application failures."""


class ConfigurationError(MediaToolkitError):
    """Raised when configuration is invalid or incomplete."""


class DatabaseSafetyError(MediaToolkitError):
    """Raised when a database operation violates a safety rule."""


class CatalogError(MediaToolkitError):
    """Raised when a catalog record cannot be created or resolved safely."""


class ExternalToolError(MediaToolkitError):
    """Raised when a required metadata tool cannot produce a valid result."""
