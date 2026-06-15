"""G-3: ToolPlan — policy/rate-limit/secret 불변식 강제."""
from __future__ import annotations

import pytest

from ingestion.orchestration.source_capability import capability_for
from ingestion.orchestration.strategy_graph import build_strategy_graph
from ingestion.orchestration.tool_plan import (
    HEADERS_BEARER,
    HEADERS_GENERIC_UA,
    HEADERS_SERVICE_KEY_QUERY,
    build_tool_plan,
)


def _node(sid, name):
    return build_strategy_graph(capability_for(sid)).node(name)


def test_gdelt_rate_limit_node_carries_rate_limit_key():
    cap = capability_for("gdelt")
    plan = build_tool_plan(cap, _node("gdelt", "spaced_single_probe"), url_or_endpoint="https://api")
    assert plan.rate_limit_key == "gdelt_host"     # rate-limit 체크 노드 → key 강제
    assert plan.headers_policy == "none"           # 키 불필요


def test_culture_info_service_key_policy():
    cap = capability_for("culture_info")
    plan = build_tool_plan(cap, _node("culture_info", "api_list_fetch"), url_or_endpoint="https://api")
    assert plan.headers_policy == HEADERS_SERVICE_KEY_QUERY


def test_product_hunt_bearer_policy():
    cap = capability_for("product_hunt")
    plan = build_tool_plan(cap, _node("product_hunt", "api_graphql_fetch"), url_or_endpoint="https://api")
    assert plan.headers_policy == HEADERS_BEARER


def test_dcinside_static_generic_ua():
    cap = capability_for("dcinside")
    plan = build_tool_plan(cap, _node("dcinside", "robots_allowed_list_fetch"), url_or_endpoint="https://x")
    assert plan.headers_policy == HEADERS_GENERIC_UA


def test_secret_value_in_params_rejected():
    cap = capability_for("culture_info")
    with pytest.raises(ValueError):
        build_tool_plan(cap, _node("culture_info", "api_list_fetch"),
                        url_or_endpoint="https://x", params={"serviceKey": "SECRET:abcd"})


def test_tool_plan_does_not_carry_secret():
    cap = capability_for("product_hunt")
    plan = build_tool_plan(cap, _node("product_hunt", "api_graphql_fetch"), url_or_endpoint="https://api")
    assert plan.carries_secret() is False          # 정책 이름만, 실키 없음
