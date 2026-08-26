"""RemoteStoryService tests against a real uvicorn server (FakeGenerator injected).

Proves the full HTTP path: headers, JSON, per-player DB, error mapping.
"""

import asyncio
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn

from choose_adventure.client.api import RemoteStoryService
from choose_adventure.llm.errors import LLMOutputError, LLMTransportError
from choose_adventure.server.app import create_app
from choose_adventure.story.models import CharacterState, GeneratedOption, GeneratedPage

from .fakes import FakeGenerator

TOKEN = "test-secret"
ART = "  /\\\n /  \\\n/____\\"


def _pages() -> list[GeneratedPage | Exception]:
    return [
        GeneratedPage(
            page_title="The Beginning",
            page_text="You stand at a crossroads.",
            is_ending=False,
            options=[GeneratedOption(label="Go north"), GeneratedOption(label="Stay here")],
            character=CharacterState(name="Hero", role="Adventurer"),
            ascii_art=ART,
            story_name="The Ember Road",
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


class ServerFixture:
    """Run a uvicorn server on an ephemeral port in a background thread."""

    def __init__(self, app):
        self._port = _free_port()
        config = uvicorn.Config(app, host="127.0.0.1", port=self._port, log_level="warning")
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)

    def start(self) -> None:
        self._thread.start()
        deadline = time.monotonic() + 10
        while not self._server.started:
            if time.monotonic() > deadline:
                raise RuntimeError("uvicorn server failed to start")
            time.sleep(0.02)

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=5)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._port}"


@pytest.fixture
def server(tmp_path: Path) -> Iterator[ServerFixture]:
    app = create_app(data_dir=tmp_path, token=TOKEN, generator=FakeGenerator(_pages()))
    srv = ServerFixture(app)
    srv.start()
    try:
        yield srv
    finally:
        srv.stop()


@pytest.fixture
def remote(server: ServerFixture) -> RemoteStoryService:
    return RemoteStoryService(base_url=server.url, token=TOKEN, player="alice")


@pytest.mark.asyncio
async def test_start_story_and_reads(remote: RemoteStoryService) -> None:
    page = await remote.start_story("A quest.", "epic")
    assert page["seq"] == 1
    assert page["ascii_art"] == ART
    assert page["is_ending"] is False

    # Reads round-trip.
    stored = remote.get_page(page["id"])
    assert stored is not None
    assert stored["body"] == "You stand at a crossroads."

    options = remote.get_options(page["id"])
    assert [o["label"] for o in options] == ["Go north", "Stay here"]

    char = remote.get_character(page["id"])
    assert char is not None and char.name == "Hero"

    story = remote.latest_story()
    assert story is not None and story["last_page_id"] == page["id"]

    stories = remote.list_stories()
    assert len(stories) == 1
    assert stories[0].title == "The Beginning"

    assert remote.first_page_id(page["story_id"]) == page["id"]
    # Generated story name round-trips through the API.
    fetched = remote.get_story(page["story_id"])
    assert fetched["name"] == "The Ember Road"
    assert stories[0].name == "The Ember Road"


@pytest.mark.asyncio
async def test_choose_returns_linked_page(remote: RemoteStoryService) -> None:
    page = await remote.start_story("A quest.", "epic")
    option = remote.get_options(page["id"])[0]
    page2 = await remote.choose(page["story_id"], page, option)
    assert page2["title"] == "North Road"
    assert page2["parent_page_id"] == page["id"]


def test_per_player_databases_are_separate(server: ServerFixture) -> None:
    alice = RemoteStoryService(base_url=server.url, token=TOKEN, player="alice")
    bob = RemoteStoryService(base_url=server.url, token=TOKEN, player="bob")

    async def start() -> None:
        page = await alice.start_story("A quest.", "epic")
        assert page["seq"] == 1

    asyncio.run(start())
    assert alice.list_stories() != []
    assert bob.list_stories() == []


def test_bad_token_rejected(server: ServerFixture) -> None:
    bad = RemoteStoryService(base_url=server.url, token="wrong", player="alice")
    with pytest.raises(LLMTransportError):
        bad.list_stories()


@pytest.mark.asyncio
async def test_llm_error_surfaces_as_llm_output_error(tmp_path: Path) -> None:
    script: list[GeneratedPage | Exception] = [LLMOutputError("boom")]
    app = create_app(data_dir=tmp_path, token=TOKEN, generator=FakeGenerator(script))
    srv = ServerFixture(app)
    srv.start()
    try:
        remote = RemoteStoryService(base_url=srv.url, token=TOKEN, player="alice")
        with pytest.raises(LLMOutputError) as exc:
            await remote.start_story("A quest.", "epic")
        assert exc.value.detail == "boom"
    finally:
        srv.stop()


def test_unreachable_server_raises_transport_error() -> None:
    remote = RemoteStoryService(
        base_url="http://127.0.0.1:1", token=TOKEN, player="alice", timeout=2.0
    )
    with pytest.raises(LLMTransportError):
        remote.list_stories()
