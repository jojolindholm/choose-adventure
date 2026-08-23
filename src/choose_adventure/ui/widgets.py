import time

from textual.widgets import Static

from choose_adventure.story.models import CharacterState


class GeneratingIndicator(Static):
    """Animated "generating…" indicator with an elapsed-seconds counter.

    Shows a slowly cycling animation plus a live elapsed-time readout so a
    slow LLM call never looks like the app has frozen. Start it when a
    generation begins and stop it (or let unmount clean up) when it finishes.
    """

    DEFAULT_CSS = """
    GeneratingIndicator {
        height: 1;
        color: $accent;
    }
    """

    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, base_text: str = "Generating story", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._base_text = base_text
        self._started_at: float | None = None
        self._frame_index = 0
        self._timer = None

    def on_mount(self) -> None:
        self.start()

    def start(self) -> None:
        """Begin the animation and elapsed-time ticker."""
        self._started_at = time.monotonic()
        self._frame_index = 0
        if self._timer is None:
            self._timer = self.set_interval(0.25, self._tick)
        self._tick()

    def stop(self) -> None:
        """Stop the ticker (keeps current text)."""
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    def _tick(self) -> None:
        frame = self.FRAMES[self._frame_index % len(self.FRAMES)]
        self._frame_index += 1
        elapsed = 0
        if self._started_at is not None:
            elapsed = int(time.monotonic() - self._started_at)
        self.update(f"{frame} {self._base_text}… {elapsed}s")

    def on_unmount(self) -> None:
        self.stop()


class CharacterPanel(Static):
    """Fixed character-info panel."""

    DEFAULT_CSS = """
    CharacterPanel {
        width: 30;
        height: 1fr;
        border: solid $primary;
        padding: 1;
    }
    """

    def set_state(self, state: CharacterState | None) -> None:
        """Render the character state."""
        if state is None:
            self.update("CHARACTER\n(no character yet)")
            return

        name = state.name or "-"
        role = state.role or "-"
        location = state.location or "-"
        condition = state.condition or "-"
        traits = ", ".join(state.traits) if state.traits else "-"
        inventory = ", ".join(state.inventory) if state.inventory else "-"

        self.update(
            f"CHARACTER\n"
            f"Name:      {name}\n"
            f"Role:      {role}\n"
            f"Location:  {location}\n"
            f"Condition: {condition}\n"
            f"Traits:    {traits}\n"
            f"Inventory: {inventory}"
        )
