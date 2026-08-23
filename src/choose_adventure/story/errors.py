

class StoryError(Exception):
    """Base exception for story errors."""


class StoryEndedError(StoryError):
    """Raised when trying to choose from an ending page."""
