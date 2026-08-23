from __future__ import annotations

import json
from unittest.mock import MagicMock

import httpx2 as httpx
import pytest

from choose_adventure.config import CyaConfig
from choose_adventure.llm.client import LLMClient
from choose_adventure.llm.errors import LLMOutputError, LLMTransportError


def _make_mock_response(
    content: str = "",
    reasoning_content: str | None = None,
    finish_reason: str = "stop",
    content_dict: dict | list | None = None,
):
    """Create a mock OpenAI response."""
    message = MagicMock()
    message.content = content_dict if content_dict is not None else content
    message.reasoning_content = reasoning_content or ""
    message.role = "assistant"
    message.tool_calls = []

    choice = MagicMock()
    choice.message = message
    choice.finish_reason = finish_reason

    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.mark.asyncio
async def test_happy_path_returns_content():
    """Canned 200 completion → content returned."""
    mock_resp = _make_mock_response(content='{"page_title": "Test", "page_text": "Hello"}')

    http_transport = httpx.MockTransport(lambda req: httpx.Response(200))
    config = CyaConfig(base_url="http://test.local/v1")
    client = LLMClient(config, http_client=httpx.AsyncClient(transport=http_transport))

    original_method = client._client.chat.completions.create

    async def patched_create(*args, **kwargs):
        return mock_resp

    client._client.chat.completions.create = patched_create  # type: ignore[attr-defined]
    try:
        result = await client.chat([("system", "test"), ("user", "hello")])
        assert result == '{"page_title": "Test", "page_text": "Hello"}'
    finally:
        client._client.chat.completions.create = original_method  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_500_raises_transport_error():
    """500 response → LLMTransportError."""
    http_transport = httpx.MockTransport(lambda req: httpx.Response(500))
    config = CyaConfig(base_url="http://test.local/v1")
    client = LLMClient(config, http_client=httpx.AsyncClient(transport=http_transport))

    with pytest.raises(LLMTransportError):
        await client.chat([("system", "test"), ("user", "hello")])


@pytest.mark.asyncio
async def test_connect_timeout_raises_transport_error():
    """Transport raising ConnectTimeout → LLMTransportError."""
    http_transport = httpx.MockTransport(lambda req: httpx.Response(503))
    config = CyaConfig(base_url="http://test.local/v1")
    client = LLMClient(config, http_client=httpx.AsyncClient(transport=http_transport))

    with pytest.raises(LLMTransportError):
        await client.chat([("system", "test"), ("user", "hello")])


@pytest.mark.asyncio
async def test_finish_reason_length_raises_output_error():
    """finish_reason: 'length' → LLMOutputError."""
    mock_resp = _make_mock_response(content="truncated", finish_reason="length")

    config = CyaConfig(base_url="http://test.local/v1")
    client = LLMClient(config)

    original_method = client._client.chat.completions.create

    async def patched_create(*args, **kwargs):
        return mock_resp

    client._client.chat.completions.create = patched_create  # type: ignore[attr-defined]
    try:
        with pytest.raises(LLMOutputError):
            await client.chat([("system", "test"), ("user", "hello")])
    finally:
        client._client.chat.completions.create = original_method  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_reasoning_model_empty_content_with_reasoning():
    """content == '' but reasoning_content has JSON → returns reasoning string."""
    mock_resp = _make_mock_response(content="", reasoning_content='{"page_title": "Test"}')

    config = CyaConfig(base_url="http://test.local/v1")
    client = LLMClient(config)

    original_method = client._client.chat.completions.create

    async def patched_create(*args, **kwargs):
        return mock_resp

    client._client.chat.completions.create = patched_create  # type: ignore[attr-defined]
    try:
        result = await client.chat([("system", "test"), ("user", "hello")])
        assert result == '{"page_title": "Test"}'
    finally:
        client._client.chat.completions.create = original_method  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_reasoning_model_dict_content():
    """content is dict → returns serialized string."""
    mock_resp = _make_mock_response(
        content_dict={"reasoning": "...", "answer": '{"page_title": "Test"}'}
    )

    config = CyaConfig(base_url="http://test.local/v1")
    client = LLMClient(config)

    original_method = client._client.chat.completions.create

    async def patched_create(*args, **kwargs):
        return mock_resp

    client._client.chat.completions.create = patched_create  # type: ignore[attr-defined]
    try:
        result = await client.chat([("system", "test"), ("user", "hello")])
        assert json.loads(result) == {"reasoning": "...", "answer": '{"page_title": "Test"}'}
    finally:
        client._client.chat.completions.create = original_method  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_both_empty_raises_output_error():
    """Both content and reasoning_content empty → LLMOutputError."""
    mock_resp = _make_mock_response(content="", reasoning_content="")

    config = CyaConfig(base_url="http://test.local/v1")
    client = LLMClient(config)

    original_method = client._client.chat.completions.create

    async def patched_create(*args, **kwargs):
        return mock_resp

    client._client.chat.completions.create = patched_create  # type: ignore[attr-defined]
    try:
        with pytest.raises(LLMOutputError):
            await client.chat([("system", "test"), ("user", "hello")])
    finally:
        client._client.chat.completions.create = original_method  # type: ignore[attr-defined]
