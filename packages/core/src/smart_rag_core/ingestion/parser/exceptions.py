"""Parser sandbox and adapter exceptions."""

from __future__ import annotations


class ParserError(Exception):
    """Base parser failure with safe detail text."""

    def __init__(self, code: str, detail: str) -> None:
        """Initialize with stable machine code and operator-safe detail."""

        super().__init__(detail)
        self.code = code
        self.detail = detail


class ParserLimitExceeded(ParserError):
    """Raised when a bounded resource limit is exceeded."""

    def __init__(self, limit: str, detail: str) -> None:
        """Record which limit tripped."""

        super().__init__(f"limit_exceeded:{limit}", detail)


class ParserUnsupportedFormat(ParserError):
    """Raised when format is unknown or explicitly unsupported."""

    def __init__(self, detail: str) -> None:
        """Initialize unsupported-format error."""

        super().__init__("unsupported_format", detail)


class ParserSandboxError(ParserError):
    """Raised when sandbox launch or isolation fails."""

    def __init__(self, detail: str) -> None:
        """Initialize sandbox error."""

        super().__init__("sandbox_error", detail)


class ParserEncryptedError(ParserError):
    """Raised when encrypted/password-protected content cannot be parsed."""

    def __init__(self, detail: str) -> None:
        """Initialize encrypted-content error."""

        super().__init__("encrypted", detail)
