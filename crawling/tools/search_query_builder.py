from __future__ import annotations


def build_news_search_query(
    source_name: str,
    keywords: list[str] | None = None,
    date_range_days: int = 1,
) -> str:
    base = f"site:{source_name}" if "." in source_name else source_name
    if keywords:
        kw = " ".join(keywords[:3])
        return f"{kw} {base}"
    return base


def build_community_search_query(
    keywords: list[str],
    subreddit: str | None = None,
) -> str:
    kw = " ".join(keywords[:5])
    if subreddit:
        return f"{kw} subreddit:{subreddit}"
    return kw
