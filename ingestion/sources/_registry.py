from __future__ import annotations

from typing import Optional

from ingestion.sources.base import SourceCrawler

_source_instances: dict[str, SourceCrawler] = {}

_SOURCE_MAP: dict[str, str] = {
    # internal
    "_dummy": "ingestion.sources._dummy.DummySource",
    # Phase 1 — 기사형 뉴스
    "bbc": "ingestion.sources.bbc.BBCSource",
    "ap_news": "ingestion.sources.ap_news.APNewsSource",
    "techcrunch": "ingestion.sources.techcrunch.TechCrunchSource",
    "the_verge": "ingestion.sources.the_verge.TheVergeSource",
    "zdnet_korea": "ingestion.sources.zdnet_korea.ZDNetKoreaSource",
    "etnews": "ingestion.sources.etnews.ETNewsSource",
    "yna": "ingestion.sources.yna.YNASource",
    "hankyung": "ingestion.sources.hankyung.HankyungSource",
    "maekyung": "ingestion.sources.maekyung.MaekyungSource",
    "aljazeera": "ingestion.sources.aljazeera.AlJazeeraSource",
    # Phase 2 — 커뮤니티/소셜
    "reddit": "ingestion.sources.reddit.RedditSource",
    "hacker_news": "ingestion.sources.hacker_news.HackerNewsSource",
    "product_hunt": "ingestion.sources.product_hunt.ProductHuntSource",
    "youtube": "ingestion.sources.youtube.YouTubeSource",
    "dcinside": "ingestion.sources.dcinside.DCInsideSource",
    "fmkorea": "ingestion.sources.fmkorea.FMKoreaSource",
    "naver_blog_search": "ingestion.sources.naver_blog_search.NaverBlogSearchSource",
    "x": "ingestion.sources.x.XSource",
    "cnbc": "ingestion.sources.cnbc.CNBCSource",
    "blind": "ingestion.sources.blind.BlindSource",
    # Phase 3 — 공식/데이터
    "gdelt": "ingestion.sources.gdelt.GDELTSource",
    "opendart": "ingestion.sources.opendart.OpenDARTSource",
    "sec_edgar": "ingestion.sources.sec_edgar.SECEdgarSource",
    "krx_kind": "ingestion.sources.krx_kind.KRXKindSource",
    "bok_ecos": "ingestion.sources.bok_ecos.BOKECOSSource",
    "eia": "ingestion.sources.eia.EIASource",
    "federal_register": "ingestion.sources.federal_register.FederalRegisterSource",
    "eu_press_corner": "ingestion.sources.eu_press_corner.EUPressCornerSource",
    "naver_news_search": "ingestion.sources.naver_news_search.NaverNewsSearchSource",
    "reuters": "ingestion.sources.reuters.ReutersSource",
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

    from ingestion.core.source_registry import load_registry
    registry = load_registry()
    spec = registry.get(source_id)
    if spec is None:
        return None

    cls = _load_class(cls_path)
    inst = cls(spec)
    _source_instances[source_id] = inst
    return inst
