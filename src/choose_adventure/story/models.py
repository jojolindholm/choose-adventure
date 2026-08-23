from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, model_validator


class CharacterState(BaseModel):
    name: str = Field(min_length=1)
    role: str = ""
    location: str = ""
    condition: str = ""
    traits: list[str] = []
    inventory: list[str] = []


class GeneratedOption(BaseModel):
    label: str = Field(min_length=1, max_length=60)

    @model_validator(mode="before")
    @classmethod
    def strip_label(cls, data: Any) -> Any:
        if isinstance(data, dict):
            data = dict(data)
            if "label" in data and isinstance(data["label"], str):
                data["label"] = data["label"].strip()
        return data


class GeneratedPage(BaseModel):
    page_title: str = Field(min_length=1, max_length=80)
    page_text: str = Field(min_length=1)
    is_ending: bool = False
    options: list[GeneratedOption] = []
    character: CharacterState

    @model_validator(mode="after")
    def validate_options(self) -> "GeneratedPage":
        if self.is_ending:
            if len(self.options) != 0:
                raise ValueError("Ending pages must have no options (empty list)")
        else:
            n = len(self.options)
            if n < 2 or n > 4:
                raise ValueError(f"Non-ending pages must have 2-4 options, got {n}")
        return self


class Story(BaseModel):
    id: int
    premise: str
    tone: str = ""
    created_at: str
    last_page_id: int | None = None


class Page(BaseModel):
    id: int
    story_id: int
    seq: int
    title: str
    body: str
    is_ending: bool = False
    parent_page_id: int | None = None


class Option(BaseModel):
    id: int
    page_id: int
    seq: int
    label: str
    target_page_id: int | None = None


class HistoryEntry(BaseModel):
    title: str
    body: str
    chosen_label: str | None = None


class GenerationContext(BaseModel):
    premise: str
    tone: str = ""
    character: CharacterState | None = None
    history: list[HistoryEntry] = []
    choice: str | None = None


def merge_character(
    prev: CharacterState | None, new: CharacterState
) -> CharacterState:
    """Merge character state from two pages.

    - If prev is None, return new as-is.
    - Otherwise merge field-wise: scalars use new when non-empty, else prev; lists use new when non-empty, else prev.
    """
    if prev is None:
        return new

    # Scalars: use new value when non-empty, else prev
    name = new.name or prev.name
    role = new.role or prev.role
    location = new.location or prev.location
    condition = new.condition or prev.condition

    # Lists: use new list when non-empty, else prev
    traits = new.traits if new.traits else prev.traits
    inventory = new.inventory if new.inventory else prev.inventory

    return CharacterState(
        name=name,
        role=role,
        location=location,
        condition=condition,
        traits=traits,
        inventory=inventory,
    )
