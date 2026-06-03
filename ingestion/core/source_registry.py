from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class SourceSpec:
    id: str
    name: str
    type: str
    evidence_level: str
    role: str
    phase: int
    base_url: str
    layer: str = ""
    known_blockers: list[str] = field(default_factory=list)
    expected_fields: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "evidence_level": self.evidence_level,
            "role": self.role,
            "phase": self.phase,
            "base_url": self.base_url,
            "layer": self.layer,
            "known_blockers": self.known_blockers,
            "expected_fields": self.expected_fields,
            **self.extra,
        }


_KNOWN_FIELDS = {
    "id", "name", "type", "evidence_level", "role",
    "phase", "base_url", "layer", "known_blockers", "expected_fields",
}


class SourceRegistry:
    def __init__(self, config_dir: Path) -> None:
        self._config_dir = config_dir
        self._sources: dict[str, SourceSpec] = {}
        self._load()

    def _load(self) -> None:
        registry_path = self._config_dir / "source_registry.yaml"
        with open(registry_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        for entry in data.get("sources", []):
            spec = SourceSpec(
                id=entry["id"],
                name=entry["name"],
                type=entry["type"],
                evidence_level=entry["evidence_level"],
                role=entry["role"],
                phase=entry["phase"],
                base_url=entry["base_url"],
                layer=entry.get("layer", ""),
                known_blockers=entry.get("known_blockers", []),
                expected_fields=entry.get("expected_fields", []),
                extra={k: v for k, v in entry.items() if k not in _KNOWN_FIELDS},
            )
            self._sources[spec.id] = spec

    def get(self, source_id: str) -> Optional[SourceSpec]:
        return self._sources.get(source_id)

    def get_by_phase(self, phase: int) -> list[SourceSpec]:
        return [s for s in self._sources.values() if s.phase == phase]

    def all(self) -> list[SourceSpec]:
        return list(self._sources.values())

    def __len__(self) -> int:
        return len(self._sources)


_CONFIGS_DIR = Path(__file__).parent.parent / "configs"


def load_registry(config_dir: Path = _CONFIGS_DIR) -> SourceRegistry:
    return SourceRegistry(config_dir)
