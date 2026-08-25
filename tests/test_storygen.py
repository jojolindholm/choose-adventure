from __future__ import annotations

import pytest

from choose_adventure.llm.errors import LLMOutputError, LLMTransportError
from choose_adventure.llm.storygen import StoryGenerator
from choose_adventure.story.models import GeneratedPage, GenerationContext


class FakeChat:
    """Fake chat that returns scripted responses."""

    def __init__(self, responses: list[str | Exception]):
        self.responses = list(responses)
        self.call_count = 0

    async def chat(self, messages: list[tuple[str, str]]) -> str:
        self.call_count += 1
        resp = self.responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp


@pytest.mark.asyncio
async def test_garbage_then_valid_succeeds():
    """Garbage-then-valid → success (2 calls, 1 correction appended)."""
    fake = FakeChat(
        [
            LLMOutputError("bad json"),
            '{"page_title": "P2", "page_text": "Body.", "is_ending": false, "options": [{"label": "Continue"}, {"label": "Rest"}], "character": {"name": "Hero"}}',
        ]
    )
    gen = StoryGenerator(fake)  # type: ignore[arg-type]

    ctx = GenerationContext(premise="Test", tone="", history=[], choice="Go")
    result = await gen.next_page(ctx)
    assert isinstance(result, GeneratedPage)
    assert fake.call_count == 2


@pytest.mark.asyncio
async def test_always_garbage_raises_after_two_calls():
    """Always-garbage → LLMOutputError after exactly 2 calls."""
    fake = FakeChat([LLMOutputError("bad"), LLMOutputError("still bad")])
    gen = StoryGenerator(fake)  # type: ignore[arg-type]

    ctx = GenerationContext(premise="Test", tone="", history=[], choice="Go")
    with pytest.raises(LLMOutputError):
        await gen.next_page(ctx)
    assert fake.call_count == 2


@pytest.mark.asyncio
async def test_transport_error_propagates():
    """chat raising LLMTransportError → same error, exactly 1 call."""
    fake = FakeChat([LLMTransportError("network down")])
    gen = StoryGenerator(fake)  # type: ignore[arg-type]

    ctx = GenerationContext(premise="Test", tone="", history=[], choice="Go")
    with pytest.raises(LLMTransportError):
        await gen.next_page(ctx)
    assert fake.call_count == 1


@pytest.mark.asyncio
async def test_schema_violation_retries_with_correction():
    """JSON that parses but violates the schema → LLMOutputError → one retry."""
    bad = '{"page_title": "P2", "page_text": 12345, "is_ending": false, "options": [{"label": "A"}, {"label": "B"}], "character": {"name": "Hero"}}'
    good = '{"page_title": "P2", "page_text": "Body.", "is_ending": false, "options": [{"label": "A"}, {"label": "B"}], "character": {"name": "Hero"}}'
    fake = FakeChat([bad, good])
    gen = StoryGenerator(fake)  # type: ignore[arg-type]

    ctx = GenerationContext(premise="Test", tone="", history=[], choice="Go")
    result = await gen.next_page(ctx)
    assert isinstance(result, GeneratedPage)
    assert fake.call_count == 2


@pytest.mark.asyncio
async def test_string_options_are_accepted():
    """Models sometimes emit options as plain strings; they coerce to labels."""
    raw = '{"page_title": "P2", "page_text": "Body.", "is_ending": false, "options": ["Run", "Hide"], "character": {"name": "Hero"}}'
    fake = FakeChat([raw])
    gen = StoryGenerator(fake)  # type: ignore[arg-type]

    ctx = GenerationContext(premise="Test", tone="", history=[], choice="Go")
    result = await gen.next_page(ctx)
    assert [o.label for o in result.options] == ["Run", "Hide"]
    assert fake.call_count == 1
