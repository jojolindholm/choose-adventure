

import asyncio

import pytest

from choose_adventure.storage.repo import StoryRepository
from choose_adventure.story.engine import PageGenerator, StoryEngine
from choose_adventure.story.errors import StoryEndedError
from choose_adventure.story.models import (
    CharacterState,
    GeneratedOption,
    GeneratedPage,
)

from .fakes import FakeGenerator


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database file."""
    return tmp_path / "test.db"


@pytest.fixture
def repo(tmp_db):
    """Create a repository pointing to the temp DB."""
    return StoryRepository(tmp_db)


@pytest.fixture
def faker():
    """Create a FakeGenerator with scripted pages."""
    page1 = GeneratedPage(
        page_title="The Beginning",
        page_text="You stand at a crossroads.",
        is_ending=False,
        options=[GeneratedOption(label="Go north"), GeneratedOption(label="Stay here")],
        character=CharacterState(name="Hero", role="Adventurer"),
    )
    page2 = GeneratedPage(
        page_title="North Road",
        page_text="You walk north through the forest.",
        is_ending=False,
        options=[GeneratedOption(label="Continue"), GeneratedOption(label="Turn back")],
        character=CharacterState(name="Hero", role="Adventurer", location="Forest"),
    )
    page3 = GeneratedPage(
        page_title="The End",
        page_text="You found what you sought.",
        is_ending=True,
        options=[],
        character=CharacterState(name="Hero", role="Adventurer"),
    )
    return FakeGenerator([page1, page2, page3])


def test_start_stores_page_with_options(repo, faker):
    """start → page 1 stored with options (target None), character stored."""
    engine = StoryEngine(repo, faker)
    page = asyncio.run(engine.start_story("A quest.", "epic"))

    assert page["seq"] == 1
    assert page["title"] == "The Beginning"

    opts = repo.get_options(page["id"])
    assert len(opts) == 2
    for opt in opts:
        assert opt["target_page_id"] is None

    char = repo.get_character(page["id"])
    assert char is not None
    assert char.name == "Hero"

    story = repo.get_story(page["story_id"])
    assert story["last_page_id"] == page["id"]


def test_choose_generates_and_links(repo, faker):
    """choose page1.opt1 → page 2 (parent page1, option linked, merged character stored)."""
    engine = StoryEngine(repo, faker)
    page1 = asyncio.run(engine.start_story("A quest.", "epic"))

    opts = repo.get_options(page1["id"])
    page2 = asyncio.run(engine.choose(repo.get_story(page1["story_id"])["id"], page1, opts[0]))

    assert page2["parent_page_id"] == page1["id"]
    assert page2["title"] == "North Road"

    # Option is now linked
    opts_after = repo.get_options(page1["id"])
    assert opts_after[0]["target_page_id"] == page2["id"]

    # Character merged
    char = repo.get_character(page2["id"])
    assert char is not None
    assert char.location == "Forest"


def test_choose_branch_sibling(repo, faker):
    """choose page1.opt2 → page 3 (branch sibling of page 2)."""
    engine = StoryEngine(repo, faker)
    page1 = asyncio.run(engine.start_story("A quest.", "epic"))

    opts = repo.get_options(page1["id"])
    page2 = asyncio.run(engine.choose(repo.get_story(page1["story_id"])["id"], page1, opts[0]))
    page3 = asyncio.run(engine.choose(repo.get_story(page1["story_id"])["id"], page1, opts[1]))

    assert page3["parent_page_id"] == page1["id"]
    # Different from page2 (different script entry)


def test_linked_option_never_calls_generator(repo, faker):
    """Choosing page1.opt1 AGAIN → returns page 2, len(faker.calls) unchanged."""
    engine = StoryEngine(repo, faker)
    page1 = asyncio.run(engine.start_story("A quest.", "epic"))

    opts = repo.get_options(page1["id"])
    page2a = asyncio.run(engine.choose(repo.get_story(page1["story_id"])["id"], page1, opts[0]))
    calls_after_first = len(faker.calls)

    # Re-fetch options so target_page_id reflects the link from first choose
    opts = repo.get_options(page1["id"])

    # Choose the same option again — should return stored page, no LLM call
    page2b = asyncio.run(engine.choose(repo.get_story(page1["story_id"])["id"], page1, opts[0]))

    assert page2b["id"] == page2a["id"]
    assert len(faker.calls) == calls_after_first  # No new call


def test_ending_stored_with_zero_options(repo, faker):
    """Generator returning is_ending=True → stored with zero options."""
    ending_page = GeneratedPage(
        page_title="The End",
        page_text="You found what you sought.",
        is_ending=True,
        options=[],
        character=CharacterState(name="Hero"),
    )
    faker = FakeGenerator([ending_page])
    engine = StoryEngine(repo, faker)

    page = asyncio.run(engine.start_story("A quest.", "epic"))
    assert page["is_ending"] is True

    opts = repo.get_options(page["id"])
    assert len(opts) == 0


def test_choose_from_ending_raises(repo, faker):
    """choose on ending page → StoryEndedError."""
    # Create a normal (non-ending) page with options, then mark it as ending in DB.
    # We can't use GeneratedPage(is_ending=True, options=[...]) because the model
    # validator rejects ending pages with options.
    normal_page = GeneratedPage(
        page_title="Normal Page",
        page_text="This looks like an ending but isn't.",
        is_ending=False,
        options=[GeneratedOption(label="Continue"), GeneratedOption(label="Stop")],
        character=CharacterState(name="Hero"),
    )
    faker = FakeGenerator([normal_page])
    engine = StoryEngine(repo, faker)

    page = asyncio.run(engine.start_story("A quest.", "epic"))
    opts = repo.get_options(page["id"])

    # Mark the page as ending in the database
    with repo._open() as conn:
        conn.execute("UPDATE pages SET is_ending = 1 WHERE id = ?", (page["id"],))
        conn.commit()

    # Reload the page so is_ending reflects the DB change
    page = repo.get_page(page["id"])

    with pytest.raises(StoryEndedError):
        asyncio.run(engine.choose(repo.get_story(page["story_id"])["id"], page, opts[0]))


def test_history_has_12_entries_for_deep_path(repo):
    """12 pages deep: the 12th call's recorded ctx.history has 12 entries."""
    pages = []
    for i in range(12):
        if i == 11:
            # Ending page — no options
            pages.append(GeneratedPage(
                page_title=f"Page {i+1}",
                page_text=f"You are on page {i+1}.",
                is_ending=True,
                options=[],
                character=CharacterState(name="Hero"),
            ))
        else:
            # Non-ending pages need 2-4 options
            pages.append(GeneratedPage(
                page_title=f"Page {i+1}",
                page_text=f"You are on page {i+1}.",
                is_ending=False,
                options=[GeneratedOption(label="Continue"), GeneratedOption(label="Stop")],
                character=CharacterState(name="Hero"),
            ))

    faker = FakeGenerator(pages)
    engine = StoryEngine(repo, faker)

    page = asyncio.run(engine.start_story("A quest.", "epic"))
    story_id = repo.get_story(page["story_id"])["id"]

    # Walk through all 12 pages
    for i in range(11):  # 11 choices to reach page 12
        opts = repo.get_options(page["id"])
        page = asyncio.run(engine.choose(story_id, page, opts[0]))

    # The last call (generating page 12) has history = path to current page (page 11)
    assert len(faker.calls) == 12
    last_ctx = faker.calls[-1]
    assert len(last_ctx.history) == 11


def test_llm_error_leaves_no_partial_page(repo):
    """Generator raising LLMOutputError on choose → error propagates AND max_seq unchanged."""
    from choose_adventure.llm.errors import LLMOutputError

    page1 = GeneratedPage(
        page_title="Start",
        page_text="You begin.",
        is_ending=False,
        options=[GeneratedOption(label="Go"), GeneratedOption(label="Stay")],
        character=CharacterState(name="Hero"),
    )
    faker = FakeGenerator([page1, LLMOutputError("boom")])
    engine = StoryEngine(repo, faker)

    page = asyncio.run(engine.start_story("A quest.", "epic"))
    story_id = repo.get_story(page["story_id"])["id"]
    max_seq_before = repo.max_seq(story_id)

    opts = repo.get_options(page["id"])
    with pytest.raises(LLMOutputError):
        asyncio.run(engine.choose(story_id, page, opts[0]))

    # max_seq unchanged — no partial page
    assert repo.max_seq(story_id) == max_seq_before
