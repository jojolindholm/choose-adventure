import sqlite3
from pathlib import Path

import pytest

from choose_adventure.storage.repo import StoryRepository
from choose_adventure.story.models import CharacterState, GeneratedOption, GeneratedPage


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Create a temporary database file."""
    return tmp_path / "test.db"


@pytest.fixture
def repo(tmp_db: Path) -> StoryRepository:
    """Create a repository pointing to the temp DB."""
    return StoryRepository(tmp_db)


def test_create_story(repo: StoryRepository):
    """Create a story and verify it."""
    story = repo.create_story("A dragon attacks.", "fantasy")
    assert story["premise"] == "A dragon attacks."
    assert story["tone"] == "fantasy"
    assert story["last_page_id"] is None


def test_round_trip(repo: StoryRepository):
    """Full round-trip: story → page → options → character → link."""
    # Create story
    story = repo.create_story("A quest.", "epic")

    # Create page 1
    page = repo.create_page(story["id"], 1, "The Beginning", "You start your quest.", False, None)
    assert page["seq"] == 1

    # Create options
    opts = repo.create_options(page["id"], ["Go north", "Stay here"])
    assert len(opts) == 2
    assert opts[0]["label"] == "Go north"

    # Create page 2
    page2 = repo.create_page(story["id"], 2, "North Road", "You walk north.", False, page["id"])
    assert page2["parent_page_id"] == page["id"]

    # Link option
    repo.link_option(opts[0]["id"], page2["id"])

    # Save character
    char = CharacterState(name="Hero", role="Adventurer", location="Crossroads")
    repo.save_character(page["id"], char)

    # Verify character round-trip
    loaded = repo.get_character(page["id"])
    assert loaded is not None
    assert loaded.name == "Hero"

    # Verify path_to_page
    steps = repo.path_to_page(story["id"], page2["id"])
    assert len(steps) == 2
    assert steps[0].page_title == "The Beginning"
    assert steps[1].page_title == "North Road"
    assert steps[1].chosen_label == "Go north"


def test_duplicate_seq_raises(repo: StoryRepository):
    """Duplicate (story_id, seq) should raise IntegrityError."""
    story = repo.create_story("Test", "")
    repo.create_page(story["id"], 1, "P1", "Body.", False, None)
    with pytest.raises(sqlite3.IntegrityError):
        repo.create_page(story["id"], 1, "P2", "Body.", False, None)


def test_latest_story_empty(repo: StoryRepository):
    """Empty repo → latest_story() is None."""
    assert repo.latest_story() is None


def test_list_stories_empty(repo: StoryRepository):
    """Empty repo → list_stories() == []."""
    assert repo.list_stories() == []


def test_first_page_id(repo: StoryRepository):
    """first_page_id returns the seq=1 page id for a story (None when no pages)."""
    story = repo.create_story("Test", "")
    assert repo.first_page_id(story["id"]) is None

    page = repo.create_page(story["id"], 1, "P1", "Body.", False, None)
    repo.create_page(story["id"], 2, "P2", "Body.", False, page["id"])
    assert repo.first_page_id(story["id"]) == page["id"]


def test_list_stories_shows_page1_title(repo: StoryRepository):
    """list_stories shows page-1 title."""
    story = repo.create_story("Test", "")
    repo.create_page(story["id"], 1, "First Page", "Body.", False, None)
    stories = repo.list_stories()
    assert len(stories) == 1
    assert stories[0].title == "First Page"


def test_character_json_roundtrip(repo: StoryRepository):
    """Character traits/inventory survive JSON round-trip."""
    story = repo.create_story("Test", "")
    page = repo.create_page(story["id"], 1, "P1", "Body.", False, None)
    char = CharacterState(name="Hero", traits=["brave", "kind"], inventory=["sword", "shield"])
    repo.save_character(page["id"], char)

    loaded = repo.get_character(page["id"])
    assert loaded is not None
    assert loaded.traits == ["brave", "kind"]
    assert loaded.inventory == ["sword", "shield"]


def test_save_generated_page_transaction_rollback(repo: StoryRepository):
    """save_generated_page where character violates NOT NULL name → raises AND max_seq unchanged."""
    story = repo.create_story("Test", "")

    # Create page 1 with an option
    page = repo.create_page(story["id"], 1, "P1", "Body.", False, None)
    opts = repo.create_options(page["id"], ["Go"])

    # max_seq before should be 1
    assert repo.max_seq(story["id"]) == 1

    # Try to save a generated page with empty name (violates NOT NULL)
    gen = GeneratedPage.model_construct(
        page_title="P2",
        page_text="Body.",
        is_ending=False,
        options=[GeneratedOption(label="Continue"), GeneratedOption(label="Stop")],
        character=CharacterState.model_construct(
            name=None, role="", location="", condition="", traits=[], inventory=[]
        ),
    )

    with pytest.raises(sqlite3.IntegrityError):  # NOT NULL constraint violation
        repo.save_generated_page(story["id"], page["id"], gen, gen.character, opts[0]["id"])

    # max_seq should be unchanged
    assert repo.max_seq(story["id"]) == 1

    # No orphan options rows
    opts_after = repo.get_options(page["id"])
    assert len(opts_after) == 1
