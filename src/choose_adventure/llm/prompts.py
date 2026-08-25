SYSTEM_PROMPT = (
    "You are the Game Master of a text adventure. You write vivid, atmospheric second-person prose.\n"
    "Reply with a single valid JSON object and NOTHING else - no markdown fences, no commentary, no trailing text.\n"
    "\n"
    "Schema:\n"
    "{\n"
    '  "page_title": string,           // 1-4 words\n'
    '  "page_text": string,            // 100-250 words, second person, present tense\n'
    '  "is_ending": boolean,           // true only when the story reaches a definite end\n'
    '  "options": [{"label": string}], // 2-4 choices, each max 8 words, must be [] when is_ending is true\n'
    '  "character": {\n'
    '    "name": string, "role": string, "location": string, "condition": string,\n'
    '    "traits": [string], "inventory": [string]\n'
    "  },\n"
    '  "ascii_art": string             // 8-20 lines of ASCII line-art depicting the scene (monochrome, no color codes)\n'
    "}\n"
    "Rules:\n"
    "- Stay strictly consistent with everything in the story so far: names, places, items, injuries, promises, consequences.\n"
    "- The new page must be a direct consequence of the player's chosen option.\n"
    '- Update "character" to the state AFTER this page. Change it only when the page\'s events justify it. Keep "name" unchanged.\n'
    '- When the story concludes (victory, death, escape, a final revelation), set "is_ending": true and "options": []'
)


def first_page_user_prompt(premise: str, tone: str = "") -> str:
    """Build the user prompt for generating page 1."""
    tone_str = tone or "default"
    return (
        f"STORY PREMISE: {premise}\n"
        f"TONE: {tone_str}\n"
        "\n"
        "Write page 1 of the story. Introduce the setting and invent the player character (name, role, a hint of background) through the scene. Present the first situation the player must react to."
    )


def next_page_user_prompt(
    premise: str,
    tone: str,
    character_json: str | None,
    history: list[dict[str, str | None]],
    choice: str,
    full_context_pages: int = 10,
) -> str:
    """Build the user prompt for generating the next page.

    Args:
        premise: The story's one-line premise.
        tone: The story's tone/genre.
        character_json: JSON string of current character state, or None if malformed.
        history: List of dicts with keys 'title', 'body', 'chosen_label'.
        choice: The player's chosen option label.
        full_context_pages: Number of recent pages to include in full (default 10).

    Returns:
        The formatted user prompt string.
    """
    # Build history block
    lines = []
    for i, entry in enumerate(history):
        title = entry.get("title", "")
        body = entry.get("body", "")
        chosen_label = entry.get("chosen_label")

        # Older entries beyond full_context_pages are collapsed
        if i < len(history) - full_context_pages and i < len(history) - 1:
            lines.append(f'{i + 1}. (Earlier: page "{title}" - the player chose "{chosen_label}")')
        elif i == len(history) - 1:
            # Last entry (current page): no -> line
            lines.append(f'{i + 1}. [Page "{title}"] {body}')
        else:
            # Middle entries: show -> chosen line
            lines.append(f'{i + 1}. [Page "{title}"] {body}')
            if chosen_label:
                lines.append(f'   -> the player chose: "{chosen_label}"')

    history_block = "\n".join(lines)

    # Build character state block
    char_block = ""
    if character_json:
        char_block = f"\nCHARACTER STATE (JSON): {character_json}"

    return (
        f"STORY PREMISE: {premise}\n"
        f"TONE: {tone or 'default'}\n"
        f"{char_block}\n"
        "\n"
        "STORY SO FAR (oldest to newest):\n"
        f"{history_block}\n"
        "\n"
        f"NOW WRITE the next page, in which the player: {choice}"
    )
