from .errors import LLMOutputError


def extract_json(text: str) -> str:
    """Extract a JSON object from model output.

    Tries in order:
    1. Parse raw text as JSON directly
    2. Strip ```json/``` fences if present
    3. Slice text[text.find("{"):text.rfind("}")+1]

    Raises LLMOutputError if no braces found.
    """
    import json

    # Try raw parse first
    try:
        json.loads(text)
        return text
    except (json.JSONDecodeError, ValueError):
        pass

    # Try stripping ```json fences
    if "```" in text:
        start = text.find("```") + 3
        end = text.rfind("```")
        if end > start:
            fenced = text[start:end].strip()
            try:
                json.loads(fenced)
                return fenced
            except (json.JSONDecodeError, ValueError):
                pass

    # Try slicing between first { and last }
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start == -1 or brace_end == -1:
        raise LLMOutputError("No JSON object found in model output (no braces)")

    sliced = text[brace_start : brace_end + 1]
    try:
        json.loads(sliced)
        return sliced
    except (json.JSONDecodeError, ValueError):
        raise LLMOutputError("Text between braces is not valid JSON")


def parse_generated_page(text: str) -> dict:
    """Parse a model response into a GeneratedPage-compatible dict.

    Raises LLMOutputError with a <=200-char summary on any failure.
    """
    import json

    try:
        cleaned = extract_json(text)
        data = json.loads(cleaned)
    except LLMOutputError:
        raise
    except (json.JSONDecodeError, ValueError) as e:
        raise LLMOutputError(f"JSON parse failed: {str(e)[:200]}")

    return data


def correction_message(err: LLMOutputError) -> str:
    """Build a correction prompt for retrying the model."""
    return f"Your last reply was not valid: {err.detail}. Reply again with ONLY the JSON object matching the schema."
