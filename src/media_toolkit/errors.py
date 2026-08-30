"""Application-specific exceptions."""


class MediaToolkitError(Exception):
    """Base exception for expected application failures."""


class ConfigurationError(MediaToolkitError):
    """Raised when configuration is invalid or incomplete."""


class DatabaseSafetyError(MediaToolkitError):
    """Raised when a database operation violates a safety rule."""
