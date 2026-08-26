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


def test_create_story_with_name(repo: StoryRepository):
    """create_story stores the generated story name."""
    story = repo.create_story("A quest.", "epic", name="The Ember Road")
    assert story["name"] == "The Ember Road"
    loaded = repo.get_story(story["id"])
    assert loaded is not None
    assert loaded["name"] == "The Ember Road"


def test_list_stories_includes_name(repo: StoryRepository):
    """list_stories exposes the story name (empty for unnamed stories)."""
    repo.create_story("A quest.", "epic", name="The Ember Road")
    repo.create_story("Plain", "")
    stories = repo.list_stories()
    assert len(stories) == 2
    by_id = {s.id: s for s in stories}
    named = [s for s in stories if s.name]
    assert len(named) == 1
    assert named[0].name == "The Ember Road"
    assert by_id[named[0].id].premise == "A quest."


def test_v2_db_migrates_story_name(tmp_db: Path):
    """A v2 database gains stories.name on ensure_schema, existing rows default ''."""
    conn = sqlite3.connect(str(tmp_db))
    conn.executescript(
        """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta (key, value) VALUES ('schema_version', '2');
        CREATE TABLE stories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            premise TEXT NOT NULL, tone TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL, last_page_id INTEGER
        );
        CREATE TABLE pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            story_id INTEGER NOT NULL REFERENCES stories(id),
            seq INTEGER NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
            is_ending INTEGER NOT NULL DEFAULT 0,
            parent_page_id INTEGER REFERENCES pages(id),
            ascii_art TEXT NOT NULL DEFAULT '',
            UNIQUE(story_id, seq)
        );
        CREATE TABLE options (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page_id INTEGER NOT NULL REFERENCES pages(id),
            seq INTEGER NOT NULL, label TEXT NOT NULL,
            target_page_id INTEGER REFERENCES pages(id),
            UNIQUE(page_id, seq)
        );
        CREATE TABLE character_states (
            page_id INTEGER PRIMARY KEY REFERENCES pages(id),
            name TEXT NOT NULL, role TEXT NOT NULL DEFAULT '',
            location TEXT NOT NULL DEFAULT '', condition TEXT NOT NULL DEFAULT '',
            traits TEXT NOT NULL DEFAULT '[]', inventory TEXT NOT NULL DEFAULT '[]'
        );
        INSERT INTO stories (id, premise, created_at) VALUES (1, 'old', 'now');
        """
    )
    conn.commit()
    conn.close()

    repo = StoryRepository(tmp_db)
    story = repo.get_story(1)
    assert story is not None
    assert story["name"] == ""
    # New stories written after migration accept a name.
    new_story = repo.create_story("New", "", name="Fresh Name")
    fresh = repo.get_story(new_story["id"])
    assert fresh is not None
    assert fresh["name"] == "Fresh Name"


def test_ascii_art_roundtrip(repo: StoryRepository):
    """create_page stores ascii_art; get_page returns it verbatim."""
    story = repo.create_story("Test", "")
    art = "  /\\\n /  \\\n/____\\"
    page = repo.create_page(story["id"], 1, "P1", "Body.", False, None, ascii_art=art)
    assert page["ascii_art"] == art
    loaded = repo.get_page(page["id"])
    assert loaded is not None
    assert loaded["ascii_art"] == art


def test_ascii_art_defaults_to_empty(repo: StoryRepository):
    """create_page without ascii_art stores an empty string."""
    story = repo.create_story("Test", "")
    page = repo.create_page(story["id"], 1, "P1", "Body.", False, None)
    loaded = repo.get_page(page["id"])
    assert loaded is not None
    assert loaded["ascii_art"] == ""


def test_save_generated_page_ascii_art(repo: StoryRepository):
    """save_generated_page persists generated.ascii_art."""
    story = repo.create_story("Test", "")
    page = repo.create_page(story["id"], 1, "P1", "Body.", False, None)
    opts = repo.create_options(page["id"], ["Go"])
    art = "  /\\\n /  \\\n/____\\"
    gen = GeneratedPage(
        page_title="P2",
        page_text="Body.",
        is_ending=False,
        options=[GeneratedOption(label="Continue"), GeneratedOption(label="Stop")],
        character=CharacterState(name="Hero"),
        ascii_art=art,
    )
    saved = repo.save_generated_page(story["id"], page["id"], gen, gen.character, opts[0]["id"])
    assert saved["ascii_art"] == art
    loaded = repo.get_page(saved["id"])
    assert loaded is not None
    assert loaded["ascii_art"] == art


def test_v1_db_migrates_ascii_art_column(tmp_db: Path):
    """A v1 database gains the ascii_art column on ensure_schema, existing rows default ''."""
    # Build a v1 database by hand (old schema, version 1)
    conn = sqlite3.connect(str(tmp_db))
    conn.executescript(
        """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta (key, value) VALUES ('schema_version', '1');
        CREATE TABLE stories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            premise TEXT NOT NULL, tone TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL, last_page_id INTEGER
        );
        CREATE TABLE pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            story_id INTEGER NOT NULL REFERENCES stories(id),
            seq INTEGER NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
            is_ending INTEGER NOT NULL DEFAULT 0,
            parent_page_id INTEGER REFERENCES pages(id),
            UNIQUE(story_id, seq)
        );
        CREATE TABLE options (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page_id INTEGER NOT NULL REFERENCES pages(id),
            seq INTEGER NOT NULL, label TEXT NOT NULL,
            target_page_id INTEGER REFERENCES pages(id),
            UNIQUE(page_id, seq)
        );
        CREATE TABLE character_states (
            page_id INTEGER PRIMARY KEY REFERENCES pages(id),
            name TEXT NOT NULL, role TEXT NOT NULL DEFAULT '',
            location TEXT NOT NULL DEFAULT '', condition TEXT NOT NULL DEFAULT '',
            traits TEXT NOT NULL DEFAULT '[]', inventory TEXT NOT NULL DEFAULT '[]'
        );
        INSERT INTO stories (id, premise, created_at) VALUES (1, 'old', 'now');
        INSERT INTO pages (id, story_id, seq, title, body) VALUES (1, 1, 1, 'Old', 'Old body.');
        """
    )
    conn.commit()
    conn.close()

    # Open via the repo path: ensure_schema migrates
    repo = StoryRepository(tmp_db)
    loaded = repo.get_page(1)
    assert loaded is not None
    assert loaded["ascii_art"] == ""

    # New pages written after migration accept ascii_art
    story = repo.create_story("New", "")
    page = repo.create_page(story["id"], 1, "New P", "Body.", False, None, ascii_art="art")
    new_loaded = repo.get_page(page["id"])
    assert new_loaded is not None
    assert new_loaded["ascii_art"] == "art"


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
