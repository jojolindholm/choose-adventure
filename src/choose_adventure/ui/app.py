

from __future__ import annotations

import asyncio
import pathlib
from typing import Any

from typing import cast

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from choose_adventure.config import CyaConfig
from choose_adventure.llm.errors import LLMError
from choose_adventure.story.errors import StoryEndedError
from choose_adventure.storage.repo import StoryRepository, StorySummary
from choose_adventure.story.engine import PageGenerator, StoryEngine


class MenuScreen(Screen):
    """Main menu screen."""

    BINDINGS = [
        Binding("1", "new_story", "New story"),
        Binding("2", "continue_story", "Continue"),
        Binding("3", "replay_stories", "Replay..."),
        Binding("q", "quit_app", "Quit"),
    ]

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

    BINDINGS = [Binding("escape", "menu", "Menu")]

    def __init__(self):
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Static("NEW STORY", id="title"),
            Static("Story premise (one line):", id="premise-label"),
            Static("", id="hint"),
            id="new-story-container",
        )
        yield Footer()

    def on_mount(self) -> None:
        container = self.query_one("#new-story-container", Container)
        container.remove_children()

        premise_input = Static(
            "Type your premise here (press Enter to begin)", id="premise-input"
        )
        tone_input = Static("Tone (optional, e.g. eerie, comedic)", id="tone-input")
        hint = Static("", id="hint")

        container.mount(Static("NEW STORY", id="title"), premise_input, tone_input, hint)

    def action_menu(self) -> None:
        self.app.pop_screen()


class StoryScreen(Screen):
    """Story playing screen."""

    BINDINGS = [
        Binding("escape", "menu", "Menu"),
        Binding("n", "new_story_mid_game", "New story"),
    ]

    app: AdventureApp

    def __init__(self, story_id: int, page_id: int):
        super().__init__()
        self._story_id = story_id
        self._page_id = page_id
        self._page: dict | None = None
        self._options: list[dict] = []
        self._busy = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(Static("", id="topbar"), Static("", id="story-pane"))
        yield Container(Static("", id="options-dock"))
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

        # Update story pane
        self.query_one("#story-pane", Static).update(
            f"{self._page['title']}\n\n{self._page['body']}"
        )

        # Load options
        self._options = self.app.repo.get_options(self._page["id"])

        # Update options dock
        dock = self.query_one("#options-dock", Container)
        dock.remove_children()
        if not self._page["is_ending"]:
            for i, opt in enumerate(self._options, 1):
                dock.mount(Static(f"[{i}] {opt['label']}", id=f"opt-{i}"))
        else:
            dock.mount(Static("— The End —", id="ending-text"))

    def action_menu(self) -> None:
        self.app.pop_screen()

    def action_new_story_mid_game(self) -> None:
        self.app.push_screen(NewStoryScreen())

    def _choose(self, option_index: int) -> None:
        """Choose an option by index (1-based)."""
        if self._busy or not self._options:
            return

        if option_index < 1 or option_index > len(self._options):
            self.notify(f"Invalid choice. Enter 1-{len(self._options)}.")
            return

        option = self._options[option_index - 1]
        self._busy = True

        async def _do_choose() -> None:
            assert self._page is not None, "No page loaded"
            try:
                new_page = await self.app.engine.choose(self._story_id, self._page, option)
                self._page = new_page
                self._page_id = new_page["id"]
                self._load_page()
            except LLMError as e:
                self.notify(f"The tale faltered: {e.detail}")
            except StoryEndedError:
                self.notify("The story has ended.")
            finally:
                self._busy = False

        self.app.run_worker(_do_choose(), exclusive=True)


class ReplayListScreen(Screen):
    """List of saved stories to replay."""

    BINDINGS = [Binding("escape", "menu", "Menu")]

    def __init__(self, stories: list[StorySummary]):
        super().__init__()
        self._stories = stories

    def compose(self) -> ComposeResult:
        yield Header()
        container = Container(id="replay-container")
        for i, story in enumerate(self._stories, 1):
            container.mount(Static(f"{i}. {story.title} — \"{story.premise}\"", id=f"replay-{i}"))
        yield container
        yield Footer()

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

    #topbar {
        dock: top;
        height: 1;
        border-bottom: solid $primary;
    }

    #story-pane {
        width: 1fr;
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

    #ending-text {
        text-align: center;
        height: 1;
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

    BINDINGS = [Binding("q", "quit_app", "Quit")]

    def __init__(self, config: CyaConfig, repo: StoryRepository, engine: StoryEngine):
        super().__init__()
        self.config = config
        self.repo = repo
        self.engine = engine

    def compose(self) -> ComposeResult:
        yield Header()
        yield MenuScreen(self.repo)

    def action_quit_app(self) -> None:
        self.exit()


# CLI entry point stub — wired in T10
def main() -> None:
    """Entry point for the `cya` console script."""
    import argparse

    parser = argparse.ArgumentParser(description="Choose Your Adventure")
    parser.add_argument("--model", default="qwen/qwen3.8-27b")
    parser.add_argument("--base-url", default="http://llm.courtdata.se/v1")
    parser.add_argument("--db", default="~/.local/share/choose-adventure/stories.db")
    args = parser.parse_args()

    config = CyaConfig(
        base_url=args.base_url,
        model=args.model,
        db_path=str(__import__("pathlib").Path(args.db).expanduser()),
    )

    repo = StoryRepository(pathlib.Path(config.db_path).expanduser())
    # Use a dummy generator for now — T10 wires the real one
    from choose_adventure.llm.client import LLMClient
    llm = LLMClient(config)
    from choose_adventure.llm.storygen import StoryGenerator
    gen = StoryGenerator(llm)
    engine = StoryEngine(repo, gen)

    app = AdventureApp(config, repo, engine)
    app.run()


if __name__ == "__main__":
    main()
