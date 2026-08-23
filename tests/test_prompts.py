

from choose_adventure.llm.prompts import (
    SYSTEM_PROMPT,
    first_page_user_prompt,
    next_page_user_prompt,
)


def test_system_prompt_contains_required_phrases():
    """SYSTEM_PROMPT must contain key instructions."""
    assert "single valid JSON object" in SYSTEM_PROMPT
    assert '"is_ending"' in SYSTEM_PROMPT
    assert 'Keep "name" unchanged' in SYSTEM_PROMPT


def test_first_page_user_prompt_basic():
    """Basic first page prompt."""
    result = first_page_user_prompt("A dragon attacks the village.")
    assert "STORY PREMISE: A dragon attacks the village." in result
    assert "TONE: default" in result


def test_first_page_user_prompt_with_tone():
    """First page prompt with explicit tone."""
    result = first_page_user_prompt("A detective story", "noir")
    assert "TONE: noir" in result


def test_next_page_user_prompt_basic():
    """Basic next page prompt with short history."""
    history = [
        {"title": "Page 1", "body": "You wake up.", "chosen_label": None},
        {"title": "Page 2", "body": "You see a door.", "chosen_label": "Open the door"},
    ]
    result = next_page_user_prompt(
        premise="Test", tone="", character_json=None, history=history, choice="Go through"
    )
    assert "STORY PREMISE: Test" in result
    assert "NOW WRITE the next page, in which the player: Go through" in result


def test_next_page_user_prompt_no_character_block():
    """When character_json is None, no CHARACTER STATE block."""
    history = [{"title": "P1", "body": "Body.", "chosen_label": None}]
    result = next_page_user_prompt(
        premise="Test", tone="", character_json=None, history=history, choice="Go"
    )
    assert "CHARACTER STATE" not in result


def test_next_page_user_prompt_with_character_block():
    """When character_json is provided, CHARACTER STATE block present."""
    history = [{"title": "P1", "body": "Body.", "chosen_label": None}]
    result = next_page_user_prompt(
        premise="Test", tone="", character_json='{"name":"Alice"}', history=history, choice="Go"
    )
    assert 'CHARACTER STATE (JSON): {"name":"Alice"}' in result


def test_next_page_user_prompt_history_rendering():
    """History entries render with [Page "title"] and -> chosen_label."""
    history = [
        {"title": "P1", "body": "Body 1.", "chosen_label": None},
        {"title": "P2", "body": "Body 2.", "chosen_label": "Choice A"},
        {"title": "P3", "body": "Body 3.", "chosen_label": None},
    ]
    result = next_page_user_prompt(
        premise="Test", tone="", character_json=None, history=history, choice="Go"
    )
    assert '[Page "P1"] Body 1.' in result
    assert "-> the player chose: \"Choice A\"" in result


def test_next_page_user_prompt_last_entry_no_arrow():
    """Last entry (current page) has no -> line."""
    history = [
        {"title": "P1", "body": "Body 1.", "chosen_label": None},
        {"title": "P2", "body": "Body 2.", "chosen_label": None},
    ]
    result = next_page_user_prompt(
        premise="Test", tone="", character_json=None, history=history, choice="Go"
    )
    # P2 is the last entry — no -> line after it
    assert '[Page "P2"] Body 2.' in result


def test_next_page_user_prompt_collapse_old_entries():
    """Entries older than full_context_pages are collapsed."""
    # 12 entries, full_context_pages=10 → entry at index 1 (the second oldest) should be collapsed
    history: list[dict[str, str | None]] = [
        {"title": f"P{i}", "body": f"Body {i}.", "chosen_label": f"Choice {i}"}
        for i in range(12)
    ]
    result = next_page_user_prompt(
        premise="Test", tone="", character_json=None, history=history, choice="Go", full_context_pages=10
    )
    # Entry 2 (index 1) should be collapsed: "(Earlier: page \"P1\" - the player chose \"Choice 1\")"
    assert '(Earlier: page "P1"' in result
    # Entry 3 (index 2) should NOT be collapsed — it's within the last 10
    assert '[Page "P2"] Body 2.' in result
