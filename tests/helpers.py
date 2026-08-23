

from pathlib import Path
from typing import Any

from choose_adventure.storage.repo import StoryRepository, StorySummary
from choose_adventure.story.models import CharacterState, GeneratedOption, GeneratedPage


def make_repo(tmp_path: Path) -> StoryRepository:
    """Create a StoryRepository pointing to a temp DB."""
    return StoryRepository(tmp_path / "test.db")


def seed_story(
    repo: StoryRepository,
    pages: list[tuple[str, str, list[str], CharacterState, bool]],
) -> dict:
    """Seed a story with pre-built pages.

    Args:
        repo: The repository to seed.
        pages: List of (title, body, labels, character, is_ending) tuples.

    Returns:
        The created story dict.
    """
    story = repo.create_story("Seeded", "")

    prev_page_id = None
    for i, (title, body, labels, character, is_ending) in enumerate(pages, 1):
        page = repo.create_page(story["id"], i, title, body, is_ending, prev_page_id)
        opts = repo.create_options(page["id"], labels)

        if i > 1 and prev_page_id is not None:
            # Link the option from previous page to this one (first option)
            prev_opts = repo.get_options(prev_page_id)
            if prev_opts:
                repo.link_option(prev_opts[0]["id"], page["id"])

        repo.save_character(page["id"], character)
        prev_page_id = page["id"]

    if prev_page_id is not None:
        repo.set_last_page(story["id"], prev_page_id)
    return story


def mk_page(**kw: Any) -> GeneratedPage:
    """Shortcut to create a GeneratedPage with defaults."""
    return GeneratedPage(
        page_title=kw.get("page_title", "Test"),
        page_text=kw.get("page_text", "Body."),
        is_ending=kw.get("is_ending", False),
        options=[GeneratedOption(label=o) for o in kw.get("options", [])],
        character=kw.get("character", CharacterState(name="Hero")),
    )
