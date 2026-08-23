from __future__ import annotations

import json

from choose_adventure.story.models import GenerationContext, GeneratedPage

from .client import LLMClient
from .errors import LLMOutputError, LLMTransportError
from .parse import correction_message, parse_generated_page
from .prompts import SYSTEM_PROMPT, first_page_user_prompt, next_page_user_prompt


class StoryGenerator:
    """Facade that builds prompts, calls the LLM, and parses responses."""

    def __init__(self, llm: LLMClient):
        self._llm = llm

    async def next_page(self, ctx: GenerationContext) -> GeneratedPage:
        """Generate the next page from a generation context.

        On LLMOutputError, retries once with a correction message.
        LLMTransportError propagates without retry.
        """
        # Build prompt
        if ctx.choice is None:
            user_prompt = first_page_user_prompt(ctx.premise, ctx.tone)
        else:
            # Build character JSON for context
            char_json = None
            if ctx.character is not None:
                char_json = ctx.character.model_dump_json()

            user_prompt = next_page_user_prompt(
                premise=ctx.premise,
                tone=ctx.tone,
                character_json=char_json,
                history=[{"title": h.title, "body": h.body, "chosen_label": h.chosen_label} for h in ctx.history],
                choice=ctx.choice,
            )

        messages = [("system", SYSTEM_PROMPT), ("user", user_prompt)]

        # First attempt
        try:
            raw = await self._llm.chat(messages)
            data = parse_generated_page(raw)
            return GeneratedPage.model_validate(data)
        except LLMOutputError as e:
            # One retry with correction message
            messages.append(("user", correction_message(e)))
            try:
                raw = await self._llm.chat(messages)
                data = parse_generated_page(raw)
                return GeneratedPage.model_validate(data)
            except LLMOutputError:
                raise  # Second failure → propagate

        except LLMTransportError:
            raise  # Transport errors don't retry
