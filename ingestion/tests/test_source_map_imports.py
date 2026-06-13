from __future__ import annotations

import importlib

import pytest

from ingestion.sources._registry import _SOURCE_MAP, _load_class

# All 31 dotted-paths in _SOURCE_MAP must remain importable.
# This test guards against regression when source files are moved
# (e.g. sources/bbc.py -> sources/news/bbc.py) in a future round.


@pytest.mark.parametrize("source_id,dotted_path", list(_SOURCE_MAP.items()))
def test_source_map_class_importable(source_id, dotted_path):
    """Each _SOURCE_MAP entry must resolve to an importable class."""
    try:
        cls = _load_class(dotted_path)
    except (ImportError, AttributeError) as exc:
        pytest.fail(
            f"_SOURCE_MAP['{source_id}'] = '{dotted_path}' failed to import: {exc}"
        )
    assert cls is not None, f"_load_class returned None for '{dotted_path}'"


def test_source_map_has_31_entries():
    assert len(_SOURCE_MAP) == 31, (
        f"Expected 31 entries in _SOURCE_MAP, got {len(_SOURCE_MAP)}"
    )
