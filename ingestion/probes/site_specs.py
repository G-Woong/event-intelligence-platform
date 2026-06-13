from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

_CONFIG_PATH = Path(__file__).parent.parent / "configs" / "playwright_probe_sites.yaml"


@dataclass
class SiteSpec:
    site_id: str
    layer: str
    input_type: str
    collection_method: str
    start_url: str
    official: bool
    evidence_level: str
    max_items_default: int = 10
    min_interval_minutes: int = 60
    selectors: dict = field(default_factory=dict)
    status: dict = field(default_factory=dict)
    search_strategy: str = ""
    wait_after_ms: int = 0
    deferred: bool = False


def load_site_specs(config_path: Optional[Path] = None) -> dict[str, SiteSpec]:
    path = config_path or _CONFIG_PATH
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    result: dict[str, SiteSpec] = {}
    for site_id, data in raw.get("sites", {}).items():
        result[site_id] = SiteSpec(
            site_id=site_id,
            layer=data.get("layer", ""),
            input_type=data.get("input_type", "none"),
            collection_method=data.get("collection_method", "playwright"),
            start_url=data.get("start_url", ""),
            official=bool(data.get("official", False)),
            evidence_level=data.get("evidence_level", "low"),
            max_items_default=int(data.get("max_items_default", 10)),
            min_interval_minutes=int(data.get("min_interval_minutes", 60)),
            selectors=data.get("selectors", {}),
            status=data.get("status", {}),
            search_strategy=data.get("search_strategy", ""),
            wait_after_ms=int(data.get("wait_after_ms", 0)),
            deferred=bool(data.get("deferred", False)),
        )
    return result
