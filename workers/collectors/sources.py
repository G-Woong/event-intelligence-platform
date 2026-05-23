from __future__ import annotations

from typing import TypedDict


class SourceConfig(TypedDict):
    name: str
    url: str
    theme_hint: str
    enabled: bool


DEFAULT_SOURCES: list[SourceConfig] = [
    {
        "name": "bbc_world",
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "theme_hint": "geopolitics",
        "enabled": True,
    },
    {
        "name": "reuters_business",
        "url": "https://feeds.reuters.com/reuters/businessNews",
        "theme_hint": "macro",
        "enabled": True,
    },
    {
        "name": "yna_economy",
        "url": "https://www.yna.co.kr/rss/economy.xml",
        "theme_hint": "macro_kr",
        "enabled": True,
    },
]


def get_sources() -> list[SourceConfig]:
    # RSS_SOURCES_CONFIG_PATH stub — DB-backed sources are STEP 008+
    return [s for s in DEFAULT_SOURCES if s["enabled"]]
