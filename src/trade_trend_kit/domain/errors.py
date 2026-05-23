"""Project-specific exceptions shared by application services and adapters."""


class TradeTrendKitError(Exception):
    """Base class for all project-specific errors."""


class ConfigError(TradeTrendKitError):
    """Raised when runtime or account configuration is invalid."""


class XClientError(TradeTrendKitError):
    """Raised when fetching data from X fails in a recoverable way."""


class AuthenticationError(XClientError):
    """Raised when X authentication or cookie reuse fails."""


class RateLimitError(XClientError):
    """Raised when X rejects requests because of rate limits."""


class StorageError(TradeTrendKitError):
    """Raised when local persistence cannot read or write project data."""


class AnalysisError(TradeTrendKitError):
    """Raised when tweet analysis fails or returns unusable output."""
