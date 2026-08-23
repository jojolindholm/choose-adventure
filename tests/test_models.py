import pytest
from pydantic import ValidationError

from choose_adventure.story.models import (
    CharacterState,
    GeneratedOption,
    GeneratedPage,
    GenerationContext,
    HistoryEntry,
    merge_character,
)


# --- GeneratedPage validation ---

def test_ending_page_requires_no_options():
    """Ending page with 2 options must raise ValidationError."""
    opt = GeneratedOption(label="Go")
    with pytest.raises(ValidationError):
        GeneratedPage(
            page_title="End",
            page_text="You reached the end.",
            is_ending=True,
            options=[opt],
            character=CharacterState(name="Hero"),
        )


def test_non_ending_requires_two_to_four_options():
    """Non-ending page with 1 option must raise ValidationError."""
    opt = GeneratedOption(label="Go")
    with pytest.raises(ValidationError):
        GeneratedPage(
            page_title="Start",
            page_text="You begin.",
            is_ending=False,
            options=[opt],  # only 1
            character=CharacterState(name="Hero"),
        )


def test_non_ending_with_five_options():
    """Non-ending page with 5 options must raise ValidationError."""
    opts = [GeneratedOption(label=f"Opt{i}") for i in range(5)]
    with pytest.raises(ValidationError):
        GeneratedPage(
            page_title="Start",
            page_text="You begin.",
            is_ending=False,
            options=opts,  # 5 options
            character=CharacterState(name="Hero"),
        )


def test_valid_three_option_page():
    """Valid 3-option non-ending page must pass."""
    opts = [GeneratedOption(label=f"Opt{i}") for i in range(3)]
    page = GeneratedPage(
        page_title="Start",
        page_text="You begin.",
        is_ending=False,
        options=opts,
        character=CharacterState(name="Hero"),
    )
    assert page.is_ending is False
    assert len(page.options) == 3


def test_valid_ending_page():
    """Valid ending page with empty options must pass."""
    page = GeneratedPage(
        page_title="End",
        page_text="The end.",
        is_ending=True,
        options=[],
        character=CharacterState(name="Hero"),
    )
    assert page.is_ending is True
    assert len(page.options) == 0


# --- GeneratedOption validation ---

def test_empty_label_raises():
    """Empty label must raise ValidationError."""
    with pytest.raises(ValidationError):
        GeneratedOption(label="")


def test_label_too_long_raises():
    """Label over 60 chars must raise ValidationError."""
    with pytest.raises(ValidationError):
        GeneratedOption(label="x" * 61)


def test_label_is_stripped():
    """Label whitespace is stripped."""
    opt = GeneratedOption(label="  Go  ")
    assert opt.label == "Go"


# --- merge_character ---

def test_merge_none_prev_returns_new():
    """prev is None → return new as-is."""
    new = CharacterState(name="Alice", role="Wizard")
    result = merge_character(None, new)
    assert result.name == "Alice"
    assert result.role == "Wizard"


def test_merge_empty_new_keeps_prev():
    """Empty new values keep prev values."""
    prev = CharacterState(name="Bob", role="Knight", location="Castle")
    new = CharacterState.model_construct(
        name="", role="", location="", condition="", traits=[], inventory=[]
    )  # all empty scalars, bypassed validation
    result = merge_character(prev, new)
    assert result.name == "Bob"
    assert result.role == "Knight"
    assert result.location == "Castle"


def test_merge_nonempty_new_overrides():
    """Non-empty new values override prev."""
    prev = CharacterState(name="Bob", location="Castle")
    new = CharacterState(name="Alice", location="Forest")
    result = merge_character(prev, new)
    assert result.name == "Alice"
    assert result.location == "Forest"


def test_merge_list_new_overrides():
    """Non-empty new list overrides prev list."""
    prev = CharacterState(name="Bob", traits=["brave"], inventory=["sword"])
    new = CharacterState(name="Alice", traits=["cunning"], inventory=[])  # empty list
    result = merge_character(prev, new)
    assert result.traits == ["cunning"]  # non-empty overrides
    assert result.inventory == ["sword"]  # empty list → keep prev


def test_merge_list_empty_new_keeps_prev():
    """Empty new list keeps prev list."""
    prev = CharacterState(name="Bob", traits=["brave"], inventory=["sword"])
    new = CharacterState(name="Alice", traits=[], inventory=[])  # both empty
    result = merge_character(prev, new)
    assert result.traits == ["brave"]
    assert result.inventory == ["sword"]


def test_merge_name_empty_keeps_prev():
    """Name: new.name or prev.name."""
    prev = CharacterState(name="Bob")
    new = CharacterState.model_construct(
        name="", role="", location="", condition="", traits=[], inventory=[]
    )  # empty name, bypassed validation
    result = merge_character(prev, new)
    assert result.name == "Bob"


def test_merge_name_nonempty_overrides():
    """Name: new.name or prev.name."""
    prev = CharacterState(name="Bob")
    new = CharacterState(name="Alice")
    result = merge_character(prev, new)
    assert result.name == "Alice"
