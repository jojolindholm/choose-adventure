import pytest
from textual.widgets import Input

from choose_adventure.config import CyaConfig
from choose_adventure.storage.repo import StoryRepository
from choose_adventure.story.engine import StoryEngine
from choose_adventure.story.models import CharacterState, GeneratedOption, GeneratedPage
from choose_adventure.ui.app import AdventureApp, NewStoryScreen, StoryScreen

from .fakes import FakeGenerator
from .helpers import make_repo, seed_story


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


def _menu_texts(app: AdventureApp) -> list[str]:
    """Return the rendered text of each menu row."""
    menu = app.screen
    rows = list(menu.query("#menu-container > Static"))
    return [str(r.render()) for r in rows]


async def _start_story_via_ui(pilot, premise: str = "A mysterious door.") -> None:
    """Drive the UI: menu → NewStoryScreen → type premise → Enter → StoryScreen."""
    await pilot.press("1")
    await pilot.pause()
    pilot.app.screen.query_one("#premise", Input).value = premise
    await pilot.press("enter")
    await pilot.pause()
    await pilot.pause()


@pytest.mark.asyncio
async def test_menu_renders_when_empty(app: AdventureApp):
    """Menu renders New story / Replay / Quit and NO Continue row when empty."""
    async with app.run_test() as pilot:
        await pilot.pause()  # Let on_mount fire
        texts = _menu_texts(app)
        assert any("New story" in t for t in texts)
        assert any("Replay a saved story" in t for t in texts)
        assert any("Quit" in t for t in texts)
        assert not any("Continue" in t for t in texts)


@pytest.mark.asyncio
async def test_menu_renders_when_story_exists(app: AdventureApp, repo: StoryRepository):
    """Menu renders a Continue row when a story exists."""
    page1 = GeneratedPage(
        page_title="Start",
        page_text="You begin.",
        is_ending=False,
        options=[GeneratedOption(label="Go"), GeneratedOption(label="Stay")],
        character=CharacterState(name="Hero"),
    )
    faker = FakeGenerator([page1])
    app.engine = StoryEngine(repo, faker)

    # Seed a story by starting one
    await app.engine.start_story("Test", "")

    async with app.run_test() as pilot:
        await pilot.pause()  # Let on_mount fire
        texts = _menu_texts(app)
        assert any("Continue" in t for t in texts)


@pytest.mark.asyncio
async def test_new_story_screen_shows_input(app: AdventureApp):
    """Press 1 → NewStoryScreen with real premise + tone Input widgets."""
    async with app.run_test() as pilot:
        await pilot.press("1")
        await pilot.pause()
        assert isinstance(app.screen, NewStoryScreen)
        premise = app.screen.query_one("#premise", Input)
        assert premise is not None
        assert app.screen.query_one("#tone", Input) is not None


@pytest.mark.asyncio
async def test_start_story_via_ui(app: AdventureApp):
    """Type a premise + Enter → StoryScreen shows page-1 body and story is created."""
    async with app.run_test() as pilot:
        await _start_story_via_ui(pilot, "A mysterious door.")
        assert isinstance(app.screen, StoryScreen)
        body = str(app.screen.query_one("#story-pane").render())
        assert "You begin." in body
        assert app.repo.latest_story() is not None


@pytest.mark.asyncio
async def test_empty_premise_rejected(app: AdventureApp):
    """Empty premise + Enter → still on NewStoryScreen, hint shown, no story created."""
    async with app.run_test() as pilot:
        await pilot.press("1")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, NewStoryScreen)
        hint = str(app.screen.query_one("#hint").render())
        assert "Give the story a premise first." in hint
        assert app.repo.latest_story() is None


@pytest.mark.asyncio
async def test_quit_from_menu(app: AdventureApp):
    """Press q in menu → app exits cleanly."""
    async with app.run_test() as pilot:
        await pilot.press("q")
        await pilot.pause()
        assert app._exit is True


@pytest.mark.asyncio
async def test_continue_shows_page2(app: AdventureApp, repo: StoryRepository):
    """With a seeded 2-page story, press Continue → StoryScreen shows page-2 body."""
    char = CharacterState(name="Hero")
    seed_story(
        repo,
        [
            ("Start", "You begin.", ["Go", "Stay"], char, False),
            ("North", "You went north.", ["Continue", "Look"], char, False),
        ],
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("2")
        await pilot.pause()
        assert isinstance(app.screen, StoryScreen)
        body = str(app.screen.query_one("#story-pane").render())
        assert "You went north." in body
