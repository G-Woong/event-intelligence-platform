"""Phase C StrategyRouter(최소) 결정 단위 테스트 (docs 03)."""
from __future__ import annotations

from ingestion.orchestration.source_profile import SourceProfile
from ingestion.orchestration.strategy_router import StrategyDecision, decide_strategy


def test_news_source_decision():
    p = SourceProfile("gdelt", purpose="news", preferred_strategy="api_json_fetch")
    d = decide_strategy(p)
    assert isinstance(d, StrategyDecision)
    assert d.purpose == "news"
    assert d.preferred_strategy == "api_json_fetch"
    assert d.confirmation_policy == "standard"
    assert d.should_enqueue_success is True


def test_community_source_forces_unconfirmed_policy():
    """community인데 yaml에서 standard로 남아도 보수적으로 보정한다(단독 확정 금지)."""
    p = SourceProfile("dcinside", purpose="community", is_community=True,
                      confirmation_policy="standard")
    d = decide_strategy(p)
    assert d.confirmation_policy == "unconfirmed_until_corroborated"


def test_community_explicit_policy_preserved():
    p = SourceProfile("hacker_news", purpose="community", is_community=True,
                      confirmation_policy="unconfirmed_until_corroborated")
    d = decide_strategy(p)
    assert d.confirmation_policy == "unconfirmed_until_corroborated"


def test_disabled_source_should_not_enqueue():
    p = SourceProfile("x", enabled=False)
    assert decide_strategy(p).should_enqueue_success is False


def test_requires_api_key_source_decision():
    p = SourceProfile("youtube", purpose="community", is_community=True,
                      requires_api_key=True, preferred_strategy="api_json_fetch")
    d = decide_strategy(p)
    # requires_api_key는 metadata 영역 — decision은 live check 없이 진행
    assert d.preferred_strategy == "api_json_fetch"
    assert d.should_enqueue_success is True


def test_preferred_strategy_none_is_stable():
    p = SourceProfile("y", preferred_strategy=None)
    d = decide_strategy(p)
    assert d.preferred_strategy is None
