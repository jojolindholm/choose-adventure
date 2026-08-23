

import pytest
from choose_adventure.llm.parse import extract_json, parse_generated_page, correction_message
from choose_adventure.llm.errors import LLMOutputError


def test_raw_valid_json_parses():
    """Raw valid JSON passes through."""
    text = '{"page_title": "Test", "page_text": "Hello"}'
    result = extract_json(text)
    assert result == text


def test_fenced_json_parses():
    """```json-fenced JSON is extracted."""
    text = 'Here is some text\n```json\n{"page_title": "Test"}\n```\nMore text'
    result = extract_json(text)
    assert '{"page_title": "Test"}' in result


def test_prose_before_json_parses():
    """Prose before JSON is handled by brace-slicing."""
    text = 'Sure! Here you go:\n\n{"page_title": "Test", "page_text": "Hello"}'
    result = extract_json(text)
    assert '{"page_title": "Test", "page_text": "Hello"}' in result


def test_garbage_raises():
    """Pure garbage raises LLMOutputError, not json.JSONDecodeError."""
    with pytest.raises(LLMOutputError):
        extract_json("this is not json at all")


def test_no_braces_raises():
    """Text with no braces raises LLMOutputError."""
    with pytest.raises(LLMOutputError):
        extract_json("no braces here")


def test_parse_generated_page_valid():
    """Valid JSON parses into a dict."""
    text = '{"page_title": "Test", "page_text": "Hello world.", "is_ending": false, "options": [], "character": {"name": "Hero"}}'
    result = parse_generated_page(text)
    assert isinstance(result, dict)
    assert result["page_title"] == "Test"


def test_parse_generated_page_invalid_raises():
    """Invalid JSON raises LLMOutputError."""
    with pytest.raises(LLMOutputError):
        parse_generated_page("not json")


def test_correction_message_contains_error_summary():
    """correction_message includes the error detail."""
    err = LLMOutputError("missing required field: page_title")
    msg = correction_message(err)
    assert "missing required field: page_title" in msg
