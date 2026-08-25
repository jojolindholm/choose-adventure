from pathlib import Path

import pytest
from textual.widgets import Input

from choose_adventure.config import CyaConfig
from choose_adventure.llm.errors import LLMOutputError
from choose_adventure.storage.repo import StoryRepository
from choose_adventure.story.engine import StoryEngine
from choose_adventure.story.models import CharacterState, GeneratedOption, GeneratedPage
from choose_adventure.ui.app import AdventureApp, ConfirmDialog, NewStoryScreen, StoryScreen
from choose_adventure.ui.widgets import CharacterPanel

from .fakes import FakeGenerator


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


@pytest.mark.asyncio
async def test_full_playthrough_to_ending(app: AdventureApp, faker: FakeGenerator):
    """New story → press 1 → page-2 body rendered; character pane shows name + inventory."""
    async with app.run_test() as pilot:
        await _start_story_via_ui(pilot, "A quest.")
        assert isinstance(app.screen, StoryScreen)

        await pilot.press("1")
        await pilot.pause()
        await pilot.pause()

        assert isinstance(app.screen, StoryScreen)
        assert "You walk north through the forest." in _story_body(app)

        char_panel = app.screen.query_one("#character-pane", CharacterPanel)
        text = str(char_panel.render())
        assert "Hero" in text
        assert "torch" in text


@pytest.mark.asyncio
async def test_ascii_art_rendered_under_body(repo: StoryRepository):
    """ASCII art is displayed underneath the story text."""
    art = "  /\\\n /  \\\n/____\\"
    page1 = GeneratedPage(
        page_title="The Beginning",
        page_text="You stand at a crossroads.",
        is_ending=False,
        options=[GeneratedOption(label="Go north"), GeneratedOption(label="Stay here")],
        character=CharacterState(name="Hero"),
        ascii_art=art,
    )
    engine = StoryEngine(repo, FakeGenerator([page1]))
    config = CyaConfig(base_url="http://test.local/v1")
    art_app = AdventureApp(config, repo, engine)

    async with art_app.run_test() as pilot:
        await _start_story_via_ui(pilot, "A quest.")
        body = _story_body(art_app)
        assert "You stand at a crossroads." in body
        assert art in body
        # Art appears after the body text, not before it
        assert body.index(art) > body.index("You stand at a crossroads.")


@pytest.mark.asyncio
async def test_ending_replay(app: AdventureApp, faker: FakeGenerator):
    """Reach ending → 'The End' shown; press ending 1 → page-1 body."""
    async with app.run_test() as pilot:
        await _start_story_via_ui(pilot, "A quest.")
        await pilot.press("1")
        await pilot.pause()
        await pilot.pause()
        await pilot.press("1")
        await pilot.pause()
        await pilot.pause()

        assert isinstance(app.screen, StoryScreen)
        assert "— The End —" in _story_body(app)

        # Ending action 1 → replay this story at page 1
        await pilot.press("1")
        await pilot.pause()
        assert isinstance(app.screen, StoryScreen)
        assert "You stand at a crossroads." in _story_body(app)


@pytest.mark.asyncio
async def test_ending_new_story(app: AdventureApp, faker: FakeGenerator):
    """Reach ending → press ending 2 → NewStoryScreen."""
    async with app.run_test() as pilot:
        await _start_story_via_ui(pilot, "A quest.")
        await pilot.press("1")
        await pilot.pause()
        await pilot.pause()
        await pilot.press("1")
        await pilot.pause()
        await pilot.pause()

        assert "— The End —" in _story_body(app)

        # Ending action 2 → new story (confirm dialog, then yes)
        await pilot.press("2")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmDialog)
        await pilot.press("y")
        await pilot.pause()
        assert isinstance(app.screen, NewStoryScreen)


@pytest.mark.asyncio
async def test_error_retry(app: AdventureApp, faker: FakeGenerator):
    """Script [page1, LLMOutputError('boom'), page2] → error visible; press a → recovery."""
    page1 = GeneratedPage(
        page_title="Start",
        page_text="You begin.",
        is_ending=False,
        options=[GeneratedOption(label="Go"), GeneratedOption(label="Stay")],
        character=CharacterState(name="Hero"),
    )
    page2 = GeneratedPage(
        page_title="Go",
        page_text="You went.",
        is_ending=False,
        options=[GeneratedOption(label="Continue"), GeneratedOption(label="Stop")],
        character=CharacterState(name="Hero"),
    )

    error_faker = FakeGenerator([page1, LLMOutputError("boom"), page2])
    app.engine = StoryEngine(app.repo, error_faker)

    async with app.run_test() as pilot:
        await _start_story_via_ui(pilot, "Test")
        assert isinstance(app.screen, StoryScreen)

        await pilot.press("1")
        await pilot.pause()
        await pilot.pause()

        # Error text should be visible
        dock = app.screen.query_one("#options-dock")
        error_text = str(dock.query_one("#error-text").render())
        assert "boom" in error_text

        # Press a → retry → page2 body visible
        await pilot.press("a")
        await pilot.pause()
        await pilot.pause()
        assert "You went." in _story_body(app)


@pytest.mark.asyncio
async def test_busy_guard(app: AdventureApp, faker: FakeGenerator):
    """FakeGenerator delay=0.3 → press 1 three times rapidly → only one choose call."""
    delay_faker = FakeGenerator([faker._script[0], faker._script[1]], delay=0.3)
    app.engine = StoryEngine(app.repo, delay_faker)

    async with app.run_test() as pilot:
        await _start_story_via_ui(pilot, "Test")
        await pilot.pause(0.5)  # let the delayed start_story finish
        assert isinstance(app.screen, StoryScreen)

        calls_before = len(delay_faker.calls)  # 1 (start_story)
        await pilot.press("1")
        await pilot.press("1")
        await pilot.press("1")
        await pilot.pause(0.5)

        # Only one choose call made despite 3 rapid presses (busy guard).
        assert len(delay_faker.calls) == calls_before + 1


@pytest.mark.asyncio
async def test_confirm_quit(app: AdventureApp, faker: FakeGenerator):
    """Mid-game press q → ConfirmDialog visible → y → app exits."""
    async with app.run_test() as pilot:
        await _start_story_via_ui(pilot, "Test")
        assert isinstance(app.screen, StoryScreen)

        await pilot.press("q")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmDialog)

        await pilot.press("y")
        await pilot.pause()
        assert app._exit is True


@pytest.mark.asyncio
async def test_confirm_new_story(app: AdventureApp, faker: FakeGenerator):
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
async def test_exact_replay_from_menu(app: AdventureApp, faker: FakeGenerator):
    """After playthrough, menu → replay → page-1 body byte-identical; linked option no LLM call."""
    async with app.run_test() as pilot:
        await _start_story_via_ui(pilot, "Test")
        assert isinstance(app.screen, StoryScreen)

        # Play to page 2 (generates + links option 1 → page2)
        await pilot.press("1")
        await pilot.pause()
        await pilot.pause()
        assert "You walk north through the forest." in _story_body(app)
        calls_after_play = len(faker.calls)  # 2 (page1 + page2)

        # Back to menu
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmDialog)
        await pilot.press("y")
        await pilot.pause()

        # Menu → replay → pick story 1
        await pilot.press("3")
        await pilot.pause()
        await pilot.press("1")
        await pilot.pause()

        assert isinstance(app.screen, StoryScreen)
        latest = app.repo.latest_story()
        assert latest is not None
        first_id = app.repo.first_page_id(latest["id"])
        assert first_id is not None
        stored_page1 = app.repo.get_page(first_id)
        assert stored_page1 is not None
        assert _story_body(app) == f"{stored_page1['title']}\n\n{stored_page1['body']}"

        # Choose already-linked option → page2 identical, no LLM call
        await pilot.press("1")
        await pilot.pause()
        await pilot.pause()
        latest_after = app.repo.latest_story()
        assert latest_after is not None
        last_id = latest_after["last_page_id"]
        assert last_id is not None
        stored_page2 = app.repo.get_page(last_id)
        assert stored_page2 is not None
        assert _story_body(app) == f"{stored_page2['title']}\n\n{stored_page2['body']}"
        assert len(faker.calls) == calls_after_play
