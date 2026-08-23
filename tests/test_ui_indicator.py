import pytest

from choose_adventure.ui.widgets import GeneratingIndicator


@pytest.fixture
def indicator() -> GeneratingIndicator:
    return GeneratingIndicator("Generating page")


@pytest.mark.asyncio
async def test_indicator_ticks_with_elapsed(indicator: GeneratingIndicator):
    """After a short interval the indicator shows the base text and grows elapsed time."""
    from textual.app import App
    from textual.containers import Vertical

    class HostApp(App):
        def compose(self):
            with Vertical():
                yield indicator

    async with HostApp().run_test() as pilot:
        await pilot.pause(0.6)
        text = str(indicator.render())
        assert "Generating page" in text
        assert "s" in text


@pytest.mark.asyncio
async def test_indicator_stop_halts_updates(indicator: GeneratingIndicator):
    """Calling stop() freezes the elapsed counter."""
    from textual.app import App
    from textual.containers import Vertical

    class HostApp(App):
        def compose(self):
            with Vertical():
                yield indicator

    async with HostApp().run_test() as pilot:
        await pilot.pause(0.3)
        first = str(indicator.render())
        indicator.stop()
        await pilot.pause(0.6)
        second = str(indicator.render())
        first_elapsed = first.rsplit(" ", 1)[-1]
        second_elapsed = second.rsplit(" ", 1)[-1]
        assert first_elapsed == second_elapsed
