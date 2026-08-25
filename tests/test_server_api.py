"""Server API tests: auth, per-player isolation, and the full story flow.

Uses FastAPI's TestClient with an injected FakeGenerator, so no network.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from choose_adventure.llm.errors import LLMOutputError
from choose_adventure.server.app import create_app
from choose_adventure.story.models import CharacterState, GeneratedOption, GeneratedPage

from .fakes import FakeGenerator

TOKEN = "test-secret"

ART = "  /\\\n /  \\\n/____\\"


def _pages() -> list[GeneratedPage | Exception]:
    page1 = GeneratedPage(
        page_title="The Beginning",
        page_text="You stand at a crossroads.",
        is_ending=False,
        options=[GeneratedOption(label="Go north"), GeneratedOption(label="Stay here")],
        character=CharacterState(name="Hero", role="Adventurer"),
        ascii_art=ART,
    )
    page2 = GeneratedPage(
        page_title="North Road",
        page_text="You walk north through the forest.",
        is_ending=False,
        options=[GeneratedOption(label="Continue"), GeneratedOption(label="Turn back")],
        character=CharacterState(name="Hero", role="Adventurer", location="Forest"),
    )
    return [page1, page2]


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(data_dir=tmp_path, token=TOKEN, generator=FakeGenerator(_pages()))
    with TestClient(app) as c:
        yield c


def _headers(player: str = "alice") -> dict[str, str]:
    return {"X-CYA-Token": TOKEN, "X-CYA-Player": player}


def test_health_is_open(client: TestClient) -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_auth_rejects_missing_and_wrong_token(client: TestClient) -> None:
    assert client.get("/api/stories").status_code == 401
    assert client.get("/api/stories", headers={"X-CYA-Token": "wrong"}).status_code == 401


def test_start_story_returns_page(client: TestClient) -> None:
    resp = client.post(
        "/api/stories",
        headers=_headers(),
        json={"premise": "A quest.", "tone": "epic"},
    )
    assert resp.status_code == 201
    page = resp.json()
    assert page["seq"] == 1
    assert page["title"] == "The Beginning"
    assert page["body"] == "You stand at a crossroads."
    assert page["ascii_art"] == ART
    assert page["is_ending"] is False


def test_choose_generates_linked_page(client: TestClient) -> None:
    page1 = client.post("/api/stories", headers=_headers(), json={"premise": "A quest."}).json()
    options = client.get(f"/api/pages/{page1['id']}/options", headers=_headers()).json()
    assert len(options) == 2

    page2 = client.post(
        f"/api/stories/{page1['story_id']}/choose",
        headers=_headers(),
        json={"page_id": page1["id"], "option_id": options[0]["id"]},
    ).json()
    assert page2["title"] == "North Road"
    assert page2["parent_page_id"] == page1["id"]

    # Option is now linked on the server.
    options_after = client.get(f"/api/pages/{page1['id']}/options", headers=_headers()).json()
    assert options_after[0]["target_page_id"] == page2["id"]


def test_get_page_character_and_first_page(client: TestClient) -> None:
    page1 = client.post("/api/stories", headers=_headers(), json={"premise": "A quest."}).json()

    char = client.get(f"/api/pages/{page1['id']}/character", headers=_headers()).json()
    assert char["name"] == "Hero"
    assert char["role"] == "Adventurer"

    fp = client.get(f"/api/stories/{page1['story_id']}/first-page", headers=_headers()).json()
    assert fp["first_page_id"] == page1["id"]

    story = client.get("/api/stories/latest", headers=_headers()).json()
    assert story["id"] == page1["story_id"]
    assert story["last_page_id"] == page1["id"]


def test_per_player_isolation(client: TestClient) -> None:
    """Stories created by one player are invisible to another."""
    client.post("/api/stories", headers=_headers("alice"), json={"premise": "Alice's quest."})
    assert len(client.get("/api/stories", headers=_headers("alice")).json()) == 1
    assert client.get("/api/stories", headers=_headers("bob")).json() == []


def test_choose_with_unknown_option_returns_404(client: TestClient) -> None:
    client.post("/api/stories", headers=_headers(), json={"premise": "A quest."})
    resp = client.post(
        "/api/stories/1/choose",
        headers=_headers(),
        json={"page_id": 1, "option_id": 9999},
    )
    assert resp.status_code == 404


def test_unknown_page_returns_404(client: TestClient) -> None:
    assert client.get("/api/pages/12345", headers=_headers()).status_code == 404


def test_player_name_sanitized(tmp_path: Path) -> None:
    """Hostile player names cannot escape the data dir."""
    app = create_app(data_dir=tmp_path, token=TOKEN, generator=FakeGenerator(_pages()))
    with TestClient(app) as c:
        resp = c.post(
            "/api/stories",
            headers={"X-CYA-Token": TOKEN, "X-CYA-Player": "../evil"},
            json={"premise": "A quest."},
        )
        assert resp.status_code == 201
    db_files = [p.name for p in tmp_path.iterdir()]
    assert db_files == ["stories-evil.db"]
    assert not (tmp_path.parent / "evil.db").exists()


def test_llm_failure_maps_to_502(tmp_path: Path) -> None:
    """Generator raising LLMOutputError surfaces as a 502 with the detail."""
    script: list[GeneratedPage | Exception] = [LLMOutputError("boom")]
    app = create_app(data_dir=tmp_path, token=TOKEN, generator=FakeGenerator(script))
    with TestClient(app) as c:
        resp = c.post("/api/stories", headers=_headers(), json={"premise": "A quest."})
        assert resp.status_code == 502
        assert resp.json()["detail"] == "boom"
