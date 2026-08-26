from __future__ import annotations

from typing import Protocol

from choose_adventure.storage.repo import StoryRepository
from choose_adventure.story.errors import StoryEndedError
from choose_adventure.story.models import (
    GeneratedPage,
    GenerationContext,
    HistoryEntry,
    merge_character,
)


class PageGenerator(Protocol):
    """Protocol for page generation (production = StoryGenerator, tests = FakeGenerator)."""

    async def next_page(self, ctx: GenerationContext) -> GeneratedPage: ...


class StoryEngine:
    """Orchestrates story generation with lazy option links and exact replay."""

    def __init__(
        self, repo: StoryRepository, generator: PageGenerator, full_context_pages: int = 10
    ):
        self._repo = repo
        self._generator = generator
        self._full_context_pages = full_context_pages

    async def start_story(self, premise: str, tone: str = "") -> dict:
        """Start a new story from a premise.

        Generates page 1, stores it with options and character state.
        Returns the created page dict.
        """
        ctx = GenerationContext(premise=premise, tone=tone, character=None, history=[], choice=None)
        gen = await self._generator.next_page(ctx)

        story = self._repo.create_story(premise, tone, gen.story_name)
        page = self._repo.create_page(
            story["id"], 1, gen.page_title, gen.page_text, gen.is_ending, None, gen.ascii_art
        )
        self._repo.create_options(page["id"], [o.label for o in gen.options])
        self._repo.save_character(page["id"], gen.character)
        self._repo.set_last_page(story["id"], page["id"])

        return page

    async def choose(self, story_id: int, page: dict, option: dict) -> dict:
        """Choose an option on a page.

        - If the page is ending, raise StoryEndedError.
        - If the option already has a target_page_id (already generated), return it without LLM call.
        - Otherwise, generate the next page and store it.
        """
        if page["is_ending"]:
            raise StoryEndedError("Cannot choose from an ending page")

        # Lazy link: if already generated, return stored page
        if option.get("target_page_id") is not None:
            target = self._repo.get_page(option["target_page_id"])
            assert target is not None, "Linked option has no target page"
            return target

        # Build history context by walking path to current page
        steps = self._repo.path_to_page(story_id, page["id"])
        history = [
            HistoryEntry(title=s.page_title, body=s.page_body, chosen_label=s.chosen_label)
            for s in steps
        ]

        # Get story info and current character
        story = self._repo.get_story(story_id)
        assert story is not None, f"Story {story_id} not found"
        current_char = self._repo.get_character(page["id"])

        ctx = GenerationContext(
            premise=story["premise"],
            tone=story.get("tone", ""),
            character=current_char,
            history=history,
            choice=option["label"],
        )

        gen = await self._generator.next_page(ctx)

        # Merge character states
        merged_char = merge_character(current_char, gen.character)

        return self._repo.save_generated_page(
            story_id=story["id"],
            parent_page_id=page["id"],
            generated=gen,
            character=merged_char,
            option_id=option["id"],
        )
