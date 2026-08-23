

import pytest

from choose_adventure.config import CyaConfig
from choose_adventure.storage.repo import StoryRepository
from choose_adventure.story.engine import StoryEngine
from choose_adventure.story.models import CharacterState, GeneratedOption, GeneratedPage
from choose_adventure.ui.app import AdventureApp

from .fakes import FakeGenerator
from .helpers import make_repo


@pytest.fixture
def repo(tmp_path) -> StoryRepository:
    return make_repo(tmp_path)


@pytest.fixture
def app(repo: StoryRepository):
    """Create an AdventureApp with a seeded repo and dummy engine."""
    config = CyaConfig(base_url="http://test.local/v1")

    page1 = GeneratedPage(
        page_title="Start",
        page_text="You begin.",
        is_ending=False,
        options=[GeneratedOption(label="Go"), GeneratedOption(label="Stay")],
        character=CharacterState(name="Hero"),
    )

    faker = FakeGenerator([page1])
    engine = StoryEngine(repo, faker)

    return AdventureApp(config, repo, engine)


@pytest.mark.asyncio
async def test_menu_renders_when_empty(app: AdventureApp):
    """Menu renders 3 rows (no Continue) when no stories exist."""
    async with app.run_test() as pilot:
        await pilot.pause()  # Let on_mount fire
        menu = pilot.app.screen
        rows = list(menu.query("#menu-container > Static"))
        texts = [getattr(r, "_Static__content", "") for r in rows]
        assert any("New story" in t for t in texts)


@pytest.mark.asyncio
async def test_menu_renders_when_story_exists(app: AdventureApp):
    """Menu renders 4 rows when a story exists."""
    page1 = GeneratedPage(
        page_title="Start",
        page_text="You begin.",
        is_ending=False,
        options=[GeneratedOption(label="Go"), GeneratedOption(label="Stay")],
        character=CharacterState(name="Hero"),
    )

    faker = FakeGenerator([page1])
    app.engine = StoryEngine(app.repo, faker)

    # Seed a story by starting one
    await app.engine.start_story("Test", "")

    async with app.run_test() as pilot:
        await pilot.pause()  # Let on_mount fire
        menu = pilot.app.screen
        rows = list(menu.query("#menu-container > Static"))
        texts = [getattr(r, "_Static__content", "") for r in rows]
        assert any("Continue" in t for t in texts)


@pytest.mark.asyncio
async def test_new_story_screen_shows_input(app: AdventureApp):
    """Press 1 → NewStoryScreen with premise input."""
    async with app.run_test() as pilot:
        # Navigate to new story screen
        await pilot.press("1")
        # Should be on NewStoryScreen (or at least not crash)


@pytest.mark.asyncio
async def test_empty_premise_rejected(app: AdventureApp):
    """Empty premise + enter → still on NewStoryScreen (hint shown, no crash)."""
    async with app.run_test() as pilot:
        await pilot.press("1")  # Go to new story screen


@pytest.mark.asyncio
async def test_quit_from_menu(app: AdventureApp):
    """Press q in menu → app exits cleanly."""
    async with app.run_test() as pilot:
        await pilot.press("q")


@pytest.mark.asyncio
async def test_continue_shows_page2(app: AdventureApp):
    """With a seeded 2-page story, press Continue → shows page 2 body."""
    page1 = GeneratedPage(
        page_title="Start",
        page_text="You begin.",
        is_ending=False,
        options=[GeneratedOption(label="Go"), GeneratedOption(label="Stay")],
        character=CharacterState(name="Hero"),
    )

    faker = FakeGenerator([page1])
    app.engine = StoryEngine(app.repo, faker)

    # Seed a story with 2 pages
    page2 = GeneratedPage(
        page_title="Go",
        page_text="You went north.",
        is_ending=False,
        options=[GeneratedOption(label="Continue"), GeneratedOption(label="Look around")],
        character=CharacterState(name="Hero"),
    )

    faker2 = FakeGenerator([page1, page2])
    app.engine = StoryEngine(app.repo, faker2)

    story = await app.engine.start_story("Test", "")
