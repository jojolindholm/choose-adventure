"""Thin-client API adapter.

`RemoteStoryService` implements the exact surface the Textual screens use
from `StoryRepository` and `StoryEngine`, but over HTTP against `cya-server`.
The UI code (screens/widgets) is reused unchanged: the same object is passed
as both `repo` and `engine` to `AdventureApp`.

Sync methods (`get_page`, `get_options`, `latest_story`, ...) serve the
screens' synchronous read paths; async methods (`start_story`, `choose`) serve
the worker-based generation paths. Errors are mapped to the local exception
types the UI already handles: `LLMError` subclasses and `StoryEndedError`.
"""

from __future__ import annotations

import httpx

from choose_adventure.llm.errors import LLMOutputError, LLMTransportError
from choose_adventure.storage.repo import StorySummary
from choose_adventure.story.errors import StoryEndedError
from choose_adventure.story.models import CharacterState

_TOKEN_HEADER = "X-CYA-Token"
_PLAYER_HEADER = "X-CYA-Player"


class RemoteStoryService:
    """HTTP-backed implementation of the repo/engine surface used by the UI."""

    def __init__(
        self,
        base_url: str,
        token: str,
        player: str,
        timeout: float = 300.0,
        transport: httpx.BaseTransport | None = None,
    ):
        headers = {_TOKEN_HEADER: token, _PLAYER_HEADER: player}
        kwargs = {"base_url": base_url, "headers": headers, "timeout": timeout}
        if transport is not None:
            kwargs["transport"] = transport
        self._sync = httpx.Client(**kwargs)
        self._async = httpx.AsyncClient(**kwargs)

    # -- sync read surface (called from Textual screens) --

    def latest_story(self) -> dict | None:
        resp = self._request("GET", "/api/stories/latest")
        return resp.json()

    def list_stories(self) -> list[StorySummary]:
        data = self._request("GET", "/api/stories").json()
        return [StorySummary(**item) for item in data]

    def get_page(self, page_id: int) -> dict | None:
        return self._request("GET", f"/api/pages/{page_id}").json()

    def get_character(self, page_id: int) -> CharacterState | None:
        data = self._request("GET", f"/api/pages/{page_id}/character").json()
        return CharacterState(**data) if data is not None else None

    def get_options(self, page_id: int) -> list[dict]:
        return self._request("GET", f"/api/pages/{page_id}/options").json()

    def first_page_id(self, story_id: int) -> int | None:
        return self._request("GET", f"/api/stories/{story_id}/first-page").json()["first_page_id"]

    # -- async generation surface (called from workers) --

    async def start_story(self, premise: str, tone: str = "") -> dict:
        return await self._arequest("POST", "/api/stories", json={"premise": premise, "tone": tone})

    async def choose(self, story_id: int, page: dict, option: dict) -> dict:
        return await self._arequest(
            "POST",
            f"/api/stories/{story_id}/choose",
            json={"page_id": page["id"], "option_id": option["id"]},
        )

    # -- plumbing --

    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        try:
            resp = self._sync.request(method, url, **kwargs)
        except httpx.RequestError as e:
            raise LLMTransportError(f"cannot reach server: {e}") from e
        return self._raise_for_status(resp)

    async def _arequest(self, method: str, url: str, **kwargs) -> dict:
        try:
            resp = await self._async.request(method, url, **kwargs)
        except httpx.RequestError as e:
            raise LLMTransportError(f"cannot reach server: {e}") from e
        return self._raise_for_status(resp).json()

    def _raise_for_status(self, resp: httpx.Response) -> httpx.Response:
        if resp.status_code == 409:
            raise StoryEndedError("The story has ended.")
        if resp.status_code >= 400:
            detail = (
                resp.json().get("detail", "server error")
                if resp.headers.get("content-type", "").startswith("application/json")
                else str(resp.status_code)
            )
            if resp.status_code == 502:
                raise LLMOutputError(str(detail))
            raise LLMTransportError(f"server error ({resp.status_code}): {detail}")
        return resp
