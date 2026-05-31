from __future__ import annotations

import pytest
from pathlib import Path

from crawling.core.source_registry import SourceRegistry, SourceSpec, load_registry

_CONFIGS_DIR = Path(__file__).parent.parent / "configs"


def test_registry_loads():
    registry = load_registry(_CONFIGS_DIR)
    assert len(registry) > 0


def test_registry_has_dummy():
    registry = load_registry(_CONFIGS_DIR)
    spec = registry.get("_dummy")
    assert spec is not None
    assert spec.id == "_dummy"


def test_registry_has_30_real_sources():
    registry = load_registry(_CONFIGS_DIR)
    real_sources = [s for s in registry.all() if s.id != "_dummy"]
    assert len(real_sources) == 30


def test_registry_phase_split():
    registry = load_registry(_CONFIGS_DIR)
    phase1 = registry.get_by_phase(1)
    phase2 = registry.get_by_phase(2)
    phase3 = registry.get_by_phase(3)
    assert len(phase1) == 10
    assert len(phase2) == 10
    assert len(phase3) == 10


def test_source_spec_fields():
    registry = load_registry(_CONFIGS_DIR)
    bbc = registry.get("bbc")
    assert bbc is not None
    assert bbc.type == "news"
    assert bbc.evidence_level == "tier1"
    assert bbc.phase == 1
    assert "title" in bbc.expected_fields


def test_source_spec_to_dict():
    spec = SourceSpec(
        id="test",
        name="Test",
        type="news",
        evidence_level="tier1",
        role="primary",
        phase=1,
        base_url="https://test.com",
    )
    d = spec.to_dict()
    assert d["id"] == "test"
    assert d["phase"] == 1


def test_unknown_source_returns_none():
    registry = load_registry(_CONFIGS_DIR)
    assert registry.get("nonexistent_source") is None
