"""HTTP server: game engine + per-player persistence + LLM, exposed over JSON.

Thin clients (terminal Textual apps) talk to this server only. The LLM
endpoint and the SQLite databases live here and are never exposed to
clients directly.

Auth: every request except `/api/health` must carry `X-CYA-Token` matching
`CYA_SERVER_TOKEN` (constant-time compare). Player identity travels in
`X-CYA-Player`; each player gets their own SQLite file
(`<data_dir>/stories-<player>.db`).
"""

from __future__ import annotations

import re
import secrets
from pathlib import Path
from typing import Protocol

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from choose_adventure.config import CyaConfig
from choose_adventure.llm.client import LLMClient
from choose_adventure.llm.errors import LLMError
from choose_adventure.llm.storygen import StoryGenerator
from choose_adventure.storage.repo import StoryRepository
from choose_adventure.story.engine import StoryEngine
from choose_adventure.story.errors import StoryEndedError
from choose_adventure.story.models import CharacterState, GeneratedPage

_TOKEN_HEADER = "X-CYA-Token"
_PLAYER_HEADER = "X-CYA-Player"
DEFAULT_PORT = 8787


class PageGeneratorProto(Protocol):
    """Minimal generator protocol so tests can inject FakeGenerator."""

    async def next_page(self, ctx) -> GeneratedPage: ...


def _sanitize_player(player: str) -> str:
    """Sanitize a player name for use as a filename (no path traversal)."""
    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "_", player).strip("._")
    return cleaned or "default"


class _Player:
    def __init__(self, name: str):
        self.name = name


def _auth_player(
    request: Request, player: str = Header(alias=_PLAYER_HEADER, default="default")
) -> _Player:
    """Dependency: validate the shared-secret token, return the sanitized player."""
    token = request.headers.get(_TOKEN_HEADER, "")
    expected = request.app.state.cya_token
    if not expected or not secrets.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="invalid or missing token")
    return _Player(_sanitize_player(player))


class StartStoryRequest(BaseModel):
    premise: str
    tone: str = ""


class ChooseRequest(BaseModel):
    page_id: int
    option_id: int


class AppState:
    """Per-app wiring: generator is injectable for tests."""

    def __init__(self, data_dir: Path, generator: PageGeneratorProto):
        self.data_dir = data_dir
        self.generator = generator

    def repo_for(self, player: _Player) -> StoryRepository:
        return StoryRepository(self.data_dir / f"stories-{player.name}.db")

    def engine_for(self, player: _Player) -> StoryEngine:
        return StoryEngine(self.repo_for(player), self.generator)


def _page_dict(page: dict) -> dict:
    """Page dict as the UI expects it (keys always present)."""
    return {
        "id": page["id"],
        "story_id": page["story_id"],
        "seq": page["seq"],
        "title": page["title"],
        "body": page["body"],
        "is_ending": page["is_ending"],
        "parent_page_id": page.get("parent_page_id"),
        "ascii_art": page.get("ascii_art", ""),
    }


def create_app(
    *, data_dir: Path, token: str, generator: PageGeneratorProto | None = None
) -> FastAPI:
    """Build the FastAPI app. `generator` is injectable for tests."""
    data_dir.mkdir(parents=True, exist_ok=True)
    if generator is None:
        config = CyaConfig.from_env()
        generator = StoryGenerator(LLMClient(config))

    state = AppState(data_dir, generator)

    app = FastAPI(title="Choose Your Adventure Server")
    app.state.cya = state
    app.state.cya_token = token

    @app.exception_handler(Exception)
    async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        """Any uncaught exception becomes a clean JSON 500 (traceback is logged)."""
        return JSONResponse(status_code=500, content={"detail": "internal server error"})

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/stories")
    def list_stories(player: _Player = Depends(_auth_player)) -> list[dict]:
        repo = state.repo_for(player)
        return [
            {
                "id": s.id,
                "title": s.title,
                "premise": s.premise,
                "created_at": s.created_at,
                "last_page_id": s.last_page_id,
            }
            for s in repo.list_stories()
        ]

    @app.get("/api/stories/latest")
    def latest_story(player: _Player = Depends(_auth_player)) -> dict | None:
        return state.repo_for(player).latest_story()

    @app.post("/api/stories", status_code=201)
    async def start_story(body: StartStoryRequest, player: _Player = Depends(_auth_player)) -> dict:
        try:
            page = await state.engine_for(player).start_story(body.premise, body.tone)
        except LLMError as e:
            raise HTTPException(status_code=502, detail=e.detail)
        return _page_dict(page)

    @app.get("/api/stories/{story_id}/first-page")
    def first_page(story_id: int, player: _Player = Depends(_auth_player)) -> dict:
        page_id = state.repo_for(player).first_page_id(story_id)
        return {"first_page_id": page_id}

    @app.post("/api/stories/{story_id}/choose")
    async def choose(
        story_id: int, body: ChooseRequest, player: _Player = Depends(_auth_player)
    ) -> dict:
        repo = state.repo_for(player)
        page = repo.get_page(body.page_id)
        if page is None:
            raise HTTPException(status_code=404, detail=f"page {body.page_id} not found")
        option = next(
            (o for o in repo.get_options(body.page_id) if o["id"] == body.option_id), None
        )
        if option is None:
            raise HTTPException(status_code=404, detail=f"option {body.option_id} not found")
        try:
            new_page = await state.engine_for(player).choose(story_id, page, option)
        except StoryEndedError as e:
            raise HTTPException(status_code=409, detail=str(e))
        except LLMError as e:
            raise HTTPException(status_code=502, detail=e.detail)
        return _page_dict(new_page)

    @app.get("/api/pages/{page_id}")
    def get_page(page_id: int, player: _Player = Depends(_auth_player)) -> dict:
        page = state.repo_for(player).get_page(page_id)
        if page is None:
            raise HTTPException(status_code=404, detail=f"page {page_id} not found")
        return _page_dict(page)

    @app.get("/api/pages/{page_id}/options")
    def get_options(page_id: int, player: _Player = Depends(_auth_player)) -> list[dict]:
        return state.repo_for(player).get_options(page_id)

    @app.get("/api/pages/{page_id}/character")
    def get_character(
        page_id: int, player: _Player = Depends(_auth_player)
    ) -> CharacterState | None:
        return state.repo_for(player).get_character(page_id)

    return app
