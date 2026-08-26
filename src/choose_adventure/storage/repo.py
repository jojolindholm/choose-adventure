import json
import sqlite3
from contextlib import closing
from pathlib import Path

from choose_adventure.story.models import (
    CharacterState,
    GeneratedPage,
)

from .db import connect, ensure_schema


class StorySummary:
    """Lightweight summary for listing stories."""

    def __init__(
        self,
        id: int,
        title: str,
        premise: str,
        created_at: str,
        last_page_id: int | None,
        name: str = "",
    ):
        self.id = id
        self.title = title
        self.premise = premise
        self.created_at = created_at
        self.last_page_id = last_page_id
        self.name = name


class PathStep:
    """A single step in a path from root to a page."""

    def __init__(self, page_title: str, page_body: str, chosen_label: str | None):
        self.page_title = page_title
        self.page_body = page_body
        self.chosen_label = chosen_label


class StoryRepository:
    """SQLite repository for story data.

    Every method opens its own connection (per-operation connections by design).
    """

    def __init__(self, db_path: Path):
        self._db_path = db_path

    def _open(self) -> sqlite3.Connection:
        conn = connect(self._db_path)
        ensure_schema(conn)
        return conn

    def create_story(self, premise: str, tone: str = "", name: str = "") -> dict:
        """Create a new story and return it as a dict."""
        import datetime

        with closing(self._open()) as conn:
            now = datetime.datetime.now(datetime.UTC).isoformat()
            cursor = conn.execute(
                "INSERT INTO stories (premise, tone, created_at, name) VALUES (?, ?, ?, ?)",
                (premise, tone, now, name),
            )
            story_id = cursor.lastrowid
            conn.commit()
            return {
                "id": story_id,
                "premise": premise,
                "tone": tone,
                "created_at": now,
                "last_page_id": None,
                "name": name,
            }

    def create_page(
        self,
        story_id: int,
        seq: int,
        title: str,
        body: str,
        is_ending: bool,
        parent_page_id: int | None,
        ascii_art: str = "",
    ) -> dict:
        """Create a page and return it as a dict."""
        with closing(self._open()) as conn:
            cursor = conn.execute(
                "INSERT INTO pages (story_id, seq, title, body, is_ending, parent_page_id, ascii_art) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (story_id, seq, title, body, 1 if is_ending else 0, parent_page_id, ascii_art),
            )
            page_id = cursor.lastrowid
            conn.commit()
            return {
                "id": page_id,
                "story_id": story_id,
                "seq": seq,
                "title": title,
                "body": body,
                "is_ending": is_ending,
                "parent_page_id": parent_page_id,
                "ascii_art": ascii_art,
            }

    def create_options(self, page_id: int, labels: list[str]) -> list[dict]:
        """Create options for a page and return them as dicts."""
        with closing(self._open()) as conn:
            options = []
            for seq, label in enumerate(labels, 1):
                cursor = conn.execute(
                    "INSERT INTO options (page_id, seq, label) VALUES (?, ?, ?)",
                    (page_id, seq, label),
                )
                options.append(
                    {
                        "id": cursor.lastrowid,
                        "page_id": page_id,
                        "seq": seq,
                        "label": label,
                        "target_page_id": None,
                    }
                )
            conn.commit()
            return options

    def link_option(self, option_id: int, target_page_id: int) -> None:
        """Link an option to its target page."""
        with closing(self._open()) as conn:
            conn.execute(
                "UPDATE options SET target_page_id = ? WHERE id = ?",
                (target_page_id, option_id),
            )
            conn.commit()

    def get_story(self, story_id: int) -> dict | None:
        """Get a story by ID."""
        with closing(self._open()) as conn:
            cursor = conn.execute("SELECT * FROM stories WHERE id = ?", (story_id,))
            row = cursor.fetchone()
            if row is None:
                return None
            return dict(row)

    def get_page(self, page_id: int) -> dict | None:
        """Get a page by ID."""
        with closing(self._open()) as conn:
            cursor = conn.execute("SELECT * FROM pages WHERE id = ?", (page_id,))
            row = cursor.fetchone()
            if row is None:
                return None
            page = dict(row)
            page["is_ending"] = bool(page["is_ending"])
            return page

    def get_options(self, page_id: int) -> list[dict]:
        """Get options for a page, ordered by seq."""
        with closing(self._open()) as conn:
            cursor = conn.execute(
                "SELECT * FROM options WHERE page_id = ? ORDER BY seq", (page_id,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_character(self, page_id: int) -> CharacterState | None:
        """Get character state for a page."""
        with closing(self._open()) as conn:
            cursor = conn.execute("SELECT * FROM character_states WHERE page_id = ?", (page_id,))
            row = cursor.fetchone()
            if row is None:
                return None
            data = dict(row)
            # Parse JSON lists
            data["traits"] = json.loads(data["traits"])
            data["inventory"] = json.loads(data["inventory"])
            return CharacterState(**data)

    def save_character(self, page_id: int, state: CharacterState) -> None:
        """Save character state for a page (INSERT OR REPLACE)."""
        with closing(self._open()) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO character_states (page_id, name, role, location, condition, traits, inventory)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    page_id,
                    state.name,
                    state.role,
                    state.location,
                    state.condition,
                    json.dumps(state.traits),
                    json.dumps(state.inventory),
                ),
            )
            conn.commit()

    def set_last_page(self, story_id: int, page_id: int) -> None:
        """Set the last_page_id for a story."""
        with closing(self._open()) as conn:
            conn.execute(
                "UPDATE stories SET last_page_id = ? WHERE id = ?",
                (page_id, story_id),
            )
            conn.commit()

    def max_seq(self, story_id: int) -> int:
        """Get the maximum seq for a story (0 if none)."""
        with closing(self._open()) as conn:
            cursor = conn.execute("SELECT MAX(seq) FROM pages WHERE story_id = ?", (story_id,))
            row = cursor.fetchone()
            return row[0] if row and row[0] is not None else 0

    def first_page_id(self, story_id: int) -> int | None:
        """Get the page id of seq=1 for a story (None if no pages)."""
        with closing(self._open()) as conn:
            cursor = conn.execute(
                "SELECT id FROM pages WHERE story_id = ? AND seq = 1", (story_id,)
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def latest_story(self) -> dict | None:
        """Get the most recently created story."""
        with closing(self._open()) as conn:
            cursor = conn.execute("SELECT * FROM stories ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            if row is None:
                return None
            return dict(row)

    def list_stories(self) -> list[StorySummary]:
        """List all stories with their page-1 title and generated name."""
        with closing(self._open()) as conn:
            cursor = conn.execute("""
                SELECT s.id, p.title AS story_title, s.premise, s.created_at, s.last_page_id,
                       s.name
                FROM stories s
                LEFT JOIN pages p ON s.id = p.story_id AND p.seq = 1
                ORDER BY s.id DESC
            """)
            results = []
            for row in cursor.fetchall():
                data = dict(row)
                results.append(
                    StorySummary(
                        id=data["id"],
                        title=data["story_title"] or "",
                        premise=data["premise"],
                        created_at=data["created_at"],
                        last_page_id=data["last_page_id"],
                        name=data["name"],
                    )
                )
            return results

    def path_to_page(self, story_id: int, page_id: int) -> list[PathStep]:
        """Walk from root to target page, collecting steps with chosen labels."""
        with closing(self._open()) as conn:
            # Build a map of page_id -> (parent_page_id, option_label)
            steps = []
            current_id = page_id
            while current_id is not None:
                # Get the page
                cursor = conn.execute("SELECT * FROM pages WHERE id = ?", (current_id,))
                page_row = cursor.fetchone()
                if page_row is None:
                    break
                page_data = dict(page_row)

                # Get the option that led to this page (from parent)
                chosen_label = None
                if page_data["parent_page_id"] is not None:
                    cursor = conn.execute(
                        "SELECT label FROM options WHERE page_id = ? AND target_page_id = ?",
                        (page_data["parent_page_id"], current_id),
                    )
                    opt_row = cursor.fetchone()
                    if opt_row:
                        chosen_label = dict(opt_row)["label"]

                steps.append(
                    PathStep(
                        page_title=page_data["title"],
                        page_body=page_data["body"],
                        chosen_label=chosen_label,
                    )
                )

                current_id = page_data["parent_page_id"]

            # Reverse to get root-to-target order
            steps.reverse()
            return steps

    def save_generated_page(
        self,
        story_id: int,
        parent_page_id: int,
        generated: GeneratedPage,
        character: CharacterState,
        option_id: int,
    ) -> dict:
        """Save a generated page in ONE transaction.

        Creates the page, its options, saves merged character, links option, sets last_page.
        On any exception, rolls back fully (no partial rows).
        """
        with closing(self._open()) as conn:
            try:
                # Create page (seq = max_seq + 1)
                cursor = conn.execute(
                    "SELECT MAX(seq) FROM pages WHERE story_id = ?",
                    (story_id,),
                )
                row = cursor.fetchone()
                seq = (row[0] if row and row[0] is not None else 0) + 1

                cursor = conn.execute(
                    "INSERT INTO pages (story_id, seq, title, body, is_ending, parent_page_id, ascii_art) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        story_id,
                        seq,
                        generated.page_title,
                        generated.page_text,
                        1 if generated.is_ending else 0,
                        parent_page_id,
                        generated.ascii_art,
                    ),
                )
                new_page_id = cursor.lastrowid

                # Create options for the new page
                for seq_opt, opt in enumerate(generated.options, 1):
                    conn.execute(
                        "INSERT INTO options (page_id, seq, label) VALUES (?, ?, ?)",
                        (new_page_id, seq_opt, opt.label),
                    )

                # Save character state
                conn.execute(
                    """INSERT OR REPLACE INTO character_states (page_id, name, role, location, condition, traits, inventory)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        new_page_id,
                        character.name,
                        character.role,
                        character.location,
                        character.condition,
                        json.dumps(character.traits),
                        json.dumps(character.inventory),
                    ),
                )

                # Link the parent option to this new page
                conn.execute(
                    "UPDATE options SET target_page_id = ? WHERE id = ?",
                    (new_page_id, option_id),
                )

                # Set last page for the story
                conn.execute(
                    "UPDATE stories SET last_page_id = ? WHERE id = ?",
                    (new_page_id, story_id),
                )

                conn.commit()

                return {
                    "id": new_page_id,
                    "story_id": story_id,
                    "seq": seq,
                    "title": generated.page_title,
                    "body": generated.page_text,
                    "is_ending": generated.is_ending,
                    "parent_page_id": parent_page_id,
                    "ascii_art": generated.ascii_art,
                }

            except Exception:
                conn.rollback()
                raise
