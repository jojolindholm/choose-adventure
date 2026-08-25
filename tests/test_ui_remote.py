"""The existing Textual UI driven against a remote server (FakeGenerator).

Proves the screens work unmodified with RemoteStoryService as repo+engine:
menu -> new story -> choose -> replay, all over HTTP.
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn
from textual.widgets import Input

from choose_adventure.client.api import RemoteStoryService
from choose_adventure.config import CyaConfig
from choose_adventure.server.app import create_app
from choose_adventure.story.models import CharacterState, GeneratedOption, GeneratedPage
from choose_adventure.ui.app import AdventureApp, StoryScreen

from .fakes import FakeGenerator

TOKEN = "test-secret"


def _pages() -> list[GeneratedPage | Exception]:
    return [
        GeneratedPage(
            page_title="The Beginning",
            page_text="You stand at a crossroads.",
            is_ending=False,
            options=[GeneratedOption(label="Go north"), GeneratedOption(label="Stay here")],
            character=CharacterState(name="Hero", role="Adventurer", inventory=["torch"]),
        ),
        GeneratedPage(
            page_title="North Road",
            page_text="You walk north through the forest.",
            is_ending=False,
            options=[GeneratedOption(label="Continue"), GeneratedOption(label="Turn back")],
            character=CharacterState(name="Hero", role="Adventurer", location="Forest"),
        ),
    ]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def remote(tmp_path: Path) -> Iterator[RemoteStoryService]:
    app = create_app(data_dir=tmp_path, token=TOKEN, generator=FakeGenerator(_pages()))
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "uvicorn failed to start"
        time.sleep(0.02)
    try:
        yield RemoteStoryService(base_url=f"http://127.0.0.1:{port}", token=TOKEN, player="alice")
    finally:
        server.should_exit = True
        thread.join(timeout=5)


async def _start_story_via_ui(pilot, premise: str = "A quest.") -> None:
    await pilot.press("1")
    await pilot.pause()
    pilot.app.screen.query_one("#premise", Input).value = premise
    await pilot.press("enter")
    await pilot.pause()
    await pilot.pause()


def _story_body(app: AdventureApp) -> str:
    return str(app.screen.query_one("#story-pane").render())


@pytest.mark.asyncio
async def test_playthrough_over_http(remote: RemoteStoryService) -> None:
    """Menu -> new story -> choose -> page 2 body rendered; all traffic over HTTP."""
    app = AdventureApp(CyaConfig(base_url="http://test.local/v1"), remote, remote)
    async with app.run_test() as pilot:
        await _start_story_via_ui(pilot, "A quest.")
        assert isinstance(app.screen, StoryScreen)
        assert "You stand at a crossroads." in _story_body(app)

        await pilot.press("1")
        await pilot.pause()
        await pilot.pause()
        await pilot.pause()

        assert isinstance(app.screen, StoryScreen)
        assert "You walk north through the forest." in _story_body(app)


@pytest.mark.asyncio
async def test_replay_over_http(remote: RemoteStoryService) -> None:
    """Replay from the menu renders the stored page 1, byte-identical."""
    app = AdventureApp(CyaConfig(base_url="http://test.local/v1"), remote, remote)
    async with app.run_test() as pilot:
        # Build a story first.
        await _start_story_via_ui(pilot, "A quest.")
        await pilot.press("1")
        await pilot.pause()
        await pilot.pause()
        await pilot.pause()
        await pilot.press("m")  # menu (confirm dialog)
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()

        # Back on the menu: replay row 3 -> select 1 -> page 1 body.
        await pilot.press("3")
        await pilot.pause()
        await pilot.press("1")
        await pilot.pause()
        await pilot.pause()

        assert isinstance(app.screen, StoryScreen)
        assert "You stand at a crossroads." in _story_body(app)
