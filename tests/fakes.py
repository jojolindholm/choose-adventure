import asyncio

from choose_adventure.story.models import GeneratedPage, GenerationContext


class FakeGenerator:
    """Scripted fake generator for testing.

    Args:
        script: List of GeneratedPage or Exception to raise in order.
        delay: Optional delay (seconds) between calls for timing tests.
    """

    def __init__(self, script: list[GeneratedPage | Exception], delay: float = 0.0):
        self._script = list(script)
        self._delay = delay
        self.calls: list[GenerationContext] = []

    async def next_page(self, ctx: GenerationContext) -> GeneratedPage:
        """Execute the next entry in the script."""
        self.calls.append(ctx)
        if self._delay > 0:
            await asyncio.sleep(self._delay)

        entry = self._script.pop(0)
        if isinstance(entry, Exception):
            raise entry
        return entry
