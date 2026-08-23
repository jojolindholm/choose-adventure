class LLMError(Exception):
    """Base exception for LLM errors."""

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


class LLMTransportError(LLMError):
    """Network/transport failure (connection error, 5xx, etc.)."""


class LLMOutputError(LLMError):
    """Model returned invalid/unparseable output."""
