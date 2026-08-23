from textual.widgets import Static

from choose_adventure.story.models import CharacterState


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
