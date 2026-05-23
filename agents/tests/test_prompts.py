from __future__ import annotations

import pytest

from agents.prompts import load_prompt


def test_load_prompt_summarize_event():
    text = load_prompt("summarize_event")
    assert "{title}" in text
    assert "{body}" in text
    assert len(text) > 20


def test_load_prompt_missing():
    with pytest.raises(FileNotFoundError):
        load_prompt("nonexistent_prompt_xyz")
