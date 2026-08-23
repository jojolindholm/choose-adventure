"""T9 lifecycle tests: continue-resume, replay growth, mid-game keys, ending actions.

These cover cross-instance resume, zero-LLM replay, lazy option expansion during
replay, mid-game `n`/`r` confirm dialogs, and the ending-actions regression path.
"""

from pathlib import Path

import pytest
from textual.widgets import Input

from choose_adventure.config import CyaConfig
from choose_adventure.storage.repo import StoryRepository
from choose_adventure.story.engine import StoryEngine
from choose_adventure.story.models import CharacterState, GeneratedOption, GeneratedPage
from choose_adventure.ui.app import AdventureApp, ConfirmDialog, NewStoryScreen, StoryScreen

from .fakes import FakeGenerator
from .helpers import seed_story


@pytest.fixture
def repo(tmp_path: Path) -> StoryRepository:
    return StoryRepository(tmp_path / "test.db")


@pytest.fixture
def faker():
    """Scripted pages: page1 -> page2 -> ending."""
    page1 = GeneratedPage(
        page_title="The Beginning",
        page_text="You stand at a crossroads.",
        is_ending=False,
        options=[GeneratedOption(label="Go north"), GeneratedOption(label="Stay here")],
        character=CharacterState(name="Hero", role="Adventurer", inventory=["torch"]),
    )
    page2 = GeneratedPage(
        page_title="North Road",
        page_text="You walk north through the forest.",
        is_ending=False,
        options=[GeneratedOption(label="Continue"), GeneratedOption(label="Turn back")],
        character=CharacterState(name="Hero", role="Adventurer", location="Forest"),
    )
    ending = GeneratedPage(
        page_title="The End",
        page_text="You found what you sought.",
        is_ending=True,
        options=[],
        character=CharacterState(name="Hero", role="Adventurer"),
    )
    return FakeGenerator([page1, page2, ending])


@pytest.fixture
def app(repo: StoryRepository, faker: FakeGenerator):
    config = CyaConfig(base_url="http://test.local/v1")
    engine = StoryEngine(repo, faker)
    return AdventureApp(config, repo, engine)


def _make_app(repo: StoryRepository, faker: FakeGenerator) -> AdventureApp:
    config = CyaConfig(base_url="http://test.local/v1")
    engine = StoryEngine(repo, faker)
    return AdventureApp(config, repo, engine)


async def _start_story_via_ui(pilot, premise: str = "A quest.") -> None:
    """Drive the UI: menu → NewStoryScreen → type premise → Enter → StoryScreen."""
    await pilot.press("1")
    await pilot.pause()
    pilot.app.screen.query_one("#premise", Input).value = premise
    await pilot.press("enter")
    await pilot.pause()
    await pilot.pause()


def _story_body(app: AdventureApp) -> str:
    return str(app.screen.query_one("#story-pane").render())


def _menu_texts(app: AdventureApp) -> list[str]:
    """Return the rendered text of each menu row."""
    menu = app.screen
    rows = list(menu.query("#menu-container > Static"))
    return [str(r.render()) for r in rows]


async def _build_two_page_story(repo: StoryRepository, faker: FakeGenerator) -> None:
    """Start a story via the engine and make one choice to reach page 2."""
    app = _make_app(repo, faker)
    async with app.run_test():
        page = await app.engine.start_story("Test", "")
        opts = repo.get_options(page["id"])
        await app.engine.choose(page["story_id"], page, opts[0])


@pytest.mark.asyncio
async def test_continue_across_instances(repo: StoryRepository):
    """app#1 builds a 2-page story; app#2 (same repo) Continue → page-2 body."""
    page1 = GeneratedPage(
        page_title="Start",
        page_text="You begin.",
        is_ending=False,
        options=[GeneratedOption(label="Go"), GeneratedOption(label="Stay")],
        character=CharacterState(name="Hero"),
    )
    page2 = GeneratedPage(
        page_title="North",
        page_text="You went north.",
        is_ending=False,
        options=[GeneratedOption(label="Continue"), GeneratedOption(label="Look")],
        character=CharacterState(name="Hero"),
    )
    await _build_two_page_story(repo, FakeGenerator([page1, page2]))

    # app#2 with the SAME repo instance
    app2 = _make_app(repo, FakeGenerator([]))
    async with app2.run_test() as pilot:
        await pilot.pause()  # let on_mount fire
        texts = _menu_texts(app2)
        assert any("Continue" in t for t in texts)

        await pilot.press("2")
        await pilot.pause()
        assert isinstance(app2.screen, StoryScreen)
        assert "You went north." in _story_body(app2)


@pytest.mark.asyncio
async def test_replay_zero_llm_calls(repo: StoryRepository):
    """Replay a fully-linked story → byte-identical pages, zero LLM calls."""
    page1 = GeneratedPage(
        page_title="Start",
        page_text="You begin.",
        is_ending=False,
        options=[GeneratedOption(label="Go"), GeneratedOption(label="Stay")],
        character=CharacterState(name="Hero"),
    )
    page2 = GeneratedPage(
        page_title="North",
        page_text="You went north.",
        is_ending=False,
        options=[GeneratedOption(label="Continue"), GeneratedOption(label="Look")],
        character=CharacterState(name="Hero"),
    )
    await _build_two_page_story(repo, FakeGenerator([page1, page2]))

    # Fresh app on the same repo; empty script → any LLM call would fail loudly.
    replay_faker = FakeGenerator([])
    app = _make_app(repo, replay_faker)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("3")  # Replay
        await pilot.pause()
        await pilot.press("1")  # select story 1
        await pilot.pause()

        assert isinstance(app.screen, StoryScreen)
        story = repo.latest_story()
        assert story is not None
        first_id = repo.first_page_id(story["id"])
        assert first_id is not None
        stored_page1 = repo.get_page(first_id)
        assert stored_page1 is not None
        assert _story_body(app) == f"{stored_page1['title']}\n\n{stored_page1['body']}"

        # Choose the already-linked option → page-2 byte-identical, no LLM call.
        await pilot.press("1")
        await pilot.pause()
        await pilot.pause()
        latest = repo.latest_story()
        assert latest is not None
        last_id = latest["last_page_id"]
        assert last_id is not None
        stored_page2 = repo.get_page(last_id)
        assert stored_page2 is not None
        assert _story_body(app) == f"{stored_page2['title']}\n\n{stored_page2['body']}"
        assert len(replay_faker.calls) == 0


@pytest.mark.asyncio
async def test_replay_grows_unexpanded_option(repo: StoryRepository):
    """Replay → choose an unlinked option → new page generated + option linked."""
    char = CharacterState(name="Hero")
    seed_story(
        repo,
        [
            ("Start", "You begin.", ["Go", "Stay"], char, False),
            ("North", "You went north.", ["Continue", "Look"], char, False),
        ],
    )
    story = repo.latest_story()
    assert story is not None
    first_id = repo.first_page_id(story["id"])
    assert first_id is not None
    opts_before = repo.get_options(first_id)
    assert opts_before[1]["target_page_id"] is None  # "Stay" is unlinked

    new_page = GeneratedPage(
        page_title="Stay Path",
        page_text="You stayed where you were.",
        is_ending=False,
        options=[GeneratedOption(label="Continue"), GeneratedOption(label="Leave")],
        character=CharacterState(name="Hero"),
    )
    faker = FakeGenerator([new_page])
    app = _make_app(repo, faker)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("3")  # Replay
        await pilot.pause()
        await pilot.press("1")  # select story 1
        await pilot.pause()
        assert isinstance(app.screen, StoryScreen)

        calls_before = len(faker.calls)  # 0
        await pilot.press("2")  # choose "Stay" (unexpanded)
        await pilot.pause()
        await pilot.pause()

        assert len(faker.calls) == calls_before + 1
        opts_after = repo.get_options(first_id)
        assert opts_after[1]["target_page_id"] is not None
        assert "You stayed where you were." in _story_body(app)


@pytest.mark.asyncio
async def test_midgame_new_story_n(app: AdventureApp, faker: FakeGenerator):
    """Mid-game press n → ConfirmDialog → yes → NewStoryScreen."""
    async with app.run_test() as pilot:
        await _start_story_via_ui(pilot, "Test")
        assert isinstance(app.screen, StoryScreen)

        await pilot.press("n")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmDialog)

        await pilot.press("y")
        await pilot.pause()
        assert isinstance(app.screen, NewStoryScreen)


@pytest.mark.asyncio
async def test_midgame_replay_r(app: AdventureApp, faker: FakeGenerator):
    """Mid-game press r → ConfirmDialog → yes → same story at page 1."""
    async with app.run_test() as pilot:
        await _start_story_via_ui(pilot, "Test")
        assert isinstance(app.screen, StoryScreen)

        # Advance to page 2 so replay visibly resets to page 1.
        await pilot.press("1")
        await pilot.pause()
        await pilot.pause()
        assert "You walk north through the forest." in _story_body(app)

        await pilot.press("r")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmDialog)

        await pilot.press("y")
        await pilot.pause()
        assert isinstance(app.screen, StoryScreen)
        topbar = str(app.screen.query_one("#topbar").render())
        assert "Page 1" in topbar
        assert "You stand at a crossroads." in _story_body(app)


@pytest.mark.asyncio
async def test_ending_actions_regression(app: AdventureApp, faker: FakeGenerator):
    """Replay to an ending → ending actions visible; replay routes back to page 1."""
    async with app.run_test() as pilot:
        await _start_story_via_ui(pilot, "Test")
        assert isinstance(app.screen, StoryScreen)

        # Play to the ending.
        await pilot.press("1")
        await pilot.pause()
        await pilot.pause()
        await pilot.press("1")
        await pilot.pause()
        await pilot.pause()
        assert "— The End —" in _story_body(app)

        # Ending actions visible.
        dock = app.screen.query_one("#options-dock")
        ending_text = str(dock.query_one("#ending-actions").render())
        assert "Replay this story" in ending_text
        assert "New story" in ending_text
        assert "Menu" in ending_text

        # Ending action 1 → replay this story at page 1.
        await pilot.press("1")
        await pilot.pause()
        assert isinstance(app.screen, StoryScreen)
        assert "You stand at a crossroads." in _story_body(app)
