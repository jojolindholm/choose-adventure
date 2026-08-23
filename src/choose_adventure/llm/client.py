from __future__ import annotations

import json
from typing import cast

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from choose_adventure.config import CyaConfig

from .errors import LLMOutputError, LLMTransportError


class LLMClient:
    """OpenAI-compatible async client with reasoning-model guard."""

    def __init__(self, config: CyaConfig, http_client=None):
        self._config = config
        self._client = AsyncOpenAI(
            base_url=config.base_url,
            api_key="no-auth",
            timeout=config.timeout,
            max_retries=0,
            http_client=http_client,
        )

    async def chat(self, messages: list[tuple[str, str]]) -> str:
        """Send a chat completion request and return the extracted text.

        REASONING-MODEL GUARD: huihui-qwen3.8-27b-abliterated may return JSON in reasoning_content
        or as a dict-valued content field. Extract in priority order:
        1. message.content if non-empty str
        2. message.reasoning_content if non-empty str
        3. json.dumps(message.content) when content is dict/list
        4. raise LLMOutputError("empty model reply")
        """
        try:
            params: list[ChatCompletionMessageParam] = [
                cast(ChatCompletionMessageParam, {"role": r, "content": c}) for r, c in messages
            ]
            resp = await self._client.chat.completions.create(
                model=self._config.model,
                messages=params,
                temperature=self._config.temperature,
                max_tokens=self._config.max_tokens,
            )

            choice = resp.choices[0]

            if choice.finish_reason == "length":
                raise LLMOutputError("response truncated at max_tokens")

            if not choice.message:
                raise LLMOutputError("no message in response")

            # Reasoning-model guard: extract text from various response shapes
            content = choice.message.content or ""

            # Priority 1: non-empty string in content
            if isinstance(content, str) and content.strip():
                return content

            # Priority 2: reasoning_content as string
            reasoning = getattr(choice.message, "reasoning_content", None) or ""
            if isinstance(reasoning, str) and reasoning.strip():
                return reasoning

            # Priority 3: content is a dict/list → serialize it
            if isinstance(content, (dict, list)):
                return json.dumps(content)

            # Priority 4: empty reply
            raise LLMOutputError("empty model reply")

        except Exception as e:
            if isinstance(e, LLMOutputError):
                raise
            # Wrap any openai/httpx exception in LLMTransportError
            raise LLMTransportError(str(e))
