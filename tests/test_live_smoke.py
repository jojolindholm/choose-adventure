"""Live integration smoke test against the real LLM endpoint.

Marked `integration` so it is excluded from the default `pytest -q` run
(pyproject `addopts = "-m 'not integration'"`). Run explicitly with:
    uv run pytest -m integration -q
"""

from __future__ import annotations

import pytest

from choose_adventure.config import CyaConfig
from choose_adventure.llm.client import LLMClient
from choose_adventure.llm.storygen import StoryGenerator
from choose_adventure.storage.repo import StoryRepository
from choose_adventure.story.engine import StoryEngine


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_start_story(tmp_path) -> None:
    """Generate page 1 against the real endpoint and assert it was stored."""
    # Build config the same way main.py does: CYA_* env vars override defaults.
    config = CyaConfig.from_env()
    db_path = tmp_path / "stories.db"
    repo = StoryRepository(db_path)
    llm = LLMClient(config)
    gen = StoryGenerator(llm)
    engine = StoryEngine(repo, gen)

    page = await engine.start_story(
        "A lighthouse keeper finds a bottle with a name written inside.", "eerie"
    )

    # Page 1 was stored and is retrievable.
    assert page["seq"] == 1
    assert page["id"] is not None
    stored = repo.get_page(page["id"])
    assert stored is not None
    assert stored["title"] == page["title"]

    # Body is substantive.
    assert len(page["body"]) >= 50

    # Character has a name.
    char = repo.get_character(page["id"])
    assert char is not None
    assert char.name.strip() != ""

    # Either a non-ending page with 2-4 options, or an ending page.
    options = repo.get_options(page["id"])
    assert (2 <= len(options) <= 4) or page["is_ending"]

    # Evidence for the log.
    print(f"TITLE: {page['title']}")
    print(f"BODY: {page['body']}")
