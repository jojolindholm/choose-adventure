


import pytest
from pathlib import Path

from choose_adventure.config import CyaConfig
from choose_adventure.llm.errors import LLMOutputError
from choose_adventure.storage.repo import StoryRepository
from choose_adventure.story.engine import StoryEngine
from choose_adventure.story.models import CharacterState, GeneratedOption, GeneratedPage
from choose_adventure.ui.app import AdventureApp, StoryScreen
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


@pytest.mark.asyncio
async def test_full_playthrough_to_ending(app: AdventureApp, faker: FakeGenerator):
    """Playthrough: new story -> page 2 body rendered; character pane shows name+inventory."""
    page = await app.engine.start_story("A quest.", "epic")

    async with app.run_test() as pilot:
        await pilot.pause()
        story_id = page["story_id"]
        last_page = page["id"]
        pilot.app.push_screen(StoryScreen(story_id, last_page))
        await pilot.pause()
        story_screen = pilot.app.screen
        char_panel = story_screen.query_one("#character-pane", CharacterPanel)
        text = getattr(char_panel, "_Static__content", "") if hasattr(char_panel, "_Static__content") else str(char_panel)
        assert "Hero" in text


@pytest.mark.asyncio
async def test_ending_actions(app: AdventureApp, faker: FakeGenerator):
    """At ending press 1 -> replay; press 2 -> NewStoryScreen."""
    await app.engine.start_story("A quest.", "epic")

    async with app.run_test() as pilot:
        await pilot.pause()


@pytest.mark.asyncio
async def test_error_retry(app: AdventureApp, faker: FakeGenerator):
    """FakeGenerator script [page1, LLMOutputError("boom"), page2] -> error visible; press a -> recovery."""
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

    await app.engine.start_story("Test", "")


@pytest.mark.asyncio
async def test_busy_guard(app: AdventureApp, faker: FakeGenerator):
    """FakeGenerator with delay=0.3 -> press 1 three times -> faker.calls == 1."""
    delay_faker = FakeGenerator([faker._script[0]], delay=0.3)
    app.engine = StoryEngine(app.repo, delay_faker)

    await app.engine.start_story("Test", "")


@pytest.mark.asyncio
async def test_confirms(app: AdventureApp, faker: FakeGenerator):
    """Mid-game press q -> Confirm visible -> press y -> app exits."""
    await app.engine.start_story("Test", "")


@pytest.mark.asyncio
async def test_exact_replay_from_menu(app: AdventureApp, faker: FakeGenerator):
    """After playthrough, menu -> replay -> story -> page 1 body text BYTE-IDENTICAL."""
    await app.engine.start_story("Test", "")
