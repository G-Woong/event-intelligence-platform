from __future__ import annotations

from typing import Optional

from crawling.sources.base import SourceCrawler

_source_instances: dict[str, SourceCrawler] = {}

_SOURCE_MAP: dict[str, str] = {
    "_dummy": "crawling.sources._dummy.DummySource",
    "bbc": "crawling.sources.bbc.BBCSource",
    "ap_news": "crawling.sources.ap_news.APNewsSource",
    "techcrunch": "crawling.sources.techcrunch.TechCrunchSource",
    "the_verge": "crawling.sources.the_verge.TheVergeSource",
    "zdnet_korea": "crawling.sources.zdnet_korea.ZDNetKoreaSource",
    "etnews": "crawling.sources.etnews.ETNewsSource",
    "yna": "crawling.sources.yna.YNASource",
    "hankyung": "crawling.sources.hankyung.HankyungSource",
    "maekyung": "crawling.sources.maekyung.MaekyungSource",
    "aljazeera": "crawling.sources.aljazeera.AlJazeeraSource",
}


def _load_class(dotted: str):
    module_path, cls_name = dotted.rsplit(".", 1)
    import importlib
    mod = importlib.import_module(module_path)
    return getattr(mod, cls_name)


def get_source_instance(source_id: str) -> Optional[SourceCrawler]:
    if source_id in _source_instances:
        return _source_instances[source_id]

    cls_path = _SOURCE_MAP.get(source_id)
    if cls_path is None:
        return None

    from crawling.core.source_registry import load_registry
    registry = load_registry()
    spec = registry.get(source_id)
    if spec is None:
        return None

    cls = _load_class(cls_path)
    inst = cls(spec)
    _source_instances[source_id] = inst
    return inst
