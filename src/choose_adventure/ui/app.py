from __future__ import annotations

import pathlib
from typing import Any, ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import Footer, Header, Input, Static

from choose_adventure.config import CyaConfig
from choose_adventure.llm.errors import LLMError
from choose_adventure.storage.repo import StoryRepository, StorySummary
from choose_adventure.story.engine import StoryEngine
from choose_adventure.story.errors import StoryEndedError
from choose_adventure.ui.widgets import CharacterPanel, GeneratingIndicator


class ConfirmDialog(ModalScreen):
    """Simple confirmation dialog."""

    DEFAULT_CSS = """
    ConfirmDialog {
        layout: vertical;
        align: center middle;
        background: $background 70%;
    }

    ConfirmDialog > Container {
        width: 42;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1;
        layout: vertical;
    }

    ConfirmDialog > Container > #confirm-message {
        text-align: center;
        height: 1;
    }

    ConfirmDialog > Container > #confirm-buttons {
        height: 1;
        content-align: center middle;
    }
    """

    def __init__(self, message: str, title: str = "Confirm"):
        super().__init__()
        self._message = message
        self._title = title

    def compose(self) -> ComposeResult:
        with Container():
            yield Static(f"[bold]{self._title}[/bold]", id="confirm-message")
            yield Static(self._message, id="confirm-text")
            yield Static("  [b]\\[Y][/b]es   [b]\\[N][/b]o  ", id="confirm-buttons")

    def on_key(self, event) -> None:
        if event.key == "y":
            self.dismiss(True)
        elif event.key in ("n", "escape"):
            self.dismiss(False)


class MenuScreen(Screen):
    """Main menu screen."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("1", "new_story", "New story"),
        Binding("2", "continue_story", "Continue"),
        Binding("3", "replay_stories", "Replay..."),
        Binding("4", "quit_app", "Quit"),
        Binding("q", "quit_app", "Quit"),
    ]

    app: AdventureApp

    def __init__(self, repo: StoryRepository):
        super().__init__()
        self._repo = repo

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(Static("CHOOSE YOUR ADVENTURE", id="title"), id="menu-container")
        yield Footer()

    def on_mount(self) -> None:
        """Build menu rows dynamically."""
        container = self.query_one("#menu-container", Container)
        container.remove_children()

        rows: list[Static] = [Static("1) New story", id="row-new")]
        latest = self._repo.latest_story()
        if latest:
            rows.append(
                Static(
                    f'2) Continue "{latest.get("premise", "Story")}" (page {latest["last_page_id"] or "?"})',
                    id="row-continue",
                )
            )
        rows.append(Static("3) Replay a saved story...", id="row-replay"))
        rows.append(Static("4) Quit", id="row-quit"))

        for row in rows:
            container.mount(row)

    def action_new_story(self) -> None:
        self.app.push_screen(NewStoryScreen())

    def action_continue_story(self) -> None:
        latest = self._repo.latest_story()
        if latest and latest.get("last_page_id"):
            self.app.push_screen(StoryScreen(latest["id"], latest["last_page_id"]))
        else:
            self.app.notify("No story to continue.")

    def action_replay_stories(self) -> None:
        stories = self._repo.list_stories()
        if not stories:
            self.app.notify("No saved stories to replay.")
            return
        self.app.push_screen(ReplayListScreen(stories))

    def action_quit_app(self) -> None:
        self.app.exit()


class NewStoryScreen(Screen):
    """New story creation screen."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "menu", "Menu"),
        Binding("enter", "submit", "Submit"),
    ]

    app: AdventureApp

    def __init__(self):
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Static("NEW STORY", id="title"),
            Static("Story premise (one line):", id="premise-label"),
            Input(placeholder="Type your premise here (press Enter to begin)", id="premise"),
            Static("Tone (optional, e.g. eerie, comedic):", id="tone-label"),
            Input(placeholder="Tone (optional)", id="tone"),
            Static("", id="hint"),
            id="new-story-container",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#premise", Input).focus()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Enter pressed in an Input → submit the form."""
        self.action_submit()

    def action_submit(self) -> None:
        """Read both inputs and start a new story (or show a hint)."""
        premise = self.query_one("#premise", Input).value.strip()
        tone = self.query_one("#tone", Input).value.strip()
        if not premise:
            self.query_one("#hint", Static).update("Give the story a premise first.")
            return
        self.query_one("#hint", Static).update("")
        self.query_one("#new-story-container", Container).mount(
            GeneratingIndicator("Generating story")
        )
        self.app.start_new_story(premise, tone)

    def action_menu(self) -> None:
        self.app.pop_screen()


class StoryScreen(Screen):
    """Story playing screen with character pane, ending state, error+retry."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "menu", "Menu"),
        Binding("m", "menu", "Menu"),
        Binding("n", "new_story_mid_game", "New story"),
        Binding("r", "replay", "Replay"),
        Binding("q", "quit", "Quit"),
        Binding("a", "retry", "Retry"),
        # Option choice keys (1-4) are shown in the on-screen options dock, so keep
        # them out of the footer to avoid redundant "1 → 1, 2 → 2" noise.
        Binding("1", "choose_1", "1", show=False),
        Binding("2", "choose_2", "2", show=False),
        Binding("3", "choose_3", "3", show=False),
        Binding("4", "choose_4", "4", show=False),
    ]

    app: AdventureApp

    def __init__(self, story_id: int, page_id: int):
        super().__init__()
        self._story_id = story_id
        self._page_id = page_id
        self._page: dict | None = None
        self._options: list[dict] = []
        self._busy = False
        self._pending: tuple[dict, dict] | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        # Full-width topbar row
        yield Container(Static("", id="topbar"), id="topbar-row")
        # Side-by-side columns: story (left, scrollable) + character panel (right, fixed width)
        yield Container(
            VerticalScroll(Static("", id="story-pane"), id="story-scroll"),
            CharacterPanel(id="character-pane"),
            id="story-area",
        )
        options_dock = Container(id="options-dock")
        yield Container(options_dock)
        yield Footer()

    def on_mount(self) -> None:
        self._load_page()

    def _load_page(self) -> None:
        """Load the current page from the repository."""
        self._page = self.app.repo.get_page(self._page_id)
        if not self._page:
            self.notify(f"Page {self._page_id} not found")
            return

        # Update topbar
        self.query_one("#topbar", Static).update(
            f"{self._page['title']} — Page {self._page['seq']}"
        )

        # Update story pane with body
        body_text = f"{self._page['title']}\n\n{self._page['body']}"
        if self._page["is_ending"]:
            body_text += "\n\n— The End —"
        self.query_one("#story-pane", Static).update(body_text)

        # Update character panel
        char = self.app.repo.get_character(self._page["id"])
        self.query_one("#character-pane", CharacterPanel).set_state(char)

        # Load options
        self._options = self.app.repo.get_options(self._page["id"])

        # Update options dock
        dock = self.query_one("#options-dock", Container)
        dock.remove_children()

        if self._page["is_ending"]:
            dock.mount(Static("1) Replay this story  2) New story  3) Menu", id="ending-actions"))
        else:
            for i, opt in enumerate(self._options, 1):
                dock.mount(Static(f"[{i}] {opt['label']}", id=f"opt-{i}"))

        self._pending = None

    def action_menu(self) -> None:
        if self._busy:
            return
        self.app.push_screen(
            ConfirmDialog("Back to the menu?", "Menu?"), callback=self._on_menu_confirm
        )

    def _on_menu_confirm(self, result: Any) -> None:
        if result is True:
            self.app.pop_screen()

    def action_new_story_mid_game(self) -> None:
        if self._busy:
            return
        self.app.push_screen(
            ConfirmDialog("Start a new story? The current one stays saved.", "New story?"),
            callback=self._on_new_story_confirm,
        )

    def _on_new_story_confirm(self, result: Any) -> None:
        if result is True:
            self.app.push_screen(NewStoryScreen())

    def action_quit(self) -> None:
        if self._busy:
            return
        self.app.push_screen(
            ConfirmDialog("Quit the game?", "Quit?"), callback=self._on_quit_confirm
        )

    def _on_quit_confirm(self, result: Any) -> None:
        if result is True:
            self.app.exit()

    def action_replay(self) -> None:
        if self._busy:
            return
        self.app.push_screen(
            ConfirmDialog("Replay this story from the beginning?", "Replay?"),
            callback=self._on_replay_confirm,
        )

    def _on_replay_confirm(self, result: Any) -> None:
        if result is True:
            self._replay_story()

    def _replay_story(self) -> None:
        first_page_id = self.app.repo.first_page_id(self._story_id)
        if first_page_id is None:
            self.notify("This story has no pages to replay.")
            return
        self.app.push_screen(StoryScreen(self._story_id, first_page_id))

    def action_retry(self) -> None:
        """Re-run the pending failed choice."""
        if self._busy or self._pending is None:
            return
        _page, option = self._pending
        self._pending = None
        self._run_choose(option)

    def action_choose_1(self) -> None:
        self._handle_choice(1)

    def action_choose_2(self) -> None:
        self._handle_choice(2)

    def action_choose_3(self) -> None:
        self._handle_choice(3)

    def action_choose_4(self) -> None:
        self._handle_choice(4)

    def _handle_choice(self, n: int) -> None:
        """Dispatch a numeric key: option choice or ending action."""
        if self._busy:
            return
        if self._page and self._page["is_ending"]:
            if n == 1:
                self._replay_story()
            elif n == 2:
                self.action_new_story_mid_game()
            elif n == 3:
                self.action_menu()
            return
        self._choose(n)

    def _choose(self, option_index: int) -> None:
        """Choose an option by index (1-based)."""
        if self._busy or not self._options:
            return

        if option_index < 1 or option_index > len(self._options):
            self.notify(f"Invalid choice. Enter 1-{len(self._options)}.")
            return

        option = self._options[option_index - 1]
        self._run_choose(option)

    def _run_choose(self, option: dict) -> None:
        """Run the choose worker for a given option dict."""
        if self._busy:
            return
        self._busy = True

        dock = self.query_one("#options-dock", Container)
        dock.remove_children()
        dock.mount(GeneratingIndicator("Generating page"))

        async def _do_choose() -> None:
            try:
                assert self._page is not None, "No page loaded"
                new_page = await self.app.engine.choose(self._story_id, self._page, option)
                self._page = new_page
                self._page_id = new_page["id"]
                self._load_page()
            except LLMError as e:
                assert self._page is not None, "No page loaded"
                self._pending = (self._page, option)
                dock = self.query_one("#options-dock", Container)
                dock.remove_children()
                dock.mount(
                    Static(
                        f"The tale faltered: {e.detail} — [a] retry, [m] menu, [q] quit",
                        id="error-text",
                    )
                )
            except StoryEndedError:
                self.notify("The story has ended.")
            finally:
                self._busy = False

        self.app.run_worker(_do_choose(), exclusive=True)


class ReplayListScreen(Screen):
    """List of saved stories to replay."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "menu", "Menu"),
        Binding("1", "replay_1", "1"),
        Binding("2", "replay_2", "2"),
        Binding("3", "replay_3", "3"),
        Binding("4", "replay_4", "4"),
        Binding("5", "replay_5", "5"),
        Binding("6", "replay_6", "6"),
        Binding("7", "replay_7", "7"),
        Binding("8", "replay_8", "8"),
        Binding("9", "replay_9", "9"),
    ]

    app: AdventureApp

    def __init__(self, stories: list[StorySummary]):
        super().__init__()
        self._stories = stories

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="replay-container"):
            for i, story in enumerate(self._stories, 1):
                yield Static(f'{i}. {story.title} — "{story.premise}"', id=f"replay-{i}")
        yield Footer()

    def action_replay_1(self) -> None:
        self._pick(1)

    def action_replay_2(self) -> None:
        self._pick(2)

    def action_replay_3(self) -> None:
        self._pick(3)

    def action_replay_4(self) -> None:
        self._pick(4)

    def action_replay_5(self) -> None:
        self._pick(5)

    def action_replay_6(self) -> None:
        self._pick(6)

    def action_replay_7(self) -> None:
        self._pick(7)

    def action_replay_8(self) -> None:
        self._pick(8)

    def action_replay_9(self) -> None:
        self._pick(9)

    def _pick(self, n: int) -> None:
        if n < 1 or n > len(self._stories):
            self.notify(f"Invalid choice. Enter 1-{len(self._stories)}.")
            return
        story = self._stories[n - 1]
        first_page_id = self.app.repo.first_page_id(story.id)
        if first_page_id is None:
            self.notify("This story has no pages to replay.")
            return
        self.app.push_screen(StoryScreen(story.id, first_page_id))

    def action_menu(self) -> None:
        self.app.pop_screen()


class AdventureApp(App):
    """Main application."""

    CSS = """
    Screen {
        layout: vertical;
    }

    #title, #replay-container > Static {
        text-align: center;
        height: 1;
    }

    #menu-container {
        layout: vertical;
        align-horizontal: center;
    }

    #menu-container > Static {
        width: 40;
        text-align: center;
    }

    #topbar-row {
        height: 1;
    }

    #topbar-row > Static {
        text-align: center;
    }

    #story-area {
        height: 1fr;
        layout: horizontal;
    }

    #story-scroll {
        width: 1fr;
        height: 1fr;
    }

    #story-pane {
        min-height: 1fr;
    }

    #character-pane {
        width: 30;
        height: 1fr;
    }

    #options-dock {
        dock: bottom;
        height: auto;
        border-top: solid $primary;
    }

    #options-dock > Static {
        text-align: center;
    }

    Container#replay-container {
        layout: vertical;
        align-horizontal: center;
    }

    Container#replay-container > Static {
        width: 60;
        text-align: center;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [Binding("q", "quit_app", "Quit")]

    def __init__(self, config: CyaConfig, repo: StoryRepository, engine: StoryEngine):
        super().__init__()
        self.config = config
        self.repo = repo
        self.engine = engine
        self._story_busy = False

    def compose(self) -> ComposeResult:
        yield MenuScreen(self.repo)

    def on_mount(self) -> None:
        self.push_screen(MenuScreen(self.repo))

    def start_new_story(self, premise: str, tone: str = "") -> None:
        """Start a new story from a premise, navigating to the first page.

        Runs the generation as a Textual worker so the NewStoryScreen action can
        return immediately (avoiding a deadlock when the worker pops it).
        """
        self._story_busy = True

        async def _start() -> None:
            try:
                page = await self.engine.start_story(premise, tone)
                self.pop_screen()  # remove the NewStoryScreen
                await self.push_screen(StoryScreen(page["story_id"], page["id"]))
            except LLMError as e:
                self.notify(f"Could not start story: {e.detail}")
                self.pop_screen()  # remove the NewStoryScreen, back to menu
            finally:
                self._story_busy = False

        self.run_worker(_start(), exclusive=True)

    def action_quit_app(self) -> None:
        self.exit()


def main() -> None:
    """Entry point for the `cya` console script."""
    import argparse

    parser = argparse.ArgumentParser(description="Choose Your Adventure")
    parser.add_argument("--model", default="huihui-qwen3.8-27b-abliterated")
    parser.add_argument("--base-url", default="http://llm.courtdata.se/v1")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--db", default="~/.local/share/choose-adventure/stories.db")
    args = parser.parse_args()

    config = CyaConfig(
        base_url=args.base_url,
        model=args.model,
        db_path=str(pathlib.Path(args.db).expanduser()),
        api_key=args.api_key,
    )

    repo = StoryRepository(pathlib.Path(config.db_path).expanduser())
    from choose_adventure.llm.client import LLMClient

    llm = LLMClient(config)
    from choose_adventure.llm.storygen import StoryGenerator

    gen = StoryGenerator(llm)
    engine = StoryEngine(repo, gen)

    app = AdventureApp(config, repo, engine)
    app.run()


if __name__ == "__main__":
    main()
